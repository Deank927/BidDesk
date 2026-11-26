import csv
import hashlib
import re
import xml.etree.ElementTree as ET
from urllib.request import urlopen

from .db import now

# Verify against the county site; configurable in Settings.
LA_COUNTY_RSS_DEFAULT = "https://camisvr.co.la.ca.us/LACoBids/BidLookUp/RSSFeed"

CSV_ALIASES = {
    "agency": ["agency", "department", "owner"],
    "solicitation_no": ["solicitation_no", "solicitation", "solicitation number", "bid number", "bid no"],
    "title": ["title", "project", "description"],
    "location": ["location", "city", "address"],
    "notice_url": ["notice_url", "url", "link", "notice"],
    "posted": ["posted", "date", "posted date"],
}


def dedupe_key(agency, sol_no, url, title):
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    basis = f"{norm(agency)}|{norm(sol_no)}" if sol_no else f"url|{norm(url) or norm(title)}"
    return hashlib.sha1(basis.encode()).hexdigest()


def add_lead(p, source, agency, solicitation_no, title, location, notice_url, posted=""):
    """Returns lead id, or None if duplicate. Never sets GO, events, or messages."""
    key = dedupe_key(agency, solicitation_no, notice_url, title)
    if p.one("SELECT id FROM leads WHERE dedupe_key=?", (key,)):
        return None
    return p.x(
        "INSERT INTO leads(source,agency,solicitation_no,title,location,notice_url,posted,dedupe_key,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (source, agency, solicitation_no, title, location, notice_url, posted, key, now()),
    )


def _pick(row, field):
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for alias in CSV_ALIASES[field]:
        if alias in low and low[alias]:
            return low[alias].strip()
    return ""


def import_csv(p, path):
    added, dupes = 0, 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            vals = {k: _pick(row, k) for k in CSV_ALIASES}
            if not (vals["title"] or vals["solicitation_no"]):
                continue
            if add_lead(p, "csv", **vals):
                added += 1
            else:
                dupes += 1
    return added, dupes


SOL_RE = re.compile(r"\b(?:Solicitation|Bid|RFP|RFB|IFB)\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{3,})", re.I)


def parse_rss(xml_text, agency_default="Los Angeles County"):
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        g = lambda t: (item.findtext(t) or "").strip()
        title, desc = g("title"), re.sub(r"<[^>]+>", " ", g("description"))
        m = SOL_RE.search(title) or SOL_RE.search(desc)
        loc = re.search(r"Location\s*:\s*([^\n|;]+)", desc, re.I)
        dept = re.search(r"(?:Department|Agency)\s*:\s*([^\n|;]+)", desc, re.I)
        out.append(dict(
            agency=dept.group(1).strip() if dept else agency_default,
            solicitation_no=m.group(1) if m else g("guid"),
            title=title, location=loc.group(1).strip() if loc else "",
            notice_url=g("link"), posted=g("pubDate"),
        ))
    return out


def import_rss(p, source_url_or_path):
    if source_url_or_path.startswith("http"):
        with urlopen(source_url_or_path, timeout=20) as r:
            text = r.read().decode("utf-8", "replace")
    else:
        text = open(source_url_or_path, encoding="utf-8").read()
    added, dupes = 0, 0
    for item in parse_rss(text):
        if add_lead(p, "rss", **item):
            added += 1
        else:
            dupes += 1
    return added, dupes


def set_decision(p, lead_id, decision):
    assert decision in ("GO", "HOLD", "NO GO")
    stage = "pipeline" if decision == "GO" else "lead"
    p.x("UPDATE leads SET decision=?, stage=? WHERE id=?", (decision, stage, lead_id))
    p.x("INSERT OR IGNORE INTO lead_meta(lead_id) VALUES(?)", (lead_id,))


def mark_awarded(p, lead_id):
    p.x("UPDATE leads SET stage='awarded' WHERE id=?", (lead_id,))

