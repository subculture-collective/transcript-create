import fs from "fs-extra";
import path from "path";
import { Client } from "pg";
import { ENV } from "../pipeline/env";

async function ensureMigrationsTable(client: Client) {
  await client.query(`
    CREATE TABLE IF NOT EXISTS _migrations (
      id SERIAL PRIMARY KEY,
      name TEXT UNIQUE NOT NULL,
      applied_at TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
  `);
}

async function appliedMigrations(client: Client): Promise<Set<string>> {
  const res = await client.query<{ name: string }>(
    "SELECT name FROM _migrations ORDER BY id ASC"
  );
  return new Set(res.rows.map((r: { name: string }) => r.name));
}

async function applyMigration(client: Client, name: string, sql: string) {
  await client.query("BEGIN");
  try {
    await client.query(sql);
    await client.query("INSERT INTO _migrations(name) VALUES($1)", [name]);
    await client.query("COMMIT");
    console.log("Applied", name);
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  }
}

async function main() {
  const client = new Client({ connectionString: ENV.databaseUrl });
  await client.connect();
  await ensureMigrationsTable(client);
  const done = await appliedMigrations(client);

  const dir = path.resolve("db/migrations");
  await fs.ensureDir(dir);
  const files = (await fs.readdir(dir))
    .filter((f: string) => f.endsWith(".sql"))
    .sort();
  for (const f of files) {
    if (done.has(f)) continue;
    const sql = await fs.readFile(path.join(dir, f), "utf8");
    await applyMigration(client, f, sql);
  }
  await client.end();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
