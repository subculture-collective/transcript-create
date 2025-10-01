import fs from 'fs';
import path from 'path';
import yargs from 'yargs';
import { hideBin } from 'yargs/helpers';

interface LogEntry { t: string; level: string; msg: string; [k: string]: any }

function tailFile(file: string) {
  let size = 0;
  setInterval(() => {
    try {
      const stat = fs.statSync(file);
      if (stat.size > size) {
        const stream = fs.createReadStream(file, { start: size, end: stat.size });
        stream.on('data', (buf) => process.stdout.write(buf));
        size = stat.size;
      }
    } catch {}
  }, 1500);
}

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option('video', { type: 'string', describe: 'Video ID whose latest run log to show' })
    .option('file', { type: 'string', describe: 'Explicit log file path' })
    .option('level', { type: 'string', describe: 'Min level filter (debug|info|warn|error)' })
    .option('follow', { type: 'boolean', default: false, describe: 'Stream appended lines' })
    .demandOption(['video'], 'Provide --video or --file')
    .parse();

  let file = argv.file as string | undefined;
  if (!file && argv.video) {
    const dir = path.resolve('artifacts', String(argv.video));
    const candidates = fs
      .readdirSync(dir)
      .filter((f) => /^run-\d+\.log$/.test(f))
      .sort()
      .reverse();
    if (!candidates.length) {
      console.error('No run-*.log found for video', argv.video);
      process.exit(1);
    }
    file = path.join(dir, candidates[0]);
  }
  if (!file) {
    console.error('No log file resolved');
    process.exit(1);
  }
  if (!fs.existsSync(file)) {
    console.error('Log file does not exist:', file);
    process.exit(1);
  }
  const min = argv.level || 'debug';
  const order: Record<string, number> = { debug: 10, info: 20, warn: 30, error: 40 };
  const minOrder = order[min] ?? 10;

  const printLine = (line: string) => {
    line = line.trim();
    if (!line) return;
    try {
      const obj: LogEntry = JSON.parse(line);
      if (order[obj.level] >= minOrder) {
        process.stdout.write(line + '\n');
      }
    } catch {
      // pass through raw lines
      process.stdout.write(line + '\n');
    }
  };

  const content = fs.readFileSync(file, 'utf8').split(/\r?\n/);
  content.forEach(printLine);
  if (argv.follow) {
    tailFile(file);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
