"""Example: Search transcripts."""

import asyncio
import sys

from transcript_create_client import TranscriptClient


async def main() -> None:
    """Main example function."""
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python search_example.py <search_query>")
        print('Example: python search_example.py "machine learning"')
        sys.exit(1)

    query = sys.argv[1]

    # Create client
    async with TranscriptClient(base_url="http://localhost:8000") as client:
        print(f"Searching for: {query}")

        # Search native transcripts
        try:
            results = await client.search(
                query=query,
                source="native",
                limit=10,
            )

            print(f"\n✓ Found {results.total or len(results.hits)} results")
            if results.query_time_ms:
                print(f"  Query time: {results.query_time_ms}ms")

            print("\nTop results:")
            for i, hit in enumerate(results.hits[:10], 1):
                start_sec = hit.start_ms / 1000
                end_sec = hit.end_ms / 1000
                print(f"\n{i}. Video: {hit.video_id}")
                print(f"   Time: {start_sec:.1f}s - {end_sec:.1f}s")
                print(f"   {hit.snippet}")

        except Exception as e:
            print(f"✗ Search failed: {e}")
            sys.exit(1)

        print("\n✓ Example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
