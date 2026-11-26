import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .db import now
from .documents import sha256
from .planning import bid_items, checklist, estimate_lines, estimate_summary, COST_CATS
from .review import applicable, flags

COMPANY = "[Bidder organization - replace before use]"
ROW_RE = re.compile(r"^(ITEM|OPTION)\s+(\S+)\s*\|\s*(.*?)\s*\|\s*([\d.]*)\s*\|\s*(\w*)\s*\|\s*\$?([\d,.]*)\s*\|\s*\$?([\d,.]*)\s*$")
TOTAL_RE = re.compile(r"BASE BID TOTAL\s*\|?\s*\$?([\d,.]*)")


def money(v):
    return f"${v:,.2f}"


def _pdf(path, title, lines):
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, title)
    c.setFont("Helvetica", 9.5)
    y -= 26
    for ln in lines:
        for chunk in [ln[i:i + 110] for i in range(0, max(len(ln), 1), 110)] or [""]:
            if y < 60:
                c.showPage()
                c.setFont("Helvetica", 9.5)
                y = 750
            c.drawString(50, y, chunk)
            y -= 14
    c.save()


def _lead(p, lead_id):
    return p.one("SELECT * FROM leads WHERE id=?", (lead_id,))


def _addenda(p, lead_id):
    return p.q("SELECT * FROM documents WHERE lead_id=? AND kind='addendum' ORDER BY addendum_no", (lead_id,))


def _texts(p, lead_id, cat):
    return [l["description"] for l in estimate_lines(p, lead_id) if l["category"] == cat]


def price_rows(p, lead_id):
    rows = []
    for b in bid_items(p, lead_id):
        price = b["unit_price"]
        ext = round(b["qty"] * price, 2) if price else None
        rows.append(("OPTION" if b["is_option"] else "ITEM", b["item_no"], b["description"], b["qty"], b["unit"], price, ext))
    return rows


def generate_package(p, lead_id):
    lead = _lead(p, lead_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = p.root / "generated" / str(lead_id) / f"package_{ts}"
    n = 2
    while out.exists():
        out = p.root / "generated" / str(lead_id) / f"package_{ts}_v{n}"
        n += 1
    (out / "03_Forms").mkdir(parents=True)
    (out / "04_Supporting").mkdir()
    due = applicable(p, lead_id, "bid_due")
    addenda = _addenda(p, lead_id)
    rows = price_rows(p, lead_id)
    base_total = round(sum(r[6] or 0 for r in rows if r[0] == "ITEM"), 2)

    cover = [datetime.now().strftime("%B %d, %Y"), "", lead["agency"] or "", "",
             f"RE: {lead['title']}  -  Solicitation {lead['solicitation_no']}", "",
             f"{COMPANY} is pleased to submit this bid for the above project.",
             f"Base bid total: {money(base_total)} (see Bid Price Sheet for unit prices and options).",
             "Addenda acknowledged: " + (", ".join(f"No. {a['addendum_no']}" for a in addenda) or "None issued"),
             f"Bid due (per documents): {due[0]['value'] if due else 'NOT FOUND - verify'}", ""]
    scope = _texts(p, lead_id, "scope")
    if scope:
        cover += ["Scope:"] + [f"  - {s}" for s in scope]
    for label, cat in (("Assumptions / clarifications:", "assumption"), ("Exclusions:", "exclusion")):
        items = _texts(p, lead_id, cat)
        if items:
            cover += ["", label] + [f"  - {s}" for s in items]
    cover += ["", "Respectfully,", "", "Signature: ______________________________   Date: ____________",
              "Name / Title: ___________________________", COMPANY]
    _pdf(out / "00_Cover_Letter.pdf", "Cover Letter - DRAFT", cover)

    lines = ["Type No. | Description | Qty | Unit | Unit Price | Extended", ""]
    for kind, no, desc, qty, unit, price, ext in rows:
        lines.append(f"{kind} {no} | {desc} | {qty:g} | {unit} | {money(price) if price else ''} | {money(ext) if ext else ''}")
    lines += ["", f"BASE BID TOTAL | {money(base_total) if base_total else ''}", "",
              "Options are priced separately and are not included in the base bid total.",
              "Authorized signature: ______________________________"]
    _pdf(out / "01_Bid_Price_Sheet.pdf", f"Bid Price Sheet - {lead['solicitation_no']}", lines)
    wb = Workbook()
    ws = wb.active
    ws.title = "Bid Price Sheet"
    ws.append(["Type", "No", "Description", "Qty", "Unit", "Unit Price", "Extended"])
    for r in rows:
        ws.append(list(r))
    ws.append(["TOTAL", "", "BASE BID TOTAL", "", "", "", base_total or None])
    wb.save(out / "01_Bid_Price_Sheet.xlsx")

    ack = [f"Solicitation {lead['solicitation_no']} - {lead['title']}", ""]
    ack += [f"Addendum No. {a['addendum_no']}  ({a['filename']})   Received and acknowledged. Initials: ______"
            for a in addenda] or ["No addenda attached to this bid record."]
    _pdf(out / "02_Addendum_Acknowledgment.pdf", "Acknowledgment of Addenda", ack)

    manifest = {"lead_id": lead_id, "created": now(), "files": {}, "sources": {}}
    forms = p.q("SELECT * FROM documents WHERE lead_id=? AND kind='form'", (lead_id,))
    for item in checklist(p, lead_id):
        if item["name"] == "Bid price sheet":
            continue
        src = p.root / item["file_path"] if item["file_path"] else None
        if not src and item["category"] == "form":
            code = re.match(r"Form\s+(\S+)", item["name"])
            match = [f for f in forms if code and re.search(rf"form[\s_\-]*{re.escape(code.group(1))}\b", f["filename"], re.I)]
            src = p.root / match[0]["original_path"] if match else None
        if src and src.exists():
            sub = "03_Forms" if item["category"] == "form" else "04_Supporting"
            dest = out / sub / f"{item['id']:03d}_{src.name.split('_', 1)[-1]}"
            shutil.copyfile(src, dest)
            manifest["sources"][str(dest.relative_to(out))] = str(src.relative_to(p.root))
    for f in out.rglob("*"):
        if f.is_file():
            manifest["files"][str(f.relative_to(out))] = sha256(f)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    internal = p.root / "generated" / str(lead_id) / "internal"
    internal.mkdir(exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(["Category", "Description", "Qty", "Unit", "Unit cost", "Extended"])
    for l in estimate_lines(p, lead_id):
        ws.append([l["category"], l["description"], l["qty"], l["unit"], l["unit_cost"], (l["qty"] or 0) * (l["unit_cost"] or 0)])
    s = estimate_summary(p, lead_id)
    ws.append(["", "Cost", "", "", "", s["cost"]])
    ws.append(["", f"Markup {s['markup_pct']}%", "", "", "", s["target"]])
    wb.save(internal / f"estimate_{ts}.xlsx")

    report = inspect_package(p, lead_id, out)
    status = "ready_for_review" if report["ready"] else "blocked"
    p.x("INSERT INTO packages(lead_id,folder,created_at,status,report) VALUES(?,?,?,?,?)",
        (lead_id, str(out.relative_to(p.root)), now(), status, json.dumps(report)))
    return out, report


def _num(s):
    s = (s or "").replace(",", "").replace("$", "").strip()
    return float(s) if s else None


def _pdf_text(path):
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)


def _annots(reader):
    out = []
    for i, pg in enumerate(reader.pages, 1):
        for a in pg.get("/Annots") or []:
            a = a.get_object()
            out.append((i, a.get("/Subtype"), int(a.get("/F", 0)), str(a.get("/Contents", ""))[:60]))
    return out


def inspect_package(p, lead_id, folder):
    """Opens the exported files themselves and checks their contents."""
    folder = Path(folder)
    res = []
    add = lambda check, status, detail: res.append(dict(check=check, status=status, detail=detail))

    # 1. pricing: parse the exported PDF, compare to the bid schedule required by the applicable documents
    sheet = folder / "01_Bid_Price_Sheet.pdf"
    req = {}
    for f in applicable(p, lead_id, "bid_item"):
        no, desc, qty, unit, opt = f["value"].split("|")
        src = f"Addendum {f['addendum_no']}" if f["kind"] == "addendum" else f["filename"]
        req[no] = dict(desc=desc, qty=float(qty), opt=int(opt), cite=f"{src}, p.{f['page']}")
    if not sheet.exists():
        add("Bid price sheet", "fail", "01_Bid_Price_Sheet.pdf is missing from the package.")
    else:
        text = _pdf_text(sheet)
        found = {}
        for ln in text.splitlines():
            m = ROW_RE.match(ln.strip())
            if m:
                found[m.group(2)] = dict(qty=_num(m.group(4)), price=_num(m.group(6)), ext=_num(m.group(7)))
        if not req:
            add("Bid schedule", "fail", "No bid items were found in the documents. Add them from the cited pages first.")
        blank, missing_opt, missing_item, bad_ext = [], [], [], []
        for no, r in req.items():
            row = found.get(no)
            if not row:
                (missing_opt if r["opt"] else missing_item).append(f"{no} ({r['cite']})")
            elif not row["price"]:
                blank.append(f"{no} ({r['cite']})")
            elif row["ext"] is None or abs(row["qty"] * row["price"] - row["ext"]) > 0.01 or abs(row["qty"] - r["qty"]) > 1e-6:
                bad_ext.append(no)
        extra = [n for n in found if n not in req]
        add("Price fields filled", "fail" if blank else "pass",
            f"Blank price on: {', '.join(blank)}" if blank else f"All {len(found)} priced lines have prices.")
        add("Required bid items present", "fail" if missing_item else "pass",
            f"Missing: {', '.join(missing_item)}" if missing_item else "All required base items are on the sheet.")
        add("Option / alternate lines present", "fail" if missing_opt else "pass",
            f"Missing: {', '.join(missing_opt)}" if missing_opt else "All required options are on the sheet.")
        if extra:
            add("No items outside the documents", "fail", f"Lines not in the current documents: {', '.join(extra)}")
        add("Line math (qty x unit price)", "fail" if bad_ext else "pass",
            f"Mismatch or qty differs from documents: {', '.join(bad_ext)}" if bad_ext else "Extended amounts match.")
        tm = TOTAL_RE.search(text)
        pdf_total = _num(tm.group(1)) if tm else None
        calc = round(sum(r["ext"] or 0 for n, r in found.items() if n in req and not req[n]["opt"]), 2)
        xl_total = None
        xl = folder / "01_Bid_Price_Sheet.xlsx"
        if xl.exists():
            for row in load_workbook(xl, data_only=True).active.iter_rows(values_only=True):
                if row[0] == "TOTAL":
                    xl_total = row[6]
        ok = pdf_total is not None and abs(pdf_total - calc) < 0.01 and xl_total is not None and abs(xl_total - pdf_total) < 0.01
        add("Totals match", "pass" if ok else "fail",
            f"PDF total {pdf_total}, sum of lines {calc}, spreadsheet total {xl_total}.")

    # 2. internal costs must not leak into customer-facing files
    internal_terms = [l["description"].lower() for l in estimate_lines(p, lead_id) if l["category"] in COST_CATS and len(l["description"]) > 3]
    public = " ".join([b["description"].lower() for b in bid_items(p, lead_id)] + [t.lower() for c in ("scope", "assumption", "exclusion") for t in _texts(p, lead_id, c)])
    internal_terms = [t for t in internal_terms if t not in public] + ["unit cost", "markup", "internal estimate"]
    leaks = []
    for f in folder.rglob("*"):
        if f.suffix.lower() == ".pdf" and "03_Forms" not in f.parts and "04_Supporting" not in f.parts:
            t = _pdf_text(f).lower()
            leaks += [f"{f.name}: '{w}'" for w in internal_terms if w in t]
    add("No internal costs in package", "fail" if leaks else "pass", "; ".join(leaks) or "No internal cost data found.")

    # 3. addenda acknowledged
    ackf = folder / "02_Addendum_Acknowledgment.pdf"
    ack_text = _pdf_text(ackf) if ackf.exists() else ""
    miss = [str(a["addendum_no"]) for a in _addenda(p, lead_id) if f"Addendum No. {a['addendum_no']}" not in ack_text]
    add("Addenda acknowledged", "fail" if miss else "pass",
        f"Not acknowledged: Addendum {', '.join(miss)}" if miss else "Every attached addendum is listed.")

    # 4. checklist items present in the package and readable
    files = {f.name.split("_", 1)[0]: f for f in folder.rglob("*") if f.is_file() and f.parent.name in ("03_Forms", "04_Supporting")}
    items = checklist(p, lead_id)
    if not items:
        add("Checklist", "fail", "No checklist items saved for this bid.")
    for it in items:
        if it["name"] == "Bid price sheet" or not it["required"] or it["status"] == "na":
            continue
        f = files.get(f"{it['id']:03d}")
        label = f"{'Form' if it['category'] == 'form' else 'Document'}: {it['name']}"
        if not f or f.stat().st_size == 0:
            add(label, "fail", "Not in the package. Attach the completed file.")
            continue
        if f.suffix.lower() == ".pdf":
            try:
                rd = PdfReader(str(f))
                assert len(rd.pages) > 0
            except Exception:
                add(label, "fail", f"{f.name} cannot be opened as a PDF.")
                continue
            _inspect_pdf(rd, f, label, add, p, folder, it)
        else:
            add(label, "pass", f"{f.name} attached ({f.stat().st_size:,} bytes).")
        if it["needs_signature"]:
            add(label + " - signature", "you", "Sign and date this yourself before submitting.")

    # 5. review-level gaps
    for kind, msg in flags(p, lead_id):
        if kind in ("missing", "conflict", "unreviewed"):
            add(f"First Review: {kind}", "fail", msg)
    add("Bid price sheet - signature", "you", "Sign the price sheet and cover letter yourself.")
    add("Submission", "you", "BidDesk never submits, emails, or signs. You submit through the official method.")
    fails = [r for r in res if r["status"] == "fail"]
    return dict(ready=not fails, results=res, folder=str(folder))


def _inspect_pdf(rd, f, label, add, p, folder, item):
    fields = rd.get_fields() or {}
    blank = [n for n, v in fields.items() if v.get("/FT") == "/Tx" and not str(v.get("/V") or "").strip()]
    unsigned = [n for n, v in fields.items() if v.get("/FT") == "/Sig" and not v.get("/V")]
    add(label + " - answers", "fail" if blank else "pass",
        f"Blank fields: {', '.join(blank[:8])}" if blank else f"{len(fields)} form field(s) checked." if fields else "No fillable fields (flat form).")
    if unsigned:
        add(label + " - signature fields", "you", f"Unsigned: {', '.join(unsigned)}")
    notes = [a for a in _annots(rd) if a[1] in ("/Text", "/FreeText", "/Highlight")]
    hidden = [a for a in notes if not a[2] & 4]
    src_rel = json.loads((folder / "manifest.json").read_text())["sources"].get(str(f.relative_to(folder))) if (folder / "manifest.json").exists() else None
    lost = 0
    if src_rel:
        lost = len(_annots(PdfReader(str(p.root / src_rel)))) - len(_annots(rd))
    if hidden or lost > 0:
        add(label + " - notes", "fail",
            f"{len(hidden)} note(s) will not print / may vanish when flattened or exported (p.{', '.join(str(a[0]) for a in hidden)}). "
            "Flatten or retype them into the form." + (f" {lost} annotation(s) lost vs. original." if lost > 0 else ""))


