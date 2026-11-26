from datetime import datetime, timedelta

from .review import applicable, cite

COST_CATS = ("labor", "material", "equipment", "quote")
TEXT_CATS = ("scope", "assumption", "exclusion")


def _dt(value):
    if "not stated" in value or value.lower().endswith("local time"):
        return None
    try:
        return datetime.strptime(value.replace("MANDATORY ", "").replace("Optional ", "")[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def suggest_checklist(p, lead_id):
    """Suggestions from verified, applicable findings. Nothing is saved until the user approves."""
    out = [dict(category="form", name="Bid price sheet", needs_signature=1, finding_id=None, cite="BidDesk bid schedule")]
    for field, cat, sig in (("form_required", "form", 1), ("doc_required", "document", 0)):
        for f in applicable(p, lead_id, field, verified_only=True):
            out.append(dict(category=cat, name=f["value"], needs_signature=sig, finding_id=f["id"], cite=cite(f)))
    saved = {(r["category"], r["name"]) for r in checklist(p, lead_id)}
    uniq, seen = [], set()
    for s in out:
        k = (s["category"], s["name"])
        if k not in seen and k not in saved:
            seen.add(k)
            uniq.append(s)
    return uniq


def save_checklist_item(p, lead_id, category, name, needs_signature=0, finding_id=None, required=1):
    p.x("INSERT OR IGNORE INTO checklist(lead_id,category,name,needs_signature,finding_id,required) VALUES(?,?,?,?,?,?)",
        (lead_id, category, name, needs_signature, finding_id, required))
    return p.one("SELECT id FROM checklist WHERE lead_id=? AND category=? AND name=?", (lead_id, category, name))["id"]


def checklist(p, lead_id):
    return p.q("SELECT * FROM checklist WHERE lead_id=? ORDER BY category DESC, id", (lead_id,))


def set_checklist_file(p, item_id, path):
    """Attach the completed form / gathered document (copied to working/, original untouched)."""
    from pathlib import Path
    import shutil
    item = p.one("SELECT * FROM checklist WHERE id=?", (item_id,))
    dest = p.root / "working" / str(item["lead_id"]) / f"{item_id}_{Path(path).name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    p.x("UPDATE checklist SET file_path=?, status='done' WHERE id=?", (str(dest.relative_to(p.root)), item_id))


def set_checklist_status(p, item_id, status):
    p.x("UPDATE checklist SET status=? WHERE id=?", (status, item_id))


def suggest_tasks(p, lead_id):
    out = []
    due = applicable(p, lead_id, "bid_due", True)
    due_dt = _dt(due[0]["value"]) if due else None
    q = applicable(p, lead_id, "questions_due", True)
    if q and _dt(q[0]["value"]):
        out.append(("Send RFIs / questions", _dt(q[0]["value"]) - timedelta(days=2), q[0]))
    reg = applicable(p, lead_id, "walk_registration", True)
    if reg and _dt(reg[0]["value"]):
        out.append(("Register for job walk", _dt(reg[0]["value"]) - timedelta(days=1), reg[0]))
    walk = applicable(p, lead_id, "job_walk", True)
    if walk and _dt(walk[0]["value"]):
        out.append(("Attend job walk", _dt(walk[0]["value"]), walk[0]))
    if due_dt:
        out += [("Request sub / supplier quotes", due_dt - timedelta(days=7), due[0]),
                ("Gather licenses, insurance, bonds", due_dt - timedelta(days=5), due[0]),
                ("Final pricing", due_dt - timedelta(days=3), due[0]),
                ("Review and sign package", due_dt - timedelta(days=2), due[0]),
                ("Submit bid (you)", due_dt - timedelta(days=1), due[0])]
        if due_dt and any(t[1] > due_dt for t in out):
            out = [(t, min(d, due_dt - timedelta(hours=4)), f) for t, d, f in out]
    saved = {r["title"] for r in tasks(p, lead_id)}
    return [dict(title=t, due_date=d.strftime("%Y-%m-%d"), finding_id=f["id"], cite=cite(f))
            for t, d, f in out if t not in saved]


def save_task(p, lead_id, title, due_date, finding_id=None):
    p.x("INSERT OR IGNORE INTO tasks(lead_id,title,due_date,finding_id) VALUES(?,?,?,?)", (lead_id, title, due_date, finding_id))


def tasks(p, lead_id=None):
    if lead_id:
        return p.q("SELECT * FROM tasks WHERE lead_id=? ORDER BY due_date", (lead_id,))
    return p.q("SELECT t.*, l.title lead_title FROM tasks t JOIN leads l ON l.id=t.lead_id "
               "WHERE t.done=0 AND l.stage='pipeline' ORDER BY t.due_date")


def calendar_events(p):
    """Confirmed (verified) job walks and submission deadlines for bids in progress. Local only."""
    out = []
    for lead in p.q("SELECT * FROM leads WHERE stage='pipeline'"):
        for field, label in (("job_walk", "Job walk"), ("bid_due", "Bid due")):
            for f in applicable(p, lead["id"], field, True):
                d = _dt(f["value"])
                if d:
                    out.append(dict(when=d, label=label, lead_id=lead["id"], title=lead["title"], value=f["value"]))
    return sorted(out, key=lambda e: e["when"])


# ---- estimate (internal) ----
def add_estimate_line(p, lead_id, category, description, qty=0, unit="", unit_cost=0):
    assert category in COST_CATS + TEXT_CATS
    return p.x("INSERT INTO estimate_lines(lead_id,category,description,qty,unit,unit_cost) VALUES(?,?,?,?,?,?)",
               (lead_id, category, description, qty, unit, unit_cost))


def estimate_lines(p, lead_id):
    return p.q("SELECT * FROM estimate_lines WHERE lead_id=? ORDER BY category, id", (lead_id,))


def markup(p, lead_id):
    r = p.one("SELECT markup_pct FROM lead_meta WHERE lead_id=?", (lead_id,))
    return r["markup_pct"] if r else 10.0


def set_markup(p, lead_id, pct):
    p.x("INSERT OR REPLACE INTO lead_meta(lead_id, markup_pct) VALUES(?,?)", (lead_id, pct))


def estimate_summary(p, lead_id):
    lines = estimate_lines(p, lead_id)
    cost = sum((l["qty"] or 0) * (l["unit_cost"] or 0) for l in lines if l["category"] in COST_CATS)
    m = markup(p, lead_id)
    base = sum((b["qty"] or 0) * (b["unit_price"] or 0) for b in bid_items(p, lead_id) if not b["is_option"])
    return dict(cost=cost, markup_pct=m, target=round(cost * (1 + m / 100), 2), bid_base_total=round(base, 2))


def bid_items(p, lead_id):
    return p.q("SELECT * FROM bid_items WHERE lead_id=? ORDER BY is_option, CAST(item_no AS INTEGER), item_no", (lead_id,))


def set_unit_price(p, item_id, price):
    p.x("UPDATE bid_items SET unit_price=? WHERE id=?", (price, item_id))


