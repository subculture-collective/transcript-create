# ADR-0001: Staged Caption-First Ingestion With Rolling Native Transcription

## Status

Accepted

## Context

HasanAra ingests HasanAbi VODs from YouTube and keeps them searchable as quickly as possible. YouTube captions often arrive before native Whisper transcription, and caption fetches can be rate-limited or temporarily unavailable. The worker also runs on a GTX 1080 deployment where idle GPU time during caption cooldowns is wasteful.

The archive needs a flow that keeps captions moving, builds a searchable archive early, and still produces native transcripts for the final archive record.

## Decision

HasanAra will import YouTube transcripts first.

Native Whisper transcription may start per video in rolling mode once that specific video reaches a terminal caption state: `completed`, `unavailable`, or `failed`.

The remaining videos in the same staged batch may continue caption ingest while native transcription begins on eligible videos.

Rate-limited caption work must not block native transcription forever.

## Consequences

- Faster searchable archive availability.
- Captions can be used for citations and early browsing.
- Rate-limit delays on YouTube captions degrade gracefully instead of stalling the whole batch.
- The GTX 1080 keeps doing useful native work during caption cooldowns.
- Rolling native transcription adds orchestration complexity, but that complexity is worth the throughput and archive latency gains.
