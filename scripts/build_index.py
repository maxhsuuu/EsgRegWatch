"""
ESGRegWatch – Processing & Index Builder
-----------------------------------------
Reads raw ingested documents (JSONL) and the curated seed dataset,
then builds a SQLite store with:
  - documents table  : full text + provenance metadata
  - regulations table: extracted structured entities (deadline, fee_rate, scope)
  - tfidf_terms      : top-8 TF-IDF terms per document for quick preview

In production this step runs on Spark for large volumes; SQLite is
sufficient for the course prototype (hundreds of documents).

Usage:
    python scripts/build_index.py
"""

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
RAW_JSONL = ROOT / "data" / "raw" / "fetched_documents.jsonl"
SEED_JSONL = ROOT / "data" / "seed_documents.jsonl"
DB_PATH = ROOT / "data" / "processed" / "esgregwatch.sqlite"

# ── Entity extraction patterns ──────────────────────────────────────────────

FEE_PATTERN = re.compile(r"NT\$[\d,]+(?:\s*/\s*tCO2e)?", re.IGNORECASE)
DEADLINE_PATTERN = re.compile(
    r"(?:fiscal year|FY|by|from|starting|effective)\s+(\d{4})", re.IGNORECASE
)
SCOPE_PATTERN = re.compile(
    r"(\d[\d,]*)\s*tCO2e(?:\s+per\s+year)?", re.IGNORECASE
)


def extract_entities(text: str) -> dict:
    fees = FEE_PATTERN.findall(text)
    years = DEADLINE_PATTERN.findall(text)
    scopes = SCOPE_PATTERN.findall(text)
    return {
        "fee_rates": "; ".join(dict.fromkeys(fees)) if fees else "",
        "key_years": "; ".join(dict.fromkeys(years[:4])) if years else "",
        "emission_scopes": "; ".join(dict.fromkeys(scopes)) if scopes else "",
    }


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


def compute_tfidf_terms(texts: list[str]) -> list[str]:
    if not texts:
        return []
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=5000)
    X = vec.fit_transform(texts)
    terms = vec.get_feature_names_out()
    result = []
    for i in range(X.shape[0]):
        row = X[i].toarray().ravel()
        top_idx = row.argsort()[-8:][::-1]
        result.append(", ".join(terms[j] for j in top_idx if row[j] > 0))
    return result


def build_documents_df(raw_records: list[dict], seed_records: list[dict]) -> pd.DataFrame:
    rows = []

    # Seed curated documents always included
    for r in seed_records:
        rows.append({
            "source_id": r.get("source", "seed"),
            "title": r.get("title", ""),
            "text": r.get("text", ""),
            "authority": r.get("authority", r.get("source", "")),
            "category": r.get("category", ""),
            "regulation_type": r.get("regulation_type", ""),
            "affected_company_type": r.get("affected_company_type", ""),
            "priority": r.get("priority", "medium"),
            "date": r.get("date", ""),
            "url": r.get("url", ""),
            "retrieved_at": r.get("retrieved_at", ""),
            "document_hash": r.get("document_hash", ""),
            "customer_impact": r.get("customer_impact", ""),
            "data_source": "seed",
        })

    # Live-fetched documents (if any succeeded)
    for r in raw_records:
        if r.get("error") or not r.get("text"):
            continue
        rows.append({
            "source_id": r.get("source_id", ""),
            "title": r.get("name", ""),
            "text": r.get("text", ""),
            "authority": r.get("authority", ""),
            "category": r.get("category", ""),
            "regulation_type": r.get("regulation_type", ""),
            "affected_company_type": json.dumps(r.get("affected_company_type", [])),
            "priority": r.get("priority", "medium"),
            "date": r.get("retrieved_at", "")[:10],
            "url": r.get("url", ""),
            "retrieved_at": r.get("retrieved_at", ""),
            "document_hash": r.get("document_hash", ""),
            "customer_impact": "",
            "data_source": "live",
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["source_id", "document_hash"])
    return df.reset_index(drop=True)


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Loading raw documents...")
    raw_records = load_jsonl(RAW_JSONL)
    seed_records = load_jsonl(SEED_JSONL)
    print(f"  Raw (fetched): {len(raw_records)}, Seed (curated): {len(seed_records)}")

    df = build_documents_df(raw_records, seed_records)
    print(f"  Unique documents after dedup: {len(df)}")

    # Entity extraction
    entities = df["text"].apply(extract_entities)
    df["fee_rates"] = [e["fee_rates"] for e in entities]
    df["key_years"] = [e["key_years"] for e in entities]
    df["emission_scopes"] = [e["emission_scopes"] for e in entities]

    # TF-IDF top terms
    combined_text = (df["title"] + " " + df["text"] + " " + df.get("customer_impact", "")).tolist()
    df["top_terms"] = compute_tfidf_terms(combined_text)

    # Write to SQLite
    with sqlite3.connect(DB_PATH) as con:
        df.to_sql("documents", con, if_exists="replace", index=True, index_label="id")

        # Structured regulations view
        con.execute("""
            CREATE VIEW IF NOT EXISTS regulations AS
            SELECT id, source_id, title, authority, category, regulation_type,
                   priority, date, fee_rates, key_years, emission_scopes, url
            FROM documents
            WHERE fee_rates != '' OR key_years != '' OR emission_scopes != ''
        """)
        con.commit()

    print(f"\nIndex built → {DB_PATH}")
    print(f"  documents: {len(df)} rows")
    print(f"  with extracted entities: {(df['fee_rates'] != '').sum()} fee rates, "
          f"{(df['key_years'] != '').sum()} deadlines, "
          f"{(df['emission_scopes'] != '').sum()} emission scopes")


if __name__ == "__main__":
    main()
