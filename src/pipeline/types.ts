export type ISO8601 = string;

export interface SourceMeta {
  url: string;
  title?: string;
  channelId?: string;
  publishedAt?: ISO8601;
  durationSec?: number;
}

export interface ProcessingConfig {
  createdAt: ISO8601;
  engine: string;
  language: string;
  chunkSec: number;
  overlapSec: number;
}

export interface Segment {
  startSec: number;
  endSec: number;
  text: string;
  speaker?: string;
}

export interface Word {
  startSec: number;
  endSec: number;
  text: string;
  speaker?: string;
}

export interface Snippet {
  snippetId: string;
  startSec: number;
  endSec: number;
  text: string;
  speaker?: string;
}

export interface TranscriptJson {
  videoId: string;
  source: SourceMeta;
  processing: ProcessingConfig;
  segments: Segment[];
  words: Word[];
  snippets: Snippet[];
}

export interface ChunkInfo {
  chunkIndex: number;
  path: string;
  globalStart: number;
  globalEnd: number;
}

export interface ChunkManifest {
  videoId: string;
  audioPath: string;
  chunkSec: number;
  overlapSec: number;
  chunks: ChunkInfo[];
}
