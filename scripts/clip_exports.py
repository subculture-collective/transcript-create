#!/usr/bin/env python3
"""Operator-only local-original registration and one-job clip rendering."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.clip_exports import ClipError, ClipStore  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version="clip-exports 1")
    parser.add_argument("--spool", type=Path, required=True, help="Private output/queue directory, mode 700")
    parser.add_argument("--originals", type=Path, required=True, help="Directory containing authorized local originals")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="Register one authorized original; never downloads media")
    register.add_argument("--video-id", required=True)
    register.add_argument("--owner-id", required=True, help="Archive account UUID authorized to request exports")
    register.add_argument("--source", type=Path, required=True)
    register.add_argument(
        "--rights-note", required=True, help="Specific declared authorization basis; not independent proof"
    )
    register.add_argument(
        "--confirm-timeline-alignment",
        action="store_true",
        required=True,
        help="Confirm original and archive timestamps match exactly",
    )
    enqueue = commands.add_parser("enqueue", help="Queue a bounded passage from a registered original")
    enqueue.add_argument("--video-id", required=True)
    enqueue.add_argument("--owner-id", required=True)
    enqueue.add_argument("--start-ms", type=int, required=True)
    enqueue.add_argument("--end-ms", type=int, required=True)
    run = commands.add_parser("run", help="Render one queued job with ffmpeg, then exit")
    run.add_argument("job_id")
    commands.add_parser("run-next", help="Render the oldest unexpired queued job, then exit")
    status = commands.add_parser("status", help="Read an owned job; expired outputs are unavailable")
    status.add_argument("job_id")
    status.add_argument("--owner-id", required=True)
    revoke = commands.add_parser("revoke", help="Revoke a source and remove its rendered outputs")
    revoke.add_argument("video_id")
    cleanup = commands.add_parser("cleanup", help="Preview expired/failed output cleanup")
    cleanup.add_argument("--apply", action="store_true", help="Remove listed job metadata and generated media")
    args = parser.parse_args(argv)
    try:
        store = ClipStore(args.spool, args.originals)
        if args.command == "register":
            result = store.register(
                args.video_id,
                args.owner_id,
                args.source,
                args.rights_note,
                timeline_aligned=args.confirm_timeline_alignment,
            )
        elif args.command == "enqueue":
            result = store.enqueue(args.video_id, args.owner_id, args.start_ms, args.end_ms)
        elif args.command == "run":
            result = store.run(args.job_id)
        elif args.command == "run-next":
            import time

            queued = [json.loads(path.read_text()) for path in (store.spool / "jobs").glob("*.json")]
            queued = sorted(
                (job for job in queued if job["status"] == "queued" and job["expires_at"] > time.time()),
                key=lambda job: job["created_at"],
            )
            result = store.run(queued[0]["id"]) if queued else {"status": "idle"}
        elif args.command == "status":
            result = store.status(args.job_id, args.owner_id)
        elif args.command == "revoke":
            result = store.revoke(args.video_id)
        else:
            result = store.cleanup(args.apply)
        print(json.dumps(result))
        return 1 if result.get("status") == "failed" else 0
    except (ClipError, OSError, ValueError) as exc:
        print(f"clip-exports: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("clip-exports: interrupted; inspect job status before retrying", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
