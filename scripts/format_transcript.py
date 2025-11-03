#!/usr/bin/env python3
"""
CLI utility for formatting transcripts offline.

Supports:
- Reading from database by video ID
- Reading from JSON file
- Applying configurable formatting transformations
- Output to stdout or file

Usage:
    # Format from database
    python scripts/format_transcript.py --video-id UUID

    # Format from JSON file
    python scripts/format_transcript.py --input segments.json --output formatted.json

    # Disable specific transformations
    python scripts/format_transcript.py --input segments.json --no-punctuation --no-fillers

    # Use custom config
    python scripts/format_transcript.py --input segments.json --config config.json
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.settings import settings
from worker.formatter import TranscriptFormatter, format_transcript


def load_segments_from_file(filepath: str) -> List[Dict[str, Any]]:
    """Load segments from JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both list of segments and wrapped format
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "segments" in data:
        return data["segments"]
    else:
        raise ValueError("Invalid JSON format. Expected list of segments or dict with 'segments' key.")


def load_segments_from_db(video_id: str) -> List[Dict[str, Any]]:
    """Load segments from database by video ID."""
    engine = create_engine(settings.DATABASE_URL.replace("+psycopg", ""))

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
            SELECT start_ms, end_ms, text, speaker, speaker_label
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
                "start": row["start_ms"],
                "end": row["end_ms"],
                "text": row["text"],
            }
            if row.get("speaker"):
                seg["speaker"] = row["speaker"]
            if row.get("speaker_label"):
                seg["speaker_label"] = row["speaker_label"]
            segments.append(seg)

        return segments


def save_segments(segments: List[Dict[str, Any]], output_path: Optional[str] = None, format: str = "json"):
    """Save formatted segments to file or stdout."""
    if format == "json":
        output = json.dumps({"segments": segments}, indent=2, ensure_ascii=False)
    elif format == "text":
        lines = []
        for seg in segments:
            start_s = seg["start"] / 1000
            end_s = seg["end"] / 1000
            text = seg["text"]
            lines.append(f"[{start_s:.2f}s - {end_s:.2f}s] {text}")
        output = "\n".join(lines)
    elif format == "srt":
        lines = []
        for i, seg in enumerate(segments, start=1):
            start_ms = seg["start"]
            end_ms = seg["end"]
            text = seg["text"]

            # Format timestamps as HH:MM:SS,mmm
            def fmt_time(ms):
                s, ms_rem = divmod(ms, 1000)
                h, s = divmod(s, 3600)
                m, s = divmod(s, 60)
                return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

            lines.append(str(i))
            lines.append(f"{fmt_time(start_ms)} --> {fmt_time(end_ms)}")
            lines.append(text)
            lines.append("")
        output = "\n".join(lines)
    else:
        raise ValueError(f"Unknown format: {format}")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved formatted transcript to {output_path}", file=sys.stderr)
    else:
        print(output)


def build_config_from_args(args) -> Dict[str, Any]:
    """Build configuration dict from command line arguments."""
    config = {}

    # Load base config from file if provided
    if args.config:
        with open(args.config, "r") as f:
            config = json.load(f)

    # Override with command line flags
    if args.no_normalization:
        config["normalize_unicode"] = False
        config["normalize_whitespace"] = False

    if args.no_punctuation:
        config["punctuation_mode"] = "none"
        config["add_sentence_punctuation"] = False
        config["add_internal_punctuation"] = False
        config["capitalize_sentences"] = False

    if args.no_fillers:
        config["remove_fillers"] = False

    if args.no_segmentation:
        config["segment_by_sentences"] = False
        config["merge_short_segments"] = False

    if args.speaker_format:
        config["speaker_format"] = args.speaker_format

    if args.filler_level is not None:
        config["filler_level"] = args.filler_level

    # If no overrides, return None to use defaults
    return config if config else None


def main():
    parser = argparse.ArgumentParser(
        description="Format transcript segments with configurable transformations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Format from database
  python scripts/format_transcript.py --video-id a1b2c3d4-e5f6-7890-abcd-ef1234567890

  # Format from JSON file
  python scripts/format_transcript.py --input segments.json

  # Output to file in SRT format
  python scripts/format_transcript.py --input segments.json --output formatted.srt --format srt

  # Disable punctuation and fillers
  python scripts/format_transcript.py --input segments.json --no-punctuation --no-fillers

  # Use custom speaker format
  python scripts/format_transcript.py --input segments.json --speaker-format dialogue
        """,
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--video-id", help="Video UUID to load from database")
    input_group.add_argument("--input", "-i", help="Input JSON file with segments")

    # Output options
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "text", "srt"],
        default="json",
        help="Output format (default: json)",
    )

    # Configuration options
    parser.add_argument("--config", "-c", help="JSON config file to override settings")
    parser.add_argument("--language", "-l", help="Language code for language-specific rules")

    # Transformation toggles
    parser.add_argument("--no-normalization", action="store_true", help="Disable Unicode and whitespace normalization")
    parser.add_argument("--no-punctuation", action="store_true", help="Disable punctuation restoration")
    parser.add_argument("--no-fillers", action="store_true", help="Disable filler word removal")
    parser.add_argument("--no-segmentation", action="store_true", help="Disable sentence segmentation and merging")
    parser.add_argument(
        "--speaker-format",
        choices=["inline", "dialogue", "structured"],
        help="Speaker label format",
    )
    parser.add_argument(
        "--filler-level",
        type=int,
        choices=[0, 1, 2, 3],
        help="Filler removal aggressiveness (0=off, 1=conservative, 2=moderate, 3=aggressive)",
    )

    # Verbosity
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Load segments
    try:
        if args.video_id:
            if args.verbose:
                print(f"Loading segments from database for video {args.video_id}...", file=sys.stderr)
            segments = load_segments_from_db(args.video_id)
        else:
            if args.verbose:
                print(f"Loading segments from {args.input}...", file=sys.stderr)
            segments = load_segments_from_file(args.input)

        if args.verbose:
            print(f"Loaded {len(segments)} segments", file=sys.stderr)

    except Exception as e:
        print(f"Error loading segments: {e}", file=sys.stderr)
        sys.exit(1)

    # Build config
    config = build_config_from_args(args)

    # Format segments
    try:
        if args.verbose:
            print("Formatting segments...", file=sys.stderr)

        formatted = format_transcript(segments, language=args.language, config=config)

        if args.verbose:
            print(f"Formatted {len(formatted)} segments", file=sys.stderr)

    except Exception as e:
        print(f"Error formatting segments: {e}", file=sys.stderr)
        sys.exit(1)

    # Save output
    try:
        save_segments(formatted, args.output, format=args.format)
    except Exception as e:
        print(f"Error saving output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
