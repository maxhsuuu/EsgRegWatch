"""
ESGRegWatch – Ingestion Pipeline
---------------------------------
Fetches official public ESG/carbon-fee sources listed in sources_registry.json.
Each raw document is stored as a versioned JSONL record with full provenance:
  source_id, url, authority, retrieved_at, document_hash, text, http_status

This mirrors the Airflow-orchestrated production design described in the report,
but runs as a standalone script for the course prototype.

Usage:
    python scripts/ingest.py            # fetch all sources
    python scripts/ingest.py --dry-run  # print what would be fetched
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "data" / "sources_registry.json"
RAW_OUT = ROOT / "data" / "raw" / "fetched_documents.jsonl"
HEADERS = {
    "User-Agent": (
        "ESGRegWatch-BDA-CoursePrototype/1.0 "
        "(National Taiwan University Big Data Systems; "
        "educational use only)"
    )
}
REQUEST_DELAY_SEC = 2   # polite crawl rate


def clean_text(html: str) -> str:
    """Strip nav/footer/scripts and normalise whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return text[:25_000]   # cap at 25k chars per document


def doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def fetch_source(src: dict) -> dict:
    record = {
        "source_id": src["id"],
        "name": src["name"],
        "url": src["url"],
        "authority": src["authority"],
        "category": src["category"],
        "regulation_type": src["regulation_type"],
        "affected_company_type": src["affected_company_type"],
        "priority": src["priority"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "document_hash": None,
        "text": "",
        "error": None,
    }
    try:
        resp = requests.get(src["url"], timeout=25, headers=HEADERS)
        record["http_status"] = resp.status_code
        resp.raise_for_status()
        text = clean_text(resp.text)
        record["text"] = text
        record["document_hash"] = doc_hash(text)
        print(f"  ✓ {src['id']}  ({len(text):,} chars)")
    except requests.RequestException as exc:
        record["error"] = str(exc)
        print(f"  ✗ {src['id']}  ERROR: {exc}")
    return record


def main():
    parser = argparse.ArgumentParser(description="ESGRegWatch ingestion pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Print sources without fetching")
    args = parser.parse_args()

    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"ESGRegWatch Ingestion – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Sources to process: {len(sources)}")

    if args.dry_run:
        for s in sources:
            print(f"  [DRY] {s['id']} → {s['url']}")
        return

    records = []
    for i, src in enumerate(sources):
        print(f"[{i+1}/{len(sources)}] Fetching: {src['name']}")
        rec = fetch_source(src)
        records.append(rec)
        if i < len(sources) - 1:
            time.sleep(REQUEST_DELAY_SEC)

    # Append-write: preserves historical versions for audit trail
    with RAW_OUT.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    ok = sum(1 for r in records if not r["error"])
    print(f"\nDone: {ok}/{len(records)} succeeded → {RAW_OUT}")


if __name__ == "__main__":
    main()
