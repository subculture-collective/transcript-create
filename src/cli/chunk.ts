import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import path from "path";
import { ENV } from "../pipeline/env";
import { chunkAudio } from "../pipeline/chunk";

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option("video", { type: "string", demandOption: true })
    .option("audio", { type: "string" })
    .option("dry-run", { type: "boolean", default: true })
    .parse();

  const videoId = String(argv.video);
  const audioPath = String(argv.audio || `artifacts/${videoId}/audio.wav`);
  const outDir = `artifacts/${videoId}`;
  const manifestPath = await chunkAudio(videoId, audioPath, outDir, {
    chunkSec: ENV.chunkSec,
    overlapSec: ENV.overlapSec,
    dryRun: argv["dry-run"],
  });
  console.log("Manifest:", path.resolve(manifestPath));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
