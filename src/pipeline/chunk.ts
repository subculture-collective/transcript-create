import fs from "fs-extra";
import path from "path";
import { ChunkManifest } from "./types";

export interface ChunkOptions {
  chunkSec: number;
  overlapSec: number;
  dryRun?: boolean;
}

export async function chunkAudio(
  videoId: string,
  audioPath: string,
  outDir: string,
  opts: ChunkOptions
): Promise<string> {
  const manifest: ChunkManifest = {
    videoId,
    audioPath,
    chunkSec: opts.chunkSec,
    overlapSec: opts.overlapSec,
    chunks: [],
  };

  // In dry run we do not actually split; we create an empty manifest
  // Real implementation will probe duration and produce deterministic chunks with overlap
  const manifestPath = path.join(outDir, "manifest.json");
  await fs.writeJson(manifestPath, manifest, { spaces: 2 });
  return manifestPath;
}
