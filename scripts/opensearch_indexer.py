#!/usr/bin/env python3
import sys
import logging
from pathlib import Path
from typing import Iterable, List

from sqlalchemy import create_engine, text
import requests
import json
import time

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.settings import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [indexer] %(message)s')


def ensure_index(name: str, recreate: bool = False):
    url = f"{settings.OPENSEARCH_URL}/{name}"
    # Rich analyzers: english stemming + synonyms, ngrams, edge ngrams, shingles
    mapping = {
        "settings": {
            "index": {"number_of_shards": 1, "number_of_replicas": 0, "max_ngram_diff": 20},
            "analysis": {
                "filter": {
                    "english_stop": {"type": "stop", "stopwords": "_english_"},
                    "english_stemmer": {"type": "stemmer", "language": "english"},
                    "english_possessive_stemmer": {"type": "stemmer", "language": "possessive_english"},
                    "synonyms_index": {"type": "synonym", "expand": True, "synonyms_path": "analysis/synonyms.txt"},
                    "synonyms_query": {"type": "synonym_graph", "expand": True, "synonyms_path": "analysis/synonyms.txt"},
                    "ngram_filter": {"type": "ngram", "min_gram": 3, "max_gram": 8},
                    "edge_ngram_filter": {"type": "edge_ngram", "min_gram": 2, "max_gram": 20}
                },
                "analyzer": {
                    "text_en_index": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "english_possessive_stemmer", "english_stop", "english_stemmer", "synonyms_index"]
                    },
                    "text_en_query": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "english_possessive_stemmer", "english_stop", "english_stemmer", "synonyms_query"]
                    },
                    "text_shingle": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "shingle", "english_stop", "english_stemmer"]
                    },
                    "text_ngram": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "ngram_filter"]
                    },
                    "text_edge": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "edge_ngram_filter"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "id": {"type": "long"},
                "video_id": {"type": "keyword"},
                "start_ms": {"type": "integer"},
                "end_ms": {"type": "integer"},
                "text": {
                    "type": "text",
                    "analyzer": "text_en_index",
                    "search_analyzer": "text_en_query",
                    "fields": {
                        "shingle": {"type": "text", "analyzer": "text_shingle"},
                        "ngram": {"type": "text", "analyzer": "text_ngram", "search_analyzer": "text_en_query"},
                        "edge": {"type": "text", "analyzer": "text_edge", "search_analyzer": "text_en_query"},
                        "keyword": {"type": "keyword", "ignore_above": 256}
                    }
                }
            }
        }
    }
    r = requests.head(url, timeout=10)
    if r.status_code == 200 and recreate:
        delr = requests.delete(url, timeout=30)
        delr.raise_for_status()
    elif r.status_code == 200:
        return
    r = requests.put(url, json=mapping, timeout=60)
    if r.status_code >= 400:
        logging.error("Index create failed: %s", r.text)
    r.raise_for_status()
    logging.info("Created index %s", name)


def update_index_settings(name: str, new_settings: dict):
    url = f"{settings.OPENSEARCH_URL}/{name}/_settings"
    r = requests.put(url, json={"index": new_settings}, timeout=30)
    r.raise_for_status()
    logging.info("Updated %s settings: %s", name, new_settings)


def gen_bulk_actions(index: str, rows: Iterable[dict]):
    for r in rows:
        yield {"index": {"_index": index, "_id": r["id"]}}
        yield {
            "id": r["id"],
            "video_id": str(r["video_id"]),
            "start_ms": r["start_ms"],
            "end_ms": r["end_ms"],
            "text": r["text"],
        }


def bulk_post(actions: List[dict], retries: int = 5, base_sleep: float = 0.5):
    # NDJSON bulk API with simple backoff on 429/503
    data = "\n".join(json.dumps(a, ensure_ascii=False) for a in actions) + "\n"
    url = f"{settings.OPENSEARCH_URL}/_bulk"
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, data=data, headers={"Content-Type": "application/x-ndjson"}, timeout=120)
            if r.status_code in (429, 503):
                raise requests.HTTPError(f"{r.status_code} {r.reason}", response=r)
            r.raise_for_status()
            j = r.json()
            if j.get('errors'):
                logging.warning("Bulk had item errors (continuing): %s", j.get('errors'))
            return j
        except requests.HTTPError as e:
            last_exc = e
            status = getattr(e.response, 'status_code', None)
            if status in (429, 503) and attempt < retries:
                sleep_s = base_sleep * (2 ** attempt)
                time.sleep(sleep_s)
                continue
            raise
    if last_exc:
        raise last_exc


def index_table(engine, table: str, index: str, last_id: int, batch: int, bulk_docs: int) -> int:
    with engine.connect() as conn:
        if table == "segments":
            sql = text("""
                SELECT id, video_id, start_ms, end_ms, text
                FROM segments WHERE id > :last_id
                ORDER BY id ASC LIMIT :lim
            """)
        else:
            sql = text("""
                SELECT ys.id, yt.video_id, ys.start_ms, ys.end_ms, ys.text
                FROM youtube_segments ys
                JOIN youtube_transcripts yt ON yt.id = ys.youtube_transcript_id
                WHERE ys.id > :last_id
                ORDER BY ys.id ASC LIMIT :lim
            """)
        rows = conn.execute(sql, {"last_id": last_id, "lim": batch}).mappings().all()
        if not rows:
            return 0
        # Chunk by bulk_docs (each doc corresponds to 2 actions)
        for i in range(0, len(rows), bulk_docs):
            chunk = rows[i:i+bulk_docs]
            actions = list(gen_bulk_actions(index, chunk))
            bulk_post(actions)
        return rows[-1]["id"]


def main(batch: int = 5000, source: str = "both", bulk_docs: int = 2000, recreate: bool = False, refresh_off: bool = False):
    assert settings.SEARCH_BACKEND in ("postgres", "opensearch"), "Invalid SEARCH_BACKEND"
    ensure_index(settings.OPENSEARCH_INDEX_NATIVE, recreate=recreate)
    ensure_index(settings.OPENSEARCH_INDEX_YOUTUBE, recreate=recreate)
    eng = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    # Optionally disable refresh for faster bulk indexing
    if refresh_off:
        try:
            update_index_settings(settings.OPENSEARCH_INDEX_NATIVE, {"refresh_interval": "-1", "translog.durability": "async"})
            update_index_settings(settings.OPENSEARCH_INDEX_YOUTUBE, {"refresh_interval": "-1", "translog.durability": "async"})
        except Exception as e:
            logging.warning("Failed to disable refresh: %s", e)
    last_native = 0
    last_youtube = 0
    while True:
        progressed = False
        if source in ("native", "both"):
            new_last = index_table(eng, "segments", settings.OPENSEARCH_INDEX_NATIVE, last_native, batch, bulk_docs)
            if new_last:
                last_native = new_last
                progressed = True
                logging.info("Indexed native up to id=%d", last_native)
        if source in ("youtube", "both"):
            new_last = index_table(eng, "youtube_segments", settings.OPENSEARCH_INDEX_YOUTUBE, last_youtube, batch, bulk_docs)
            if new_last:
                last_youtube = new_last
                progressed = True
                logging.info("Indexed youtube up to id=%d", last_youtube)
        if not progressed:
            break
    logging.info("Indexing complete")
    # Restore refresh interval
    if refresh_off:
        try:
            update_index_settings(settings.OPENSEARCH_INDEX_NATIVE, {"refresh_interval": "1s", "translog.durability": "request"})
            update_index_settings(settings.OPENSEARCH_INDEX_YOUTUBE, {"refresh_interval": "1s", "translog.durability": "request"})
        except Exception as e:
            logging.warning("Failed to restore refresh: %s", e)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Index Postgres data into OpenSearch")
    parser.add_argument("--batch", type=int, default=5000, help="Rows to fetch from Postgres per pass")
    parser.add_argument("--source", choices=["native","youtube","both"], default="both")
    parser.add_argument("--bulk-docs", type=int, default=2000, help="Documents per bulk request")
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate indices before indexing")
    parser.add_argument("--refresh-off", action="store_true", help="Temporarily disable index refresh during bulk indexing")
    args = parser.parse_args()
    main(batch=args.batch, source=args.source, bulk_docs=args.bulk_docs, recreate=args.recreate, refresh_off=args.refresh_off)
