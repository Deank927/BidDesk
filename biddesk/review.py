import re
from datetime import datetime

MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE = rf"(?:{MONTHS}\.?\s+\d{{1,2}},?\s*\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})"
CLOCK = r"(?:[0-9]{1,2}(?::[0-9]{2})?\s*[AaPp]\.?(?:\s*)[Mm]\.?|noon|midnight)"
ZONE = r"(?:Pacific(?:\s+(?:Standard|Daylight))?(?:\s+Time)?|Mountain(?:\s+Time)?|Central(?:\s+Time)?|Eastern(?:\s+Time)?|[PMCE][SD]?T|UTC|GMT|local time)"
WEEKDAY = r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?,?\s+)?"
DATE_RE = re.compile(DATE, re.I)
DATE_BLOCK = re.compile(
    rf"(?P<weekday>{WEEKDAY})(?P<date>{DATE})(?:\s*[,]?\s*(?:at\s+|@\s*)?(?P<clock>{CLOCK})(?![A-Za-z]))?"
    rf"(?:\s*\(?(?P<zone>{ZONE})\)?)?[. ;]*", re.I)
TIME_BLOCK = re.compile(rf"(?:at\s+)?(?P<clock>{CLOCK})(?![A-Za-z])(?:\s*\(?(?P<zone>{ZONE})\)?)?[. ;]*", re.I)
ZONE_BLOCK = re.compile(rf"\(?(?P<zone>{ZONE})\)?[. ;]*", re.I)
REVISION = r"(?:(?:(?:has\s+been|is|was)\s+)?(?:revised|extended|postponed|rescheduled|moved|changed)\s+to\s+)"
WALK = r"(?:(?:job|site)\s+walk|pre[- ]bid\s+(?:meeting|conference))"
EVENTS = (
    ("walk_registration", rf"(?:(?:mandatory\s+|optional\s+)?{WALK}\s+registration(?:\s+(?:cutoff|deadline|due))?|register\s+for\s+(?:the\s+)?{WALK}\s+by)"),
    ("job_walk", rf"(?:(?:mandatory|required|optional)\s+)?{WALK}(?:\s+is(?:\s+(?:mandatory|required|optional))?|\s+will\s+be(?:\s+held)?|\s+(?:date(?:\s*(?:and|&)\s*time)?|schedule))?"),
    ("questions_due", r"(?:(?:questions?|rfis?|inquiries)\s+(?:are\s+)?(?:due(?:\s+by)?|deadline|cutoff)|(?:deadline|cutoff)\s+for\s+(?:questions?|rfis?|inquiries))"),
    ("bid_due", r"(?:(?:bids?|proposals?|quotes?|responses?)(?:\s+submission)?\s+(?:are\s+)?(?:due(?:\s+(?:date|by))?|deadline|cutoff|closing(?:\s+(?:date|time))?|must\s+be\s+received\s+by)|(?:submission\s+)?deadline\s+(?:for\s+)?(?:bids?|proposals?|quotes?|responses?))"),
)
EVENTS = tuple((name, re.compile(rf"^(?P<label>{pattern})(?=$|[\s:\-–—])(?:\s*[:\-–—]\s*|\s+)?(?:{REVISION})?(?P<tail>.*)$", re.I))
               for name, pattern in EVENTS)
SCOPE_HEADER = re.compile(r"^scope\s+of\s+work(?:\s*[:\-–—]\s*|\s*$)(?P<body>.*)$", re.I)
NUMBERED_HEADER = re.compile(r"^\s*(?:section\s+)?\d+(?:\.\d+)*[.)]\s+", re.I)
PRICING_SHEET = re.compile(r"\b(?:signed\s+)?(?:(?:bid|unit)\s+)?pric(?:ing|e)\s+(?:sheet|schedule)\b", re.I)
REQUIREMENT = re.compile(r"\b(?:must|shall|required|submit|include|provide|attach|complete|sign)\b", re.I)
SINGLE_FIELDS = ("bid_due", "questions_due", "job_walk", "walk_registration", "submission_method")
OVERVIEW_FIELDS = ("scope", "bid_due", "job_walk", "walk_registration", "questions_due", "submission_method",
                   "license", "eligibility", "form_required", "doc_required")
# These may guide real bid decisions. Quoted text alone does not validate an Ollama value.
RULE_ONLY_FIELDS = frozenset(SINGLE_FIELDS + ("scope", "form_required"))
MODEL_SUPPORTING_FIELDS = frozenset(("license", "eligibility", "doc_required"))
RETIRED = "History only; not current First Review evidence."
EQUIVALENT = "Equivalent current finding; see the applicable source citation."
METHOD_CHANNEL = r"(?:electronic(?:ally)?|online|(?:the\s+)?(?:[\w-]+\s+){0,3}portal|planetbids|bidnet|e-?mail|mail|hand(?:\s+delivery)?|in\s+person)"
METHOD = re.compile(
    rf"\b(?:submit(?:ted)?|deliver(?:ed)?|send|file)\b[^.;]{{0,100}}?\b(?:via|through|using|by|in|to)\s+{METHOD_CHANNEL}\b"
    rf"|\b(?:submit(?:ted)?|deliver(?:ed)?|send|file)\b[^.;]{{0,65}}?\b(?:electronically|online|in\s+person)\b"
    r"|\b(?:sealed\s+envelope|hand[- ]delivered)\b", re.I)
SUPPORT_EVIDENCE = {
    "license": re.compile(r"\blicen[sc]e\b", re.I),
    "eligibility": re.compile(r"\b(?:eligib\w+|qualif\w+|experience|registration|certified|certification|prevailing wage)\b", re.I),
    "doc_required": re.compile(r"\b(?:certificate|insurance|references?|bond|authorization|affidavit|statement|letter|proof)\b", re.I),
}
LABELS = {
    "scope": "Scope of work", "bid_due": "Bid due", "questions_due": "Questions deadline",
    "job_walk": "Job walk", "walk_registration": "Job walk registration cutoff",
    "submission_method": "Submission method", "license": "License requirement",
    "eligibility": "Eligibility requirement", "bid_item": "Bid item", "bid_item_delete": "Bid item deleted",
    "form_required": "Form to fill out", "doc_required": "Document to gather", "addendum_ref": "Addendum referenced",
}
DOC_KEYWORDS = [
    ("bid bond", "Bid bond"), ("performance bond", "Performance & payment bonds"),
    ("insurance", "Certificate of insurance"), ("reference", "Project references"),
    ("manufacturer", "Manufacturer authorization letter"), ("certif", "Certifications"),
    ("dir registration", "DIR registration"), ("department of industrial relations", "DIR registration"),
    ("license", "Contractor license copy"),
]
ITEM_RE = re.compile(
    r"^\s*(ADD\s+)?(?:(?:BID\s+)?ITEM|(ADDITIVE\s+|DEDUCTIVE\s+)?(ALTERNATE|OPTION))\s+(?:NO\.?\s*)?([A-Z0-9]+)"
    r"\s*[:\-\u2013]\s*(.+?)\s*\|\s*([\d,\.]+)\s*\|\s*([A-Za-z]+)\s*$", re.I)
DELETE_RE = re.compile(r"^\s*DELETE\s+(?:BID\s+)?(ITEM|ALTERNATE|OPTION)\s+(?:NO\.?\s*)?([A-Z0-9]+)", re.I)
FORM_RE = re.compile(r"\bForm\s+([A-Z0-9][\w\-]*)\s*[\-\u2013:]\s*([^.\n|]{3,80})")


def parse_dt(date_s, time_s):
    date_s = re.sub(r"\bSept\b", "Sep", re.sub(r"[,.]", " ", date_s), flags=re.I)
    date_s = re.sub(r"\s+", " ", date_s).strip()
    for fmt in ("%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(date_s, fmt)
            break
        except ValueError:
            continue
    else:
        return None
    if not time_s:
        return d
    t = re.sub(r"[.\s]", "", time_s).upper()
    if t in ("NOON", "MIDNIGHT"):
        return d.replace(hour=12 if t == "NOON" else 0)
    try:
        tt = datetime.strptime(t, "%I:%M%p" if ":" in t else "%I%p")
        return d.replace(hour=tt.hour, minute=tt.minute)
    except ValueError:
        return None


def sentences(text):
    for line in text.splitlines():
        for s in re.split(r"(?<=[.;])\s+(?=[A-Z])", line):
            s = s.strip()
            if s:
                yield s


def display_date(date_s, time_s, zone_s):
    d = parse_dt(date_s, time_s)
    if not d:
        return None
    zone = re.sub(r"\s+", " ", (zone_s or "").strip()).lower()
    named = {"pacific": "PT", "pacific time": "PT", "pacific standard": "PST",
             "pacific standard time": "PST", "pacific daylight": "PDT", "pacific daylight time": "PDT",
             "mountain": "MT", "mountain time": "MT", "central": "CT", "central time": "CT",
             "eastern": "ET", "eastern time": "ET", "local time": "local time"}
    tz = named.get(zone, zone.upper()) if zone else "(time zone not stated)"
    clock = d.strftime("%Y-%m-%d %H:%M") if time_s else d.strftime("%Y-%m-%d") + " (time not stated)"
    return clock + " " + tz


def clean_heading(line):
    return re.sub(r"^\s*(?:section\s+)?\d+(?:\.\d+)*[.)]\s+", "", line, flags=re.I).strip()


def event_findings(lines):
    for i, line in enumerate(lines):
        heading = clean_heading(line)
        for field, event in EVENTS:
            m = event.fullmatch(heading)
            if not m:
                continue
            tail = m["tail"].strip()
            # No free-text or column-header search: date must be a complete value directly under,
            # or on the same line as, a single recognized event label.
            last = i
            if not tail and i + 1 < len(lines):
                tail, last = lines[i + 1], i + 1
            date = DATE_BLOCK.fullmatch(tail)
            if not date:
                break
            clock, zone = date["clock"], date["zone"]
            if not clock and last + 1 < len(lines):
                time = TIME_BLOCK.fullmatch(lines[last + 1])
                if time:
                    if zone and time["zone"] and normalized(zone) != normalized(time["zone"]):
                        break
                    clock, zone = time["clock"], time["zone"] or zone
                    last += 1
            if not zone and last + 1 < len(lines):
                time_zone = ZONE_BLOCK.fullmatch(lines[last + 1])
                if time_zone:
                    zone, last = time_zone["zone"], last + 1
            # An immediately adjacent bare date or unsupported time is ambiguous; do not pick one
            # or suggest a date-only result when an unreadable/competing value is evident.
            if last + 1 < len(lines) and (DATE_BLOCK.fullmatch(lines[last + 1])
                    or TIME_BLOCK.fullmatch(lines[last + 1])
                    or (not clock and re.match(r"^(?:at\s+)?\d{1,2}:\d{2}\b", lines[last + 1], re.I))):
                break
            stated_day = date["weekday"].strip(" .,").lower()[:3]
            parsed = parse_dt(date["date"], clock)
            if not parsed or stated_day and stated_day != parsed.strftime("%a").lower():
                break
            value = display_date(date["date"], clock, zone)
            if value:
                if field == "job_walk":
                    label = m["label"].lower()
                    qualifier = ("MANDATORY " if re.search(r"\b(?:mandatory|required)\b", label)
                                 else "Optional " if "optional" in label else "Attendance not stated: ")
                    value = qualifier + value
                yield field, value, "\n".join(lines[i:last+1])
            break


def scope_findings(lines):
    for i, line in enumerate(lines):
        m = SCOPE_HEADER.fullmatch(clean_heading(line))
        if not m:
            continue
        body = m["body"].strip()
        if len(body) > 15:
            yield "scope", body, line
            continue
        for j in range(i + 1, min(len(lines), i + 7)):
            text = lines[j]
            if (not text or NUMBERED_HEADER.match(text) or text.endswith(":")
                    or (text.isupper() and len(text) > 4) or DATE_BLOCK.fullmatch(text)
                    or any(e.fullmatch(clean_heading(text)) for _, e in EVENTS)
                    or re.match(r"^(?:bidder|bid response|contractor)\s+(?:must|shall)|^(?:include|submit|provide)\s+.*\b(?:form|sheet|bond|insurance)\b", text, re.I)):
                break
            if len(text) >= 14:
                yield "scope", text, "\n".join(lines[i:j+1]) if j == i+1 else text


def rule_findings(page_text):
    """Yields (field, value, snippet) found in one page. Only what is literally in the text."""
    lines = [line.strip() for line in page_text.splitlines()]
    yield from event_findings(lines)
    yield from scope_findings(lines)
    for s in sentences(page_text):
        low = s.lower()
        m = ITEM_RE.match(s)
        if m:
            opt = bool(m.group(3))
            key = (f"ALT-{m.group(4)}" if opt else m.group(4)).upper()
            yield "bid_item", f"{key}|{m.group(5).strip()}|{m.group(6).replace(',', '')}|{m.group(7)}|{int(opt)}", s
            continue
        m = DELETE_RE.match(s)
        if m:
            key = m.group(2).upper() if m.group(1).upper() == "ITEM" else f"ALT-{m.group(2).upper()}"
            yield "bid_item_delete", key, s
            continue
        if METHOD.search(s) and not DATE_RE.search(s) and not re.search(r"\b(?:not|don't|do not)\b", s, re.I):
            yield "submission_method", s, s
        if PRICING_SHEET.search(s) and REQUIREMENT.search(s) and re.search(
                r"\b(?:sign(?:ed)?|signature)\b", s, re.I) and not re.search(r"\b(?:optional|not required|do not)\b", s, re.I):
            yield "form_required", "Completed, signed pricing sheet" if re.search(r"\bcomplet", s, re.I) else "Signed pricing sheet", s
        if "licen" in low and re.search(r"\bclass\s+[ab]\b|\bc-\d{1,2}\b|\b[ab]\s+license", low):
            yield "license", s, s
        if re.search(r"\bdir\b|industrial relations|\bsbe\b|\bdvbe\b|prevailing wage|years? of experience", low):
            yield "eligibility", s, s
        for fm in FORM_RE.finditer(s):
            yield "form_required", f"Form {fm.group(1)} \u2013 {fm.group(2).strip()}", s
        if re.search(r"\b(submit|include|provide|attach|required|must)\b", low):
            for kw, name in DOC_KEYWORDS:
                if kw in low and not FORM_RE.search(s):
                    yield "doc_required", name, s
                    break
        for am in re.finditer(r"addend(?:um|a)\s+(?:no\.?\s*)?(\d+)", low):
            yield "addendum_ref", am.group(1), s


def precedence(doc):
    return (doc["addendum_no"] or 0) if doc["kind"] == "addendum" else 0


def normalized(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


def model_finding(pages, candidate, deterministic, seen):
    """Allow only non-operational supporting drafts with an exact local source quote."""
    if not isinstance(candidate, dict):
        return None
    f = candidate.get("field")
    page_key = candidate.get("doc_id"), candidate.get("page")
    quote = str(candidate.get("snippet") or "")
    value = str(candidate.get("value") or "")
    q = normalized(quote)
    if (not isinstance(f, str) or f in RULE_ONLY_FIELDS or f not in MODEL_SUPPORTING_FIELDS
            or not all(type(n) is int for n in page_key) or page_key not in pages
            or not 12 <= len(q) <= 300 or not normalized(value) or q not in normalized(pages[page_key])
            or not SUPPORT_EVIDENCE[f].search(quote)
            or f == "doc_required" and not REQUIREMENT.search(quote)):
        return None
    if PRICING_SHEET.search(quote) and f == "doc_required":
        return None
    # Store only literal evidence as the draft's value; the model selects a supporting quote,
    # never writes the text users may approve.
    v = q.rstrip(".")
    key = (f, v)
    quote_key = (f, q)
    if key in seen or quote_key in seen:
        return None
    # A differently worded interpretation of the same rule evidence is not a new requirement.
    if any(f == r[0] and (v == normalized(r[1]).rstrip(".")
            or r[2:4] == page_key and (q in normalized(r[4]) or normalized(r[4]) in q))
           for r in deterministic):
        return None
    seen.update((key, quote_key))
    return f, quote.strip(), *page_key, quote, "ollama"


def run_first_review(p, lead_id, extra_findings=None):
    """Reconcile current evidence with stable stored provenance and human statuses."""
    old = p.q("SELECT * FROM findings WHERE lead_id=? ORDER BY id", (lead_id,))
    prior = {}
    for r in old:
        if r["source"] != "manual":
            key = (r["source"], r["field"], r["value"], r["doc_id"], r["page"], normalized(r["snippet"]))
            prior.setdefault(key, r)
    docs = {d["id"]: d for d in p.q("SELECT * FROM documents WHERE lead_id=? ORDER BY id", (lead_id,))}
    pages = {(r["doc_id"], r["page"]): r["text"] for r in p.q(
        "SELECT dp.* FROM doc_pages dp JOIN documents d ON d.id=dp.doc_id WHERE d.lead_id=? "
        "AND d.kind IN ('solicitation','addendum','other') ORDER BY dp.doc_id,dp.page", (lead_id,))}
    deterministic, exact = [], set()
    for (doc_id, page), txt in pages.items():
        for field, value, snip in rule_findings(txt):
            k = field, value, doc_id, page
            if k not in exact:
                exact.add(k)
                deterministic.append((*k, snip[:400], "rule"))
    # None is a UI status refresh, not a new model run. An explicit [] retires past model
    # drafts after an offline/empty run. Never reinstate disallowed legacy model rows.
    if extra_findings is None:
        extra_findings = [dict(r) for r in old if r["source"] == "ollama" and r["note"] != RETIRED]
    seen = set()
    candidates = deterministic + [accepted for f in extra_findings
                                  if (accepted := model_finding(pages, f, deterministic, seen))]
    current = set()
    for field, value, doc, page, text, source in candidates:
        key = (source, field, value, doc, page, normalized(text))
        before = prior.get(key)
        if before:
            status = "draft" if before["status"] == "conflict" else before["status"]
            p.x("UPDATE findings SET applicable=1,note=CASE WHEN status='rejected' THEN note ELSE NULL END,status=? WHERE id=?", (status, before["id"]))
            current.add(before["id"])
        else:
            current.add(p.x("INSERT INTO findings(lead_id,field,value,doc_id,page,snippet,source,status) "
                            "VALUES(?,?,?,?,?,?,?,?)", (lead_id, field, value, doc, page, text, source, "draft")))
    for r in old:
        if r["source"] == "manual":
            p.x("UPDATE findings SET applicable=1,note=CASE WHEN status='rejected' THEN note ELSE NULL END WHERE id=?", (r["id"],))
        elif r["id"] not in current and (r["applicable"] or r["note"] != RETIRED):
            p.x("UPDATE findings SET applicable=0,note=? WHERE id=?", (RETIRED, r["id"]))
    _apply_precedence(p, lead_id, docs)
    _sync_bid_items(p, lead_id)
    return overview(p, lead_id)


def _apply_precedence(p, lead_id, docs):
    rows = p.q("SELECT * FROM findings WHERE lead_id=? AND applicable=1", (lead_id,))
    for field in SINGLE_FIELDS:
        group = [r for r in rows if r["field"] == field]
        if not group:
            continue
        top = max(precedence(docs.get(r["doc_id"], {"kind": "", "addendum_no": 0})) for r in group)
        winners = [r for r in group if r["status"] != "rejected"
                   and precedence(docs.get(r["doc_id"], {"kind": "", "addendum_no": 0})) == top]
        # Identical dates/methods on repeated pages are one active candidate. Prefer human
        # verification at this same addendum level while retaining other citations as history.
        unique, duplicates = {}, set()
        for w in sorted(winners, key=lambda w: (w["status"] != "verified", w["source"] != "manual", w["id"])):
            k = normalized(w["value"])
            if k in unique:
                duplicates.add(w["id"])
                p.x("UPDATE findings SET applicable=0,note=? WHERE id=?",
                    (EQUIVALENT, w["id"]))
            else:
                unique[k] = w
        win_ids = {w["id"] for w in winners}
        for r in group:
            if r["status"] == "rejected":
                p.x("UPDATE findings SET applicable=0 WHERE id=?", (r["id"],))
            elif r["id"] not in win_ids:
                p.x("UPDATE findings SET applicable=0, note=? WHERE id=?", (f"Superseded by Addendum {top}", r["id"]))
            elif top and r["id"] not in duplicates:
                p.x("UPDATE findings SET note=? WHERE id=?", (f"Changed by Addendum {top}", r["id"]))
        if len(unique) > 1:
            for w in unique.values():
                if w["status"] != "verified":
                    p.x("UPDATE findings SET status='conflict' WHERE id=?", (w["id"],))
    items = {}
    for r in sorted([r for r in rows if r["status"] != "rejected" and r["field"] in ("bid_item", "bid_item_delete")],
                    key=lambda r: precedence(docs[r["doc_id"]])):
        key = r["value"].split("|")[0]
        if key in items:
            p.x("UPDATE findings SET applicable=0, note=? WHERE id=?",
                (f"Replaced by Addendum {precedence(docs[r['doc_id']])}", items[key]["id"]))
        items[key] = r
        if r["field"] == "bid_item_delete":
            p.x("UPDATE findings SET applicable=0 WHERE id=?", (r["id"],))


def resolve_conflict(p, finding_id):
    f = p.one("SELECT * FROM findings WHERE id=? AND applicable=1 AND status!='rejected'", (finding_id,))
    if not f or f["field"] not in SINGLE_FIELDS or not has_conflict(p, f["lead_id"], f["field"]):
        return
    peers = p.q("SELECT id,value,applicable,note FROM findings WHERE lead_id=? AND field=? AND id!=?",
                (f["lead_id"], f["field"], finding_id))
    rejected = {normalized(r["value"]) for r in peers if r["applicable"]}
    for r in peers:
        if (r["applicable"] or r["note"] == EQUIVALENT) and normalized(r["value"]) in rejected:
            p.x("UPDATE findings SET status='rejected',note='Not chosen by user' WHERE id=?", (r["id"],))
    p.x("UPDATE findings SET status='verified' WHERE id=?", (finding_id,))


def has_conflict(p, lead_id, field):
    if field not in SINGLE_FIELDS:
        return False
    return bool(p.one("SELECT 1 FROM findings WHERE lead_id=? AND field=? AND applicable=1 "
                      "AND status!='rejected' GROUP BY field HAVING COUNT(DISTINCT lower(value)) > 1",
                      (lead_id, field)))


def set_finding_status(p, finding_id, status):
    if status not in ("verified", "rejected"):
        return
    p.x("UPDATE findings SET status=? WHERE id=? AND applicable=1", (status, finding_id))


def verify_all_drafts(p, lead_id):
    p.x("UPDATE findings SET status='verified' WHERE lead_id=? AND status='draft' AND applicable=1", (lead_id,))


def add_manual_finding(p, lead_id, field, value, doc_id, page, snippet):
    return p.x("INSERT INTO findings(lead_id,field,value,doc_id,page,snippet,source,status) VALUES(?,?,?,?,?,?,?,?)",
               (lead_id, field, value, doc_id, page, snippet, "manual", "verified"))


def applicable(p, lead_id, field, verified_only=False):
    sql = "SELECT f.*, d.filename, d.kind, d.addendum_no FROM findings f LEFT JOIN documents d ON d.id=f.doc_id " \
          "WHERE f.lead_id=? AND f.field=? AND f.applicable=1 AND f.status!='rejected'"
    if verified_only:
        if has_conflict(p, lead_id, field):
            return []
        sql += " AND f.status='verified'"
    return p.q(sql + " ORDER BY f.id", (lead_id, field))


def _sync_bid_items(p, lead_id):
    """Bid schedule required by the applicable documents. Keeps prices the user already entered."""
    wanted = {}
    for f in applicable(p, lead_id, "bid_item"):
        no, desc, qty, unit, opt = f["value"].split("|")
        wanted[no] = (desc, float(qty), unit, int(opt), f["id"])
    for no, (desc, qty, unit, opt, fid) in wanted.items():
        if p.one("SELECT id FROM bid_items WHERE lead_id=? AND item_no=?", (lead_id, no)):
            p.x("UPDATE bid_items SET description=?, qty=?, unit=?, is_option=?, finding_id=? WHERE lead_id=? AND item_no=?",
                (desc, qty, unit, opt, fid, lead_id, no))
        else:
            p.x("INSERT INTO bid_items(lead_id,item_no,description,is_option,qty,unit,finding_id) VALUES(?,?,?,?,?,?,?)",
                (lead_id, no, desc, opt, qty, unit, fid))
    for r in p.q("SELECT id,item_no FROM bid_items WHERE lead_id=? AND finding_id IS NOT NULL", (lead_id,)):
        if r["item_no"] not in wanted:
            p.x("DELETE FROM bid_items WHERE id=?", (r["id"],))


def cite(f):
    if not f["doc_id"]:
        return "manual entry"
    label = f"Addendum {f['addendum_no']}" if f["kind"] == "addendum" else f["filename"]
    return f"{label}, p.{f['page']}"


def flags(p, lead_id):
    out = []
    docs = p.q("SELECT * FROM documents WHERE lead_id=?", (lead_id,))
    if not any(d["kind"] == "solicitation" for d in docs):
        out.append(("missing", "No solicitation document attached."))
    have = {d["addendum_no"] for d in docs if d["kind"] == "addendum"}
    refs = {int(f["value"]) for f in p.q("SELECT value FROM findings WHERE lead_id=? AND field='addendum_ref'", (lead_id,))}
    for n in sorted(refs - have):
        out.append(("missing", f"Addendum {n} is referenced but not attached."))
    for d in docs:
        if d["text_status"] in ("spreadsheet", "scan", "unsupported") and not d["reviewed"]:
            out.append(("unreviewed", f"{d['filename']} is a {d['text_status']} and has not been reviewed. Open it and mark it reviewed."))
    for field in SINGLE_FIELDS:
        if has_conflict(p, lead_id, field):
            c = applicable(p, lead_id, field)
            out.append(("conflict", f"Conflicting {LABELS[field].lower()}: " + " vs ".join(sorted({r['value'] for r in c})) + ". Choose one."))
    for f in (row for field in ("bid_due", "job_walk", "questions_due", "walk_registration") for row in applicable(p, lead_id, field)):
        if "time zone not stated" in f["value"]:
            out.append(("check", f"{LABELS[f['field']]} has no time zone in the source ({cite(f)})."))
        if "time not stated" in f["value"]:
            out.append(("check", f"{LABELS[f['field']]} has no time in the source ({cite(f)})."))
        if "Attendance not stated" in f["value"]:
            out.append(("check", f"The source does not state whether the job walk is mandatory ({cite(f)})."))
    for field in ("scope", "bid_due", "submission_method", "license"):
        if not applicable(p, lead_id, field):
            out.append(("not_found", f"{LABELS[field]} not found in the documents. Check manually; nothing was assumed."))
    return out


def next_decision(p, lead_id, fl=None):
    fl = fl if fl is not None else flags(p, lead_id)
    for kind in ("missing", "conflict", "unreviewed"):
        hit = [m for k, m in fl if k == kind]
        if hit:
            return hit[0]
    drafts = p.one("SELECT COUNT(*) c FROM findings WHERE lead_id=? AND status='draft' AND applicable=1", (lead_id,))["c"]
    if drafts:
        return f"Verify {drafts} draft finding(s) against the cited pages."
    titles = {t["title"] for t in p.q("SELECT title FROM tasks WHERE lead_id=?", (lead_id,))}
    walk = applicable(p, lead_id, "job_walk", True)
    if walk and walk[0]["value"].startswith("MANDATORY") and "Attend job walk" not in titles:
        reg = applicable(p, lead_id, "walk_registration", True)
        return f"Decide: attend the mandatory job walk {walk[0]['value'][10:]}" + (
            f" (register by {reg[0]['value']})" if reg else "") + " (save the 'Attend job walk' task), or drop the bid."
    if not titles:
        return "Approve the suggested tasks."
    blank = p.one("SELECT COUNT(*) c FROM bid_items WHERE lead_id=? AND (unit_price IS NULL OR unit_price=0)", (lead_id,))["c"]
    if blank:
        return f"Price {blank} blank line(s) on the bid sheet."
    open_items = p.one("SELECT COUNT(*) c FROM checklist WHERE lead_id=? AND status='open' AND name!='Bid price sheet'", (lead_id,))["c"]
    if open_items:
        return f"Complete {open_items} open checklist item(s)."
    pkg = p.one("SELECT status, report FROM packages WHERE lead_id=? ORDER BY id DESC", (lead_id,))
    if not pkg:
        return "Generate the draft package."
    if pkg["status"] != "ready_for_review":
        import json
        n = sum(1 for r in json.loads(pkg["report"])["results"] if r["status"] == "fail")
        return f"Fix {n} open package item(s), then regenerate."
    due = applicable(p, lead_id, "bid_due", True)
    return "Package ready: review, sign, and submit it yourself" + (f" before {due[0]['value']}." if due else ".")


def pretty(f):
    if f["field"] == "bid_item":
        no, desc, qty, unit, opt = f["value"].split("|")
        return f"{no} - {desc} - {qty} {unit}" + (" (option)" if opt == "1" else "")
    return f["value"]


def overview(p, lead_id):
    data = {k: [dict(r) | {"cite": cite(r)} for r in applicable(p, lead_id, k)]
            for k in OVERVIEW_FIELDS}
    fl = flags(p, lead_id)
    data["flags"] = fl
    data["next"] = next_decision(p, lead_id, fl)
    return data

