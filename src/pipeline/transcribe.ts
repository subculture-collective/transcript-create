import fs from "fs-extra";
import path from "path";
import { ChunkManifest, TranscriptJson } from "./types";

export interface TranscribeOptions {
  language?: string;
  engine?: string; // e.g., whisperx@large-v3
  dryRun?: boolean;
}

export async function transcribeChunks(
  manifestPath: string,
  outDir: string,
  opts: TranscribeOptions
): Promise<string> {
  const manifest = (await fs.readJson(manifestPath)) as ChunkManifest;

  const transcript: TranscriptJson = {
    videoId: manifest.videoId,
    source: { url: "" },
    processing: {
      createdAt: new Date().toISOString(),
      engine: opts.engine || "whisperx@TBD",
      language: opts.language || "en",
      chunkSec: manifest.chunkSec,
      overlapSec: manifest.overlapSec,
    },
    segments: [],
    words: [],
    snippets: [],
  };

  const transcriptPath = path.join(outDir, "transcript.json");
  await fs.writeJson(transcriptPath, transcript, { spaces: 2 });
  return transcriptPath;
}
