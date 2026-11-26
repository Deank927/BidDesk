import json
import re
from urllib.request import urlopen, Request

FIELDS = ("scope", "bid_due", "job_walk", "walk_registration", "questions_due", "submission_method",
          "license", "eligibility", "form_required", "doc_required")
PROMPT = """You review public construction bid documents. From the page below, list requirements as JSON:
{{"findings":[{{"field":one of {fields},"value":"short value","quote":"exact sentence copied from the page"}}]}}
Only include items literally stated on the page. Copy the quote exactly. If nothing, return {{"findings":[]}}.
PAGE:
{text}"""


def configured(p):
    return bool(p.setting("ollama_url")) and bool(p.setting("ollama_model"))


def ping(p):
    try:
        with urlopen(p.setting("ollama_url").rstrip("/") + "/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def review_with_ollama(p, lead_id):
    """Local-only. Returns draft findings whose quote is verified to exist on the cited page."""
    if not configured(p):
        return []
    url = p.setting("ollama_url").rstrip("/")
    if not re.match(r"https?://(localhost|127\.0\.0\.1)(:\d+)?$", url):
        raise PermissionError("Ollama must be local (localhost) to keep bid files on this computer.")
    out = []
    pages = p.q("SELECT dp.* FROM doc_pages dp JOIN documents d ON d.id=dp.doc_id WHERE d.lead_id=? AND d.kind IN ('solicitation','addendum','other')", (lead_id,))
    for pg in pages:
        if len(pg["text"].strip()) < 40:
            continue
        body = json.dumps({"model": p.setting("ollama_model"), "stream": False, "format": "json",
                           "prompt": PROMPT.format(fields=list(FIELDS), text=pg["text"][:6000])}).encode()
        try:
            with urlopen(Request(url + "/api/generate", body, {"Content-Type": "application/json"}), timeout=120) as r:
                items = json.loads(json.loads(r.read())["response"]).get("findings", [])
        except Exception:
            continue
        page_norm = _norm(pg["text"])
        for it in items:
            q = str(it.get("quote", ""))
            if it.get("field") in FIELDS and q and _norm(q) in page_norm:
                out.append(dict(field=it["field"], value=str(it.get("value", ""))[:300], doc_id=pg["doc_id"],
                                page=pg["page"], snippet=q[:400]))
    return out


