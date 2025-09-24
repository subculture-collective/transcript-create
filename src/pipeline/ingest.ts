import fs from "fs-extra";
import path from "path";
import { toVideoId } from "./ids";
import { SourceMeta } from "./types";

export interface IngestOptions {
  artifactsRoot: string;
  force?: boolean;
  dryRun?: boolean;
}

export interface IngestResult {
  videoId: string;
  videoDir: string;
  audioPath: string; // expected audio path
  sourceMetaPath: string;
}

export async function ingest(
  videoOrUrl: string,
  opts: IngestOptions
): Promise<IngestResult> {
  const videoId = toVideoId(videoOrUrl);
  const videoDir = path.join(opts.artifactsRoot, videoId);
  const audioPath = path.join(videoDir, "audio.wav");
  const sourceMetaPath = path.join(videoDir, "source.json");

  await fs.ensureDir(videoDir);

  // If not force and files exist, reuse
  const exists = await fs.pathExists(audioPath);
  if (exists && !opts.force) {
    return { videoId, videoDir, audioPath, sourceMetaPath };
  }

  // Create placeholder source metadata; a later step can update this
  const meta: SourceMeta = { url: videoOrUrl };
  await fs.writeJson(sourceMetaPath, meta, { spaces: 2 });

  // Leave audio download to a future step; for now, create a sentinel file in dry-run
  if (opts.dryRun) {
    await fs.writeFile(audioPath, "");
  }

  return { videoId, videoDir, audioPath, sourceMetaPath };
}
