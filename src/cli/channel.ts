import fs from 'fs-extra';
import path from 'path';
import yargs from 'yargs';
import { hideBin } from 'yargs/helpers';
import { ENV } from '../pipeline/env';
import { runPipelineForVideo } from '../pipeline/run';
import { listChannelVideoIds } from '../pipeline/ytdlp';

async function main() {
    const argv = await yargs(hideBin(process.argv))
        .option('channel', { type: 'string', demandOption: true })
        .option('limit', { type: 'number' })
        .option('dry-run', { type: 'boolean', default: false })
        .option('force', { type: 'boolean', default: false })
        .option('concurrency', { type: 'number', default: 1 })
        .parse();

    const channel = String(argv.channel);
    const limit = argv.limit as number | undefined;
    const ids = await listChannelVideoIds(channel, { limit });
    console.log(
        `Found ${ids.length} videos. Mode: ${
            argv['dry-run']
                ? 'DRY-RUN (no real downloads or transcription)'
                : 'REAL RUN'
        }`
    );

    const concurrency = Math.max(1, Number(argv.concurrency) || 1);
    let active = 0;
    const queue = [...ids];
    const stats = { processed: 0, skipped: 0, failed: 0 };

    async function worker() {
        while (queue.length) {
            const id = queue.shift();
            if (!id) break;
            const videoDir = path.resolve(ENV.artifactsRoot, id);
            const transcriptPath = path.join(videoDir, 'transcript.json');
            if (!argv.force && (await fs.pathExists(transcriptPath))) {
                console.log(`\n=== Skipping ${id} (transcript exists) ===`);
                stats.skipped++;
                continue;
            }
            console.log(
                `\n=== [${stats.processed + stats.failed + 1}/${
                    ids.length
                }] Processing: ${id} ===\n`
            );
            try {
                await runPipelineForVideo(id, {
                    dryRun: argv['dry-run'],
                    force: argv.force,
                });
                stats.processed++;
            } catch (e) {
                stats.failed++;
                console.error(`Video ${id} failed:`, e);
            }
        }
    }

    const workers: Promise<void>[] = [];
    for (let i = 0; i < concurrency; i++) {
        active++;
        workers.push(
            worker().finally(() => {
                active--;
            })
        );
    }
    await Promise.all(workers);

    console.log(`\n=== Channel Summary ===`);
    console.log(`Total listed: ${ids.length}`);
    console.log(`Processed:    ${stats.processed}`);
    console.log(`Skipped:      ${stats.skipped}`);
    console.log(`Failed:       ${stats.failed}`);
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
