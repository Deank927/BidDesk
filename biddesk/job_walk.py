"""Structured manual job-walk finding; no network or external calendar actions."""
import json
import re
from datetime import date, time

ATTENDANCE = ("Not stated", "Mandatory", "Optional")
REQUIREMENT = ("Not stated", "Required", "Not required")
ZONES = ("Not stated", "Pacific (PT)", "Mountain (MT)", "Central (CT)", "Eastern (ET)", "UTC")
TZ = dict(zip(ZONES, ("", "PT", "MT", "CT", "ET", "UTC")))
FIELDS = {"attendance": 20, "walk_date": 10, "walk_time": 5, "zone": 20, "address": 240,
          "rsvp": 20, "waiver": 20, "cutoff_date": 10, "cutoff_time": 5, "cutoff_zone": 20,
          "instructions": 500, "evidence": 750, "bid_due_date": 10, "bid_due_time": 5, "bid_due_zone": 20}


def validate(data):
    d = {key: str(data.get(key) or "").strip() for key in FIELDS}
    if any(len(d[k]) > FIELDS[k] for k in d):
        raise ValueError("A field is over its length limit.")
    if d["attendance"] not in ATTENDANCE or d["rsvp"] not in REQUIREMENT or d["waiver"] not in REQUIREMENT:
        raise ValueError("Choose the source-stated attendance, RSVP and waiver status.")
    for field in ("walk_date", "cutoff_date", "bid_due_date"):
        v = d[field]
        if not v and field != "walk_date":
            continue
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", v):
            raise ValueError("Enter dates in YYYY-MM-DD format.")
        try:
            date.fromisoformat(v)
        except ValueError as e:
            raise ValueError("Enter a valid calendar date as YYYY-MM-DD.") from e
    for field in ("walk_time", "cutoff_time", "bid_due_time"):
        v = d[field]
        if not v:
            continue
        try:
            if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", v):
                raise ValueError("format")
            time.fromisoformat(v)
        except ValueError as e:
            raise ValueError("Enter a valid time in 24-hour HH:MM, or leave it blank if unstated.") from e
    if d["cutoff_time"] and not d["cutoff_date"]:
        raise ValueError("A cutoff time requires a cutoff date. Leave both blank if not stated.")
    if d["cutoff_zone"] not in TZ or d["zone"] not in TZ or d["bid_due_zone"] not in TZ:
        raise ValueError("Select the stated time zones, or leave them as Not stated.")
    if d["cutoff_zone"] != ZONES[0] and not d["cutoff_time"]:
        raise ValueError("Do not choose a cutoff time zone when the time is not stated.")
    if d["bid_due_time"] and not d["bid_due_date"]:
        raise ValueError("A bid due time requires a bid due date.")
    if d["bid_due_zone"] != ZONES[0] and not d["bid_due_time"]:
        raise ValueError("Do not choose a bid due time zone when the time is not stated.")
    if not d["address"] and not d["evidence"]:
        raise ValueError("Enter the address or explain that the notice does not give one in the evidence note.")
    return d


def finding_value(d):
    prefix = {"Mandatory": "MANDATORY ", "Optional": "Optional ",
              "Not stated": "Attendance not stated: "}[d["attendance"]]
    return (prefix + d["walk_date"] + " " + (d["walk_time"] or "(time not stated)") + " "
            + (TZ[d["zone"]] or "(time zone not stated)"))


def read(p, finding_id):
    row = p.one("SELECT data_json FROM manual_job_walks WHERE finding_id=?", (finding_id,))
    return json.loads(row[0]) if row else {}


def save(p, lead_id, data, doc_id=None, page=None, existing=None):
    d = validate(data)
    if not p.one("SELECT 1 FROM leads WHERE id=?", (lead_id,)):
        raise ValueError("This bid is no longer available.")
    if doc_id is not None:
        row = p.one("SELECT pages FROM documents WHERE lead_id=? AND id=?", (lead_id, doc_id))
        if row is None or type(page) is not int or not 1 <= page <= row["pages"]:
            raise ValueError("Choose an attached source on this bid and a valid page number.")
    else:
        if not d["evidence"]:
            raise ValueError("Enter the notice source or quote in the evidence box if there is no attached document.")
        page = None
    value = finding_value(d)
    evidence = d["evidence"] or "Manually checked against the selected source and page."
    with p.conn:
        if existing is not None:
            cur = p.conn.execute("UPDATE findings SET value=?,doc_id=?,page=?,snippet=?,status='verified',"
                                 "applicable=1,note=NULL WHERE id=? AND lead_id=? AND field='job_walk' AND source='manual'",
                                 (value, doc_id, page, evidence, existing, lead_id))
            if cur.rowcount != 1:
                raise ValueError("The job walk you chose is no longer available on this bid.")
            ident = existing
        else:
            cur = p.conn.execute("INSERT INTO findings(lead_id,field,value,doc_id,page,snippet,source,status) "
                                 "VALUES(?,'job_walk',?,?,?,?,'manual','verified')",
                                 (lead_id, value, doc_id, page, evidence))
            ident = cur.lastrowid
        p.conn.execute("INSERT INTO manual_job_walks(finding_id,data_json) VALUES(?,?) "
                       "ON CONFLICT(finding_id) DO UPDATE SET data_json=excluded.data_json",
                       (ident, json.dumps(d)))
    return ident


def summary(d):
    if not d:
        return ""
    cutoff = d["cutoff_date"] or "Not stated"
    if d["cutoff_date"]:
        if d["cutoff_time"]:
            cutoff += " " + d["cutoff_time"] + " " + (TZ[d["cutoff_zone"]] or "(time zone not stated)")
        else:
            cutoff += " (time not stated)"
    fields = ["Address: " + (d["address"] or "Not stated"), "RSVP: " + d["rsvp"],
              "Waiver/release: " + d["waiver"], "RSVP/waiver cutoff: " + cutoff]
    if d.get("bid_due_date"):
        due = d["bid_due_date"] + " " + (d.get("bid_due_time") or "(time not stated)")
        if d.get("bid_due_time"):
            due += " " + (TZ.get(d.get("bid_due_zone")) or "(time zone not stated)")
        fields.append("Bid due (form reference only): " + due)
    if d["instructions"]:
        fields.append("Contact / instructions: " + d["instructions"])
    if d["evidence"]:
        fields.append("Manual source note: " + d["evidence"])
    return "\n".join(fields)
