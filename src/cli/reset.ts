import yargs from 'yargs';
import { hideBin } from 'yargs/helpers';
import fs from 'fs-extra';
import path from 'path';
import { ENV } from '../pipeline/env';
import { execa } from 'execa';

/*
 * reset.ts - destructive cleanup utility.
 * By default does NOTHING unless flags provided.
 * Operations:
 *   --artifacts : delete artifacts directory contents
 *   --dist      : delete dist build output
 *   --db        : drop all managed tables (videos, runs, artifacts, _migrations)
 *   --images    : remove local whisperx images matching tag (WHISPERX_IMAGE)
 *   --all       : shorthand for all of the above
 * Safety:
 *   Requires --yes to perform deletions. Otherwise prints plan only.
 */
async function dropDb(databaseUrl: string) {
  const { Client } = await import('pg');
  const client = new Client({ connectionString: databaseUrl });
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('DROP TABLE IF EXISTS artifacts CASCADE');
    await client.query('DROP TABLE IF EXISTS runs CASCADE');
    await client.query('DROP TABLE IF EXISTS videos CASCADE');
    await client.query('DROP TABLE IF EXISTS _migrations CASCADE');
    await client.query('COMMIT');
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    await client.end();
  }
}

async function removeImage(imageTag: string) {
  if (!imageTag) return;
  try {
    await execa('docker', ['image', 'inspect', imageTag]);
  } catch {
    return; // image not present
  }
  await execa('docker', ['rmi', '-f', imageTag]);
}

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option('artifacts', { type: 'boolean', default: false })
    .option('dist', { type: 'boolean', default: false })
    .option('db', { type: 'boolean', default: false })
    .option('images', { type: 'boolean', default: false })
    .option('all', { type: 'boolean', default: false })
    .option('yes', { type: 'boolean', default: false, describe: 'Confirm destructive actions' })
    .help()
    .parse();

  const ops = {
    artifacts: argv.all || argv.artifacts,
    dist: argv.all || argv.dist,
    db: argv.all || argv.db,
    images: argv.all || argv.images,
  };

  const plan: string[] = [];
  if (ops.artifacts) plan.push(`Delete artifacts dir: ${path.resolve(ENV.artifactsRoot)}`);
  if (ops.dist) plan.push('Delete dist/ directory');
  if (ops.db) plan.push('Drop DB tables: videos, runs, artifacts, _migrations');
  if (ops.images) plan.push(`Remove docker image: ${ENV.whisperxImage || '(none set)'}`);

  if (!plan.length) {
    console.log('Nothing selected. Use --all or specific flags (see --help).');
    return;
  }
  console.log('Reset plan:');
  for (const p of plan) console.log(' -', p);

  if (!argv.yes) {
    console.log('\nDry run only. Re-run with --yes to execute.');
    return;
  }

  if (ops.artifacts) {
    await fs.remove(ENV.artifactsRoot);
    await fs.ensureDir(ENV.artifactsRoot);
    console.log('Artifacts cleared.');
  }
  if (ops.dist) {
    await fs.remove('dist');
    console.log('dist/ removed.');
  }
  if (ops.db) {
    try {
      await dropDb(ENV.databaseUrl);
      console.log('Database tables dropped.');
    } catch (e) {
      console.error('DB drop failed:', e);
    }
  }
  if (ops.images && ENV.whisperxImage) {
    try {
      await removeImage(ENV.whisperxImage);
      console.log('Docker image removed.');
    } catch (e) {
      console.error('Image removal failed:', e);
    }
  }
  console.log('Reset complete.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
