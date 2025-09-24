#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def main():
    # Placeholder runner: reads args but outputs an empty transcript JSON
    if len(sys.argv) < 3:
        print("Usage: whisperx_runner.py <chunk_path> <out_json>")
        sys.exit(1)

    chunk_path = sys.argv[1]
    out_json = sys.argv[2]

    t = {
        "videoId": "TBD",
        "source": {"url": ""},
        "processing": {
            "createdAt": datetime.now().isoformat() + 'Z',
            "engine": "whisperx@TBD",
            "language": "en",
            "chunkSec": 0,
            "overlapSec": 0
        },
        "segments": [],
        "words": [],
        "snippets": []
    }

    with open(out_json, 'w') as f:
        json.dump(t, f)

if __name__ == '__main__':
    main()
