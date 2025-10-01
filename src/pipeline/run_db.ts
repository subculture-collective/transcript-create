import { Client } from 'pg';
import { ENV } from './env';
import { warn, debug } from './log';

export interface RunRecord {
  id: string;
  video_id: string;
  engine: string;
  language: string;
  chunk_sec: number;
  overlap_sec: number;
  status: string;
  created_at?: string;
}

export async function withPg<T>(fn: (c: Client) => Promise<T>): Promise<T> {
  if (ENV.disableDb) {
    warn('db.disabled', { reason: 'DISABLE_DB true' });
    // Execute callback with a proxy that throws on any property access to surface accidental usage.
    const dummy = new Proxy({}, {
      get() { throw new Error('DB disabled (DISABLE_DB=true): client not available'); }
    }) as Client;
    return await fn(dummy);
  }
  const client = new Client({ connectionString: ENV.databaseUrl });
  try {
    await client.connect();
  } catch (e: any) {
    const msg = e?.message || String(e);
    warn('db.connect.fail', { url: ENV.databaseUrl, error: msg });
    throw e;
  }
  try {
    return await fn(client);
  } finally {
    try { await client.end(); } catch (e: any) { debug('db.end.fail', { error: e?.message || String(e) }); }
  }
}

export async function ensureVideo(client: Client, videoId: string, url?: string) {
  await client.query(
    `INSERT INTO videos (id, url) VALUES ($1,$2) ON CONFLICT (id) DO NOTHING`,
    [videoId, url || null]
  );
}

export async function insertRun(
  client: Client,
  videoId: string,
  engine: string,
  language: string,
  chunkSec: number,
  overlapSec: number,
  status: string
): Promise<string> {
  const res = await client.query<{ id: string }>(
    `INSERT INTO runs (video_id, engine, language, chunk_sec, overlap_sec, status)
     VALUES ($1,$2,$3,$4,$5,$6) RETURNING id`,
    [videoId, engine, language, chunkSec, overlapSec, status]
  );
  return res.rows[0].id;
}

export async function updateRunStatus(
  client: Client,
  runId: string,
  status: string
) {
  await client.query(`UPDATE runs SET status=$2 WHERE id=$1`, [runId, status]);
}
