import * as dotenv from "dotenv";
dotenv.config();

export const ENV = {
  databaseUrl:
    process.env.DATABASE_URL ||
    "postgres://postgres:postgres@localhost:5432/transcripts",
  artifactsRoot: process.env.ARTIFACTS_ROOT || "artifacts",
  chunkSec: Number(process.env.CHUNK_SEC || 1800),
  overlapSec: Number(process.env.OVERLAP_SEC || 8),
  force: (process.env.FORCE || "false") === "true",
};
