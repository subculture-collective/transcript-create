# HasanAra Context

## Domain Terms

- **VOD**: A HasanAbi broadcast video archived from YouTube so it can be searched, quoted, and exported later.
- **Video**: One ingested YouTube item inside HasanAra. A VOD becomes a video record once HasanAra tracks it in the archive.
- **Job**: A user- or system-created ingestion request that tracks work through the archive pipeline.
- **Channel Job**: A job created from a channel URL that expands into many videos instead of one video.
- **Staged Batch**: The set of videos created by a channel job and processed in stages; caption ingest and native transcription may move at different speeds inside the same batch.
- **YouTube Transcript**: The transcript HasanAra imports from YouTube captions when available.
- **Native Transcript**: The transcript HasanAra creates with Whisper from the video audio.
- **Segment**: One timestamped transcript span with text, start/end timing, and any speaker or source metadata.
- **Caption Ingest State**: The current YouTube-caption state for a video, such as waiting, completed, unavailable, or failed.
- **Archive Summary**: The archive landing summary that surfaces recent VODs, popular VODs, and other high-level HasanAra signals.
- **Rolling Mode**: The native transcription mode where Whisper starts on each video as soon as that video reaches a terminal caption state, even while the rest of the batch keeps ingesting captions.

## Archive Context

HasanAra is centered on HasanAbi VODs. When configured, the canonical VOD channels are:

- `@HasanAbiVODs3`
- `@HasanAbiVODsBackup`
- `@HasanAbiVODs`

These channels are context, not an automatic import promise. HasanAra only ingests what the running deployment is configured to pull.
