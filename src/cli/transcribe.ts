import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import path from "path";
import { ENV } from "../pipeline/env";
import { ingest } from "../pipeline/ingest";
import { chunkAudio } from "../pipeline/chunk";
import { transcribeChunks } from "../pipeline/transcribe";
import { exportSnippets } from "../pipeline/export";

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option("video", { type: "string", demandOption: true })
    .option("dry-run", { type: "boolean", default: true })
    .option("force", { type: "boolean", default: ENV.force })
    .parse();

  const ing = await ingest(argv.video, {
    artifactsRoot: ENV.artifactsRoot,
    force: argv.force,
    dryRun: argv["dry-run"],
  });
  const manifestPath = await chunkAudio(
    ing.videoId,
    ing.audioPath,
    ing.videoDir,
    {
      chunkSec: ENV.chunkSec,
      overlapSec: ENV.overlapSec,
      dryRun: argv["dry-run"],
    }
  );
  const transcriptPath = await transcribeChunks(manifestPath, ing.videoDir, {
    engine: "whisperx@TBD",
    language: "en",
    dryRun: argv["dry-run"],
  });
  const snippetsPath = await exportSnippets(transcriptPath, ing.videoDir, {
    windowSec: 20,
  });

  console.log("Artifacts:");
  console.log(" - manifest:", path.resolve(manifestPath));
  console.log(" - transcript:", path.resolve(transcriptPath));
  console.log(" - snippets:", path.resolve(snippetsPath));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
