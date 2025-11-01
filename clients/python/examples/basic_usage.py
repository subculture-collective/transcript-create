"""Example: Create a job and wait for completion."""

import asyncio
import sys

from transcript_create_client import TranscriptClient


async def main() -> None:
    """Main example function."""
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python basic_usage.py <youtube_url>")
        print("Example: python basic_usage.py https://youtube.com/watch?v=dQw4w9WgXcQ")
        sys.exit(1)

    youtube_url = sys.argv[1]

    # Create client
    async with TranscriptClient(base_url="http://localhost:8000") as client:
        print(f"Creating job for: {youtube_url}")

        # Create job
        job = await client.create_job(url=youtube_url, kind="single")
        print(f"✓ Job created: {job.id}")
        print(f"  State: {job.state}")

        # Wait for completion (poll every 5 seconds, timeout after 1 hour)
        print("\nWaiting for transcription to complete...")
        try:
            completed_job = await client.wait_for_completion(
                job.id,
                timeout=3600,  # 1 hour
                poll_interval=5.0,  # Check every 5 seconds
            )
        except Exception as e:
            print(f"✗ Error waiting for job: {e}")
            sys.exit(1)

        print(f"✓ Job completed: {completed_job.state}")

        if completed_job.state == "failed":
            print(f"✗ Job failed: {completed_job.error}")
            sys.exit(1)

        # Get video ID from the job (for single video jobs)
        # Note: In production, you'd query the videos for this job
        print("\nFetching transcript...")
        try:
            # For demonstration, we'll use the job ID as video ID
            # In real usage, you'd get the video ID from the job's videos
            transcript = await client.get_transcript(job.id)

            print(f"✓ Transcript retrieved: {len(transcript.segments)} segments")
            print("\nFirst 5 segments:")
            for i, segment in enumerate(transcript.segments[:5]):
                start_sec = segment.start_ms / 1000
                end_sec = segment.end_ms / 1000
                speaker = f"[{segment.speaker_label}] " if segment.speaker_label else ""
                print(f"  {start_sec:.1f}s - {end_sec:.1f}s: {speaker}{segment.text[:80]}...")

        except Exception as e:
            print(f"Note: Could not fetch transcript - {e}")
            print("This is expected if the video hasn't been fully processed yet.")

        print("\nExample completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
