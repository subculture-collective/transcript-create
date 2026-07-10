#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.archive.smart_summaries import generate_period_summary_proposals
from app.db import session_scope


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate citation-validated archive period summary proposals.")
    parser.add_argument("--granularity", choices=("month", "week"), default="month")
    parser.add_argument("--period", default="", help="Optional exact period such as 2026-04.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum periods to process (1-24).")
    parser.add_argument("--model", default=os.getenv("ARCHIVE_SUMMARY_MODEL", "qwen3:4b"))
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://ollama:11434"))
    parser.add_argument("--apply", action="store_true", help="Persist validated summaries; default is dry-run.")
    args = parser.parse_args()

    with session_scope() as db:
        proposals = generate_period_summary_proposals(
            db,
            base_url=args.ollama_url,
            model=args.model,
            granularity=args.granularity,
            period=args.period or None,
            limit=args.limit,
            apply=args.apply,
        )
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry_run",
                "model": args.model,
                "prompted_periods": len(proposals),
                "proposals": proposals,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
