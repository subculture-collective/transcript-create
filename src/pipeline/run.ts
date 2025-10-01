import path from "path";
import { ENV } from "./env";
import { ingest } from "./ingest";
import { chunkAudio } from "./chunk";
import { transcribeChunks } from "./transcribe";
import { exportSnippets } from "./export";
import { withPg, ensureVideo, insertRun, updateRunStatus } from "./run_db";
import { setLogFile, info, warn } from "./log";

export interface RunPipelineOptions {
  dryRun?: boolean;
  force?: boolean;
}

export interface RunPipelineResult {
  manifestPath: string;
  transcriptPath: string;
  snippetsPath: string;
}

export async function runPipelineForVideo(
  videoOrUrl: string,
  opts: RunPipelineOptions = {}
): Promise<RunPipelineResult> {
  const ing = await ingest(videoOrUrl, {
    artifactsRoot: ENV.artifactsRoot,
    force: opts.force ?? ENV.force,
    dryRun: opts.dryRun,
  });
  let runId: string | null = null;
  const runLogPath = path.join(ing.videoDir, `run-${Date.now()}.log`);
  setLogFile(runLogPath);
  const engine = "whisperx@pipeline";
  const language = "en";
  const startTs = Date.now();
  try {
    await withPg(async (c) => {
      await ensureVideo(c, ing.videoId, ing.audioPath);
      runId = await insertRun(
        c,
        ing.videoId,
        engine,
        language,
        ENV.chunkSec,
        ENV.overlapSec,
        opts.dryRun ? "dry-run" : "started"
      );
      info("run.start", { videoId: ing.videoId, runId, log: runLogPath });
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const redacted = ENV.databaseUrl.replace(/:[^:@/]+@/, ':***@');
    warn("run.db.init.fail", { error: msg, dbUrl: redacted, disableDb: ENV.disableDb });
  }
  const manifestPath = await chunkAudio(ing.videoId, ing.audioPath, ing.videoDir, {
    chunkSec: ENV.chunkSec,
    overlapSec: ENV.overlapSec,
    dryRun: opts.dryRun,
  });
  const transcriptPath = await transcribeChunks(manifestPath, ing.videoDir, {
    engine: "whisperx@pipeline",
    language: "en",
    dryRun: opts.dryRun,
  });
  const snippetsPath = await exportSnippets(transcriptPath, ing.videoDir, {
    windowSec: 20,
  });
  const durationMs = Date.now() - startTs;
  info("run.complete", { videoId: ing.videoId, runId, durationMs });
  if (runId) {
    await withPg(async (c) => {
      await updateRunStatus(c, runId!, "completed");
    });
  }
  return { manifestPath, transcriptPath, snippetsPath };
}
