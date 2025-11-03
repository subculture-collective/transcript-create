#!/usr/bin/env python3
"""
Backfill script to apply formatting/cleanup to existing transcripts.

This script iterates through videos and applies the transcript formatting
module to existing segments, storing the cleaned output in the database.

Features:
- Idempotency: skips already-formatted transcripts with same version
- Dry-run mode: preview changes without committing
- Filtering: by channel, job ID, or specific video IDs
- Batch processing: processes videos in configurable batches
- Resume capability: can be stopped and resumed safely
- Progress tracking: detailed logging and metrics

Usage:
    # Dry run to preview changes
    python scripts/backfill_formatting.py --dry-run --batch 10

    # Process all videos in batches
    python scripts/backfill_formatting.py --batch 100 --until-empty

    # Process specific videos
    python scripts/backfill_formatting.py --video-ids UUID1,UUID2,UUID3

    # Filter by channel
    python scripts/backfill_formatting.py --channel-name "My Channel" --batch 50

    # Filter by job ID
    python scripts/backfill_formatting.py --job-id JOB_UUID --batch 20
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.logging_config import configure_logging, get_logger
from app.settings import settings
from worker.formatter import TranscriptFormatter

# Configure structured logging for scripts
configure_logging(
    service="script.backfill-formatting",
    level=settings.LOG_LEVEL,
    json_format=(settings.LOG_FORMAT == "json"),
)
logger = get_logger(__name__)

# Formatting version - increment when formatting logic changes significantly
FORMATTING_VERSION = "1.0.0"


def compute_config_hash(config: Dict[str, Any]) -> str:
    """
    Compute a stable hash of the formatting configuration.
    
    This allows us to detect when the config has changed and reformat accordingly.
    """
    # Sort keys for stable hashing
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


def get_current_formatting_config() -> Dict[str, Any]:
    """Get the current formatting configuration from settings."""
    formatter = TranscriptFormatter()
    return formatter.config


def should_process_transcript(
    conn, transcript_id: str, current_config_hash: str, force: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Check if a transcript should be processed.
    
    Returns:
        tuple: (should_process: bool, reason: Optional[str])
    """
    if force:
        return True, "forced reprocessing"
    
    # Check if transcript has cleanup_config
    row = conn.execute(
        text(
            """
            SELECT cleanup_config, is_cleaned
            FROM transcripts
            WHERE id = :tid
        """
        ),
        {"tid": transcript_id},
    ).mappings().fetchone()
    
    if not row:
        return False, "transcript not found"
    
    cleanup_config = row["cleanup_config"]
    is_cleaned = row["is_cleaned"]
    
    # If never cleaned, process it
    if not is_cleaned or not cleanup_config:
        return True, "never formatted"
    
    # Check version and config hash
    stored_version = cleanup_config.get("version", "0.0.0")
    stored_config_hash = cleanup_config.get("config_hash", "")
    
    # Process if version or config has changed
    if stored_version != FORMATTING_VERSION:
        return True, f"version changed ({stored_version} -> {FORMATTING_VERSION})"
    
    if stored_config_hash != current_config_hash:
        return True, "config changed"
    
    return False, "already formatted with current version"


def load_segments_for_video(conn, video_id: str) -> List[Dict[str, Any]]:
    """Load raw segments for a video."""
    rows = conn.execute(
        text(
            """
            SELECT id, start_ms, end_ms, text, speaker, speaker_label, idx
            FROM segments
            WHERE video_id = :vid
            ORDER BY start_ms
        """
        ),
        {"vid": video_id},
    ).mappings()
    
    segments = []
    for row in rows:
        seg = {
            "id": row["id"],
            "start": row["start_ms"],
            "end": row["end_ms"],
            "text": row["text"],
            "idx": row["idx"],
        }
        if row.get("speaker"):
            seg["speaker"] = row["speaker"]
        if row.get("speaker_label"):
            seg["speaker_label"] = row["speaker_label"]
        segments.append(seg)
    
    return segments


def apply_formatting_to_video(
    conn,
    video_id: str,
    transcript_id: str,
    formatter: TranscriptFormatter,
    config_hash: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Apply formatting to a single video's segments.
    
    Returns:
        dict: Statistics about the operation
    """
    # Load segments
    segments = load_segments_for_video(conn, video_id)
    
    if not segments:
        return {
            "video_id": video_id,
            "status": "skipped",
            "reason": "no segments found",
            "segments_processed": 0,
            "segments_updated": 0,
        }
    
    original_count = len(segments)
    
    # Get language from video metadata if available
    video_info = conn.execute(
        text("SELECT language FROM videos WHERE id = :vid"),
        {"vid": video_id},
    ).mappings().fetchone()
    language = video_info["language"] if video_info else None
    
    # Apply formatting
    try:
        formatted_segments = formatter.format_segments(segments, language=language)
    except Exception as e:
        logger.error(f"Error formatting segments for video {video_id}", extra={"error": str(e)})
        return {
            "video_id": video_id,
            "status": "error",
            "reason": str(e),
            "segments_processed": 0,
            "segments_updated": 0,
        }
    
    formatted_count = len(formatted_segments)
    
    if dry_run:
        logger.info(
            f"[DRY RUN] Would format video {video_id}: {original_count} -> {formatted_count} segments",
            extra={
                "video_id": video_id,
                "original_count": original_count,
                "formatted_count": formatted_count,
            },
        )
        return {
            "video_id": video_id,
            "status": "dry_run",
            "segments_processed": original_count,
            "segments_updated": formatted_count,
        }
    
    # Update segments with cleaned text
    # Match formatted segments back to original segments by timing
    updated_count = 0
    
    # Build a mapping from original segment IDs to formatted text
    # This is complex because formatting can split/merge segments
    # For now, we'll use a simple approach: update original segments with cleaned text
    # where we can match them, and mark cleanup_applied=true
    
    # Create a simple 1:1 mapping based on start time for segments that weren't split
    seg_id_to_formatted = {}
    for orig_seg in segments:
        # Find formatted segment(s) that overlap with this original segment
        matching = [
            f for f in formatted_segments
            if f["start"] <= orig_seg["start"] < f["end"]
        ]
        if matching:
            seg_id_to_formatted[orig_seg["id"]] = matching[0]["text"]
    
    # Update segments in database
    for seg_id, cleaned_text in seg_id_to_formatted.items():
        conn.execute(
            text(
                """
                UPDATE segments
                SET text_cleaned = :cleaned,
                    cleanup_applied = true
                WHERE id = :sid
            """
            ),
            {"sid": seg_id, "cleaned": cleaned_text},
        )
        updated_count += 1
    
    # Update transcript metadata
    cleanup_metadata = {
        "version": FORMATTING_VERSION,
        "config_hash": config_hash,
        "config": formatter.config,
        "applied_at": "now()",
    }
    
    conn.execute(
        text(
            """
            UPDATE transcripts
            SET cleanup_config = :config,
                is_cleaned = true
            WHERE id = :tid
        """
        ),
        {"tid": transcript_id, "config": json.dumps(cleanup_metadata)},
    )
    
    logger.info(
        f"Formatted video {video_id}",
        extra={
            "video_id": video_id,
            "transcript_id": transcript_id,
            "original_segments": original_count,
            "formatted_segments": formatted_count,
            "updated_segments": updated_count,
        },
    )
    
    return {
        "video_id": video_id,
        "status": "success",
        "segments_processed": original_count,
        "segments_updated": updated_count,
    }


def get_videos_to_process(
    conn,
    batch_size: int,
    video_ids: Optional[List[str]] = None,
    channel_name: Optional[str] = None,
    job_id: Optional[str] = None,
) -> List[tuple[str, str]]:
    """
    Get a batch of videos to process.
    
    Returns:
        List of (video_id, transcript_id) tuples
    """
    # Build WHERE clause based on filters
    where_clauses = ["v.state = 'completed'"]
    params = {"limit": batch_size}
    
    if video_ids:
        placeholders = ",".join([f":vid{i}" for i in range(len(video_ids))])
        where_clauses.append(f"v.id IN ({placeholders})")
        for i, vid in enumerate(video_ids):
            params[f"vid{i}"] = vid
    
    if channel_name:
        where_clauses.append("v.channel_name = :channel")
        params["channel"] = channel_name
    
    if job_id:
        where_clauses.append("v.job_id = :job_id")
        params["job_id"] = job_id
    
    where_clause = " AND ".join(where_clauses)
    
    query = f"""
        SELECT v.id as video_id, t.id as transcript_id
        FROM videos v
        INNER JOIN transcripts t ON t.video_id = v.id
        WHERE {where_clause}
        ORDER BY v.created_at ASC
        LIMIT :limit
    """
    
    rows = conn.execute(text(query), params).mappings()
    return [(row["video_id"], row["transcript_id"]) for row in rows]


def run_backfill(
    batch_size: int = 10,
    until_empty: bool = False,
    max_iterations: Optional[int] = None,
    dry_run: bool = False,
    force: bool = False,
    video_ids: Optional[List[str]] = None,
    channel_name: Optional[str] = None,
    job_id: Optional[str] = None,
):
    """
    Run the backfill operation.
    
    Args:
        batch_size: Number of videos to process per iteration
        until_empty: Continue until no more videos to process
        max_iterations: Maximum number of iterations (safety cap)
        dry_run: Preview changes without committing
        force: Force reprocessing even if already formatted
        video_ids: Filter to specific video IDs
        channel_name: Filter to specific channel
        job_id: Filter to specific job ID
    """
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    
    # Get current config
    current_config = get_current_formatting_config()
    current_config_hash = compute_config_hash(current_config)
    
    logger.info(
        "Starting formatting backfill",
        extra={
            "version": FORMATTING_VERSION,
            "config_hash": current_config_hash,
            "batch_size": batch_size,
            "dry_run": dry_run,
            "force": force,
        },
    )
    
    # Create formatter instance
    formatter = TranscriptFormatter(config=current_config)
    
    total_processed = 0
    total_skipped = 0
    total_errors = 0
    iterations = 0
    
    while True:
        iterations += 1
        
        # Get videos to process
        with engine.begin() as conn:
            videos = get_videos_to_process(
                conn,
                batch_size=batch_size,
                video_ids=video_ids,
                channel_name=channel_name,
                job_id=job_id,
            )
        
        if not videos:
            logger.info("No more videos to process")
            break
        
        logger.info(
            f"Processing batch {iterations}",
            extra={"batch_size": len(videos), "iteration": iterations},
        )
        
        # Process each video in the batch
        batch_stats = []
        for video_id, transcript_id in videos:
            # Check if should process
            with engine.begin() as conn:
                should_process, reason = should_process_transcript(
                    conn, transcript_id, current_config_hash, force=force
                )
            
            if not should_process:
                logger.debug(
                    f"Skipping video {video_id}: {reason}",
                    extra={"video_id": video_id, "reason": reason},
                )
                total_skipped += 1
                continue
            
            # Process the video
            with engine.begin() as conn:
                result = apply_formatting_to_video(
                    conn,
                    video_id,
                    transcript_id,
                    formatter,
                    current_config_hash,
                    dry_run=dry_run,
                )
            
            batch_stats.append(result)
            
            if result["status"] == "success" or result["status"] == "dry_run":
                total_processed += 1
            elif result["status"] == "error":
                total_errors += 1
            else:
                total_skipped += 1
        
        logger.info(
            f"Batch {iterations} complete",
            extra={
                "iteration": iterations,
                "videos_in_batch": len(videos),
                "processed": len([s for s in batch_stats if s["status"] in ["success", "dry_run"]]),
                "errors": len([s for s in batch_stats if s["status"] == "error"]),
                "skipped": len([s for s in batch_stats if s["status"] == "skipped"]),
                "total_processed": total_processed,
                "total_skipped": total_skipped,
                "total_errors": total_errors,
            },
        )
        
        # Check stopping conditions
        if not until_empty:
            break
        
        if max_iterations and iterations >= max_iterations:
            logger.info(
                f"Reached max iterations: {max_iterations}",
                extra={"max_iterations": max_iterations},
            )
            break
        
        # If we processed fewer videos than batch size and not filtering by specific IDs,
        # we're probably done
        if len(videos) < batch_size and not video_ids:
            logger.info("Processed partial batch, likely complete")
            break
    
    # Final summary
    logger.info(
        "Formatting backfill complete",
        extra={
            "iterations": iterations,
            "total_processed": total_processed,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "dry_run": dry_run,
        },
    )
    
    return {
        "iterations": iterations,
        "processed": total_processed,
        "skipped": total_skipped,
        "errors": total_errors,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Backfill transcript formatting for existing videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to preview changes
  python scripts/backfill_formatting.py --dry-run --batch 10

  # Process all videos until complete
  python scripts/backfill_formatting.py --until-empty --batch 100

  # Process specific videos
  python scripts/backfill_formatting.py --video-ids UUID1,UUID2,UUID3

  # Filter by channel and process incrementally
  python scripts/backfill_formatting.py --channel-name "My Channel" --batch 50

  # Force reprocess everything (ignore version checks)
  python scripts/backfill_formatting.py --force --until-empty
        """,
    )
    
    parser.add_argument(
        "--batch",
        type=int,
        default=10,
        help="Number of videos to process per batch (default: 10)",
    )
    parser.add_argument(
        "--until-empty",
        action="store_true",
        help="Continue processing batches until no more videos need formatting",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of iterations (safety cap when using --until-empty)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to database",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing even if already formatted with current version",
    )
    parser.add_argument(
        "--video-ids",
        type=str,
        help="Comma-separated list of specific video UUIDs to process",
    )
    parser.add_argument(
        "--channel-name",
        type=str,
        help="Filter to videos from a specific channel",
    )
    parser.add_argument(
        "--job-id",
        type=str,
        help="Filter to videos from a specific job UUID",
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.batch <= 0:
        parser.error("--batch must be positive")
    
    # Parse video IDs if provided
    video_ids = None
    if args.video_ids:
        video_ids = [vid.strip() for vid in args.video_ids.split(",")]
        logger.info(f"Filtering to {len(video_ids)} specific video(s)")
    
    # Run the backfill
    try:
        result = run_backfill(
            batch_size=args.batch,
            until_empty=args.until_empty,
            max_iterations=args.max_iterations,
            dry_run=args.dry_run,
            force=args.force,
            video_ids=video_ids,
            channel_name=args.channel_name,
            job_id=args.job_id,
        )
        
        # Exit with appropriate code
        if result["errors"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"Fatal error during backfill: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
