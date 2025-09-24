import fs from "fs-extra";
import path from "path";
import { Snippet, TranscriptJson } from "./types";

export interface ExportOptions {
  windowSec?: number; // default 20s
}

export async function exportSnippets(
  transcriptPath: string,
  outDir: string,
  opts: ExportOptions = {}
): Promise<string> {
  const windowSec = opts.windowSec ?? 20;
  const t = (await fs.readJson(transcriptPath)) as TranscriptJson;

  // Simple sliding window over segments text for snippet baseline (placeholder)
  const snippets: Snippet[] = [];
  t.segments.forEach((seg, i) => {
    const start = seg.startSec;
    const end = Math.min(seg.endSec, start + windowSec);
    const snippetId = `${t.videoId}-${String(i).padStart(5, "0")}-${Math.round(
      start * 1000
    )}`;
    snippets.push({
      snippetId,
      startSec: start,
      endSec: end,
      text: seg.text,
      speaker: seg.speaker,
    });
  });

  const outPath = path.join(outDir, "snippets.jsonl");
  const lines = snippets.map((s) => JSON.stringify(s));
  await fs.writeFile(outPath, lines.join("\n") + (lines.length ? "\n" : ""));
  return outPath;
}
