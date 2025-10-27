"""Example: Export transcripts in different formats."""

import asyncio
import sys
from pathlib import Path
from uuid import UUID

from transcript_create_client import TranscriptClient


async def main() -> None:
    """Main example function."""
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python export_example.py <video_id>")
        print("Example: python export_example.py 123e4567-e89b-12d3-a456-426614174000")
        sys.exit(1)

    try:
        video_id = UUID(sys.argv[1])
    except ValueError:
        print("Error: Invalid video ID format. Must be a valid UUID.")
        sys.exit(1)

    # Create client
    async with TranscriptClient(base_url="http://localhost:8000") as client:
        print(f"Exporting transcript for video: {video_id}")

        # Create output directory
        output_dir = Path("exports")
        output_dir.mkdir(exist_ok=True)

        # Export as SRT
        print("\n1. Exporting as SRT...")
        try:
            srt_content = await client.export_srt(video_id)
            srt_path = output_dir / f"{video_id}.srt"
            srt_path.write_bytes(srt_content)
            print(f"   ✓ Saved to: {srt_path}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")

        # Export as VTT
        print("\n2. Exporting as VTT...")
        try:
            vtt_content = await client.export_vtt(video_id)
            vtt_path = output_dir / f"{video_id}.vtt"
            vtt_path.write_bytes(vtt_content)
            print(f"   ✓ Saved to: {vtt_path}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")

        # Export as PDF
        print("\n3. Exporting as PDF...")
        try:
            pdf_content = await client.export_pdf(video_id)
            pdf_path = output_dir / f"{video_id}.pdf"
            pdf_path.write_bytes(pdf_content)
            print(f"   ✓ Saved to: {pdf_path}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")

        # Also get YouTube captions if available
        print("\n4. Exporting YouTube captions as SRT...")
        try:
            yt_srt = await client.export_srt(video_id, source="youtube")
            yt_srt_path = output_dir / f"{video_id}_youtube.srt"
            yt_srt_path.write_bytes(yt_srt)
            print(f"   ✓ Saved to: {yt_srt_path}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")

        print("\n✓ Export completed!")
        print(f"All files saved to: {output_dir.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())
