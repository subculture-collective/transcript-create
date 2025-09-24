# transcript-create (scaffold)

Local, GPU-accelerated pipeline to generate canonical transcripts from long YouTube livestreams. TypeScript orchestrates; WhisperX runs in Docker (ROCm for AMD, CPU fallback). Postgres stores run/video metadata; large artifacts live on the filesystem.

Quick start

- Prereqs: Docker, Node 18+, ffmpeg, yt-dlp, Postgres (via docker compose).
- Copy .env.example to .env and adjust as needed.

Dev flow

1. Install deps: npm install
2. Start Postgres: docker compose -f docker/compose.yaml up -d db
3. Build TS: npm run build
4. Run migrations: npm run migrate
5. Dry run end-to-end: npm run transcribe -- --video <id|url> --dry-run

AMD GPU (ROCm) notes

- Default target: ROCm 6.0 container. Adjust base image tag if your host uses a different ROCm version.
- For AMD GPU pass-through, you’ll typically map /dev/kfd and /dev/dri and add the container user to video/render groups (see Dockerfile comments).

CPU fallback

- Build docker/whisperx.cpu.Dockerfile and run the same orchestration; performance will be limited but useful for debugging.
