import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import path from "path";
import { ENV } from "../pipeline/env";
import { ingest } from "../pipeline/ingest";

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option("video", { type: "string", demandOption: true })
    .option("dry-run", { type: "boolean", default: true })
    .option("force", { type: "boolean", default: ENV.force })
    .parse();

  const res = await ingest(argv.video, {
    artifactsRoot: ENV.artifactsRoot,
    force: argv.force,
    dryRun: argv["dry-run"],
  });
  console.log(JSON.stringify(res, null, 2));
  console.log("Artifacts dir:", path.resolve(res.videoDir));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
