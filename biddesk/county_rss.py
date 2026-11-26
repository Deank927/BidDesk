"""LA County's public OpenBidList; preview and selected import only."""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .db import now

HOST = "camisvr.co.la.ca.us"
DETAIL = "/LACoBids/BidLookUp/BidDetail"
FEED = f"https://{HOST}/LACoBids/RssFeed/OpenBidList"
ORIGIN_DETAIL = f"https://{HOST}{DETAIL}"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
KEY = re.compile(r"^[#A-Za-z0-9][A-Za-z0-9_ .#()/-]{2,79}$")

@dataclass(frozen=True)
class Notice:
    key: str
    title: str
    department: str
    closing: str
    posted: str

    url: str

@dataclass(frozen=True)
class Preview:
    notices: tuple
    skipped: int

def clean(text, limit=500):
    return " ".join((text or "").split())[:limit]

def notice_key(link):
    try:
        parts = urlsplit(link)
        if (parts.scheme != "https" or parts.netloc.lower() != HOST
                or parts.path.lower() != DETAIL.lower() or parts.fragment):
            return ""
        q = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1, errors="strict")
        if len(q) == 1 and q[0][0].casefold() == "bidnumber":
            value = q[0][1].strip()
            if KEY.fullmatch(value):
                return value.upper()
    except (ValueError, TypeError):
        pass
    return ""

def closing_text(raw):
    raw = clean(raw, 80)
    if raw.casefold() == "continuous":
        return "Continuous (not a deadline)"
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %I:%M %p PT")
        except ValueError:
            pass
    return "Not stated / unverified"

def parse_open(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("County response is empty or exceeds the size limit.")
    # Parse only UTF-8 public RSS; no DTD, external entities or document types.
    xml = raw.decode("utf-8-sig", errors="strict")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml, re.I):
        raise ValueError("County response contains unsupported XML declarations.")
    root = ET.fromstring(xml)
    nodes = root.findall("./channel/item")
    if root.tag != "rss" or len(root.findall("./channel")) != 1 or len(nodes) > MAX_ROWS:
        raise ValueError("County response is not the expected OpenBidList RSS.")
    rows, seen = [], set()
    for n in nodes:
        link = (n.findtext("link") or "").strip()
        key = notice_key(link) if len(link) <= 2048 and not any(c.isspace() for c in link) else ""
        title = clean(n.findtext("title"))
        if not key or not title:
            continue
        # A clearly formed different RFB/RFP/IFB/RFQ identity in the title is contradictory.
        lead_token = title.split(" ", 1)[0].rstrip(":").upper()
        if re.fullmatch(r"RF[BPQ]-[A-Z0-9-]+-[A-Z0-9-]+|IFB-[A-Z0-9-]+-[A-Z0-9-]+", lead_token) and lead_token != key:
            continue
        if key in seen:
            continue
        seen.add(key)
        rows.append(Notice(key, title, clean(n.findtext("bidDepartment"), 160) or "Not stated",
                           closing_text(n.findtext("closeDate")), clean(n.findtext("pubDate"), 96), link))
    if not rows and nodes:
        raise ValueError("County feed has no entries with a verified detail link and title.")
    return Preview(tuple(rows), len(nodes) - len(rows))

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def fetch_open():
    req = Request(FEED, headers={"Accept": "application/rss+xml, application/xml;q=0.9",
                                 "User-Agent": "BidDesk-Emergent/CountyFeed-Test3"})
    with build_opener(NoRedirect()).open(req, timeout=8) as response:
        if response.geturl() != FEED or response.status != 200:
            raise ValueError("County feed did not return the expected official HTTPS response.")
        body = response.read(MAX_BYTES + 1)
    return parse_open(body)

def existing_keys(project):
    keys = set()
    for r in project.q("SELECT source, agency, solicitation_no, notice_url FROM leads"):
        key = notice_key(r["notice_url"])
        if key:
            keys.add(key)
        elif (r["source"] == "la_county_open_rss" or "los angeles county" in (r["agency"] or "").casefold()):
            value = (r["solicitation_no"] or "").strip().upper()
            if KEY.fullmatch(value):
                keys.add(value)
    return keys

def import_selected(project, notices):
    added = duplicates = 0
    with project.conn:
        have = existing_keys(project)
        for item in notices:
            if not isinstance(item, Notice) or notice_key(item.url) != item.key or not item.title:
                raise ValueError("Selected notice has no verified County identity.")
            if item.key in have:
                duplicates += 1
                continue
            department = "" if item.department == "Not stated" else " - " + item.department
            cur = project.conn.execute(
                "INSERT OR IGNORE INTO leads(source,agency,solicitation_no,title,location,notice_url,posted,dedupe_key,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)", ("la_county_open_rss", "Los Angeles County" + department, item.key,
                 item.title, "", item.url, item.posted, "la-county/open/" + item.key.casefold(), now()))
            if cur.rowcount == 1:
                added += 1
            else:
                duplicates += 1
            have.add(item.key)
    return added, duplicates
