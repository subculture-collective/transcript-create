import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import path from "path";
import { exportSnippets } from "../pipeline/export";

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option("transcript", { type: "string", demandOption: true })
    .option("out", { type: "string", demandOption: true })
    .parse();

  const outPath = await exportSnippets(
    String(argv.transcript),
    String(argv.out)
  );
  console.log("Snippets:", path.resolve(outPath));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
