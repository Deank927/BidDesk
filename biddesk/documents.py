import hashlib
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen, Request

from pypdf import PdfReader

from .db import now, copy_readonly

KINDS = ("solicitation", "addendum", "form", "supporting", "other")
SPREADSHEET = {".xlsx", ".xls", ".csv", ".xlsm"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pages(path):
    """Returns (status, [page_text...]). status: ok | scan | spreadsheet | unsupported"""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        pages = [(pg.extract_text() or "") for pg in PdfReader(str(path)).pages]
        if pages and sum(len(t.strip()) for t in pages) < 20 * len(pages):
            return "scan", pages
        return "ok", pages
    if ext in (".txt", ".md"):
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return "ok", text.split("\f")
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return "ok", [re.sub(r"<[^>]+>", "", xml)]
    if ext in SPREADSHEET:
        return "spreadsheet", []
    if ext in IMAGES:
        return "scan", []
    return "unsupported", []


def guess_kind(name):
    n = name.lower()
    m = re.search(r"addend(?:um|a)[\s_\-#no.]*(\d+)", n)
    if m:
        return "addendum", int(m.group(1))
    if "form" in n or "bid sheet" in n or "proposal" in n:
        return "form", None
    if re.search(r"(?<![a-z0-9])rfq(?![a-z0-9])", n) or any(k in n for k in ("solicitation", "rfp", "ifb", "rfb", "spec", "notice")):
        return "solicitation", None
    return "other", None


def attach(p, lead_id, src, kind=None, addendum_no=None):
    """Copy the official file once into originals/ (read-only). Returns doc id (existing if same file)."""
    src = Path(src)
    digest = sha256(src)
    existing = p.one("SELECT id FROM documents WHERE lead_id=? AND sha256=?", (lead_id, digest))
    if existing:
        return existing["id"]
    gk, gn = guess_kind(src.name)
    kind = kind or gk
    addendum_no = addendum_no if addendum_no is not None else gn
    dest = p.root / "originals" / str(lead_id) / f"{digest[:8]}_{src.name}"
    if not dest.exists():
        copy_readonly(src, dest)
    status, pages = extract_pages(dest)
    did = p.x(
        "INSERT INTO documents(lead_id,kind,addendum_no,filename,original_path,sha256,pages,text_status,imported_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (lead_id, kind, addendum_no, src.name, str(dest.relative_to(p.root)), digest, len(pages), status, now()),
    )
    for i, t in enumerate(pages, 1):
        p.x("INSERT INTO doc_pages(doc_id,page,text) VALUES(?,?,?)", (did, i, t))
    return did


def docs(p, lead_id):
    return p.q("SELECT * FROM documents WHERE lead_id=? ORDER BY kind, addendum_no, id", (lead_id,))


def reclassify(p, lead_id, doc_id, kind, addendum_no=None):
    """Change existing metadata only. No copy, reimport, or review is triggered here."""
    if kind not in KINDS:
        raise ValueError("Choose a valid document kind.")
    if kind == "addendum":
        if not isinstance(addendum_no, int) or not 1 <= addendum_no <= 99:
            raise ValueError("Enter an addendum number from 1 to 99.")
    elif addendum_no is not None:
        raise ValueError("Only addenda can carry an addendum number.")
    doc = p.one("SELECT kind, addendum_no FROM documents WHERE lead_id=? AND id=?", (lead_id, doc_id))
    if doc is None:
        raise ValueError("The document does not belong to this opportunity.")
    if (doc["kind"], doc["addendum_no"]) == (kind, addendum_no):
        return False
    p.x("UPDATE documents SET kind=?, addendum_no=? WHERE lead_id=? AND id=?",
        (kind, addendum_no, lead_id, doc_id))
    return True


def mark_reviewed(p, doc_id):
    p.x("UPDATE documents SET reviewed=1 WHERE id=?", (doc_id,))


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href") if tag == "a" else None
        if href and re.search(r"\.(pdf|docx?|xlsx?|zip)(\?|$)", href, re.I):
            self.links.append(href)


def list_notice_attachments(p, notice_url):
    """Preview official attachments linked from the notice page (only if the user enabled connections)."""
    if p.setting("allow_network", "0") != "1":
        raise PermissionError("Network connections are off. Enable them in Settings to fetch from the notice.")
    with urlopen(Request(notice_url, headers={"User-Agent": "BidDesk"}), timeout=20) as r:
        html = r.read().decode("utf-8", "replace")
    parser = _Links()
    parser.feed(html)
    return sorted({urljoin(notice_url, h) for h in parser.links})


def download_attachment(p, lead_id, url):
    if p.setting("allow_network", "0") != "1":
        raise PermissionError("Network connections are off.")
    name = re.sub(r"[^\w.\-]", "_", url.split("?")[0].rsplit("/", 1)[-1]) or "attachment"
    tmp = p.root / "working" / "_downloads" / name
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(Request(url, headers={"User-Agent": "BidDesk"}), timeout=60) as r:
        tmp.write_bytes(r.read())
    return attach(p, lead_id, tmp)
