/* Lightweight structured logger with step timing & ETA */
import { performance } from 'perf_hooks';
import fs from 'fs';
import path from 'path';

interface InternalConfig {
  format: 'json' | 'pretty';
  progressIntervalMs: number;
}

export type LogLevel = "debug" | "info" | "warn" | "error";

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

let currentLevel: LogLevel = (process.env.LOG_LEVEL as LogLevel) || 'info';
const config: InternalConfig = {
  format: (process.env.LOG_FORMAT as any) === 'pretty' ? 'pretty' : 'json',
  progressIntervalMs: Number(process.env.PROGRESS_INTERVAL_MS || 1500),
};
export function setLogLevel(l: LogLevel) {
  currentLevel = l;
}

function ts() { return new Date().toISOString(); }

export interface StepTimer {
  end: () => void;
  eta: (done: number, total: number) => void;
}

function color(level: LogLevel, s: string) {
  if (config.format !== 'pretty') return s;
  const map: Record<LogLevel, string> = {
    debug: '\u001b[90m',
    info: '\u001b[36m',
    warn: '\u001b[33m',
    error: '\u001b[31m',
  };
  const reset = '\u001b[0m';
  return map[level] + s + reset;
}

const lastProgress: Record<string, number> = {};
let logFilePath: string | null = null;
let logFileFd: number | null = null;

export function setLogFile(filePath: string) {
  try {
    if (logFileFd) {
      fs.closeSync(logFileFd);
      logFileFd = null;
    }
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    logFileFd = fs.openSync(filePath, 'a');
    logFilePath = filePath;
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('Failed to open log file', filePath, e);
  }
}

export function log(level: LogLevel, msg: string, meta?: Record<string, any>) {
  if (LEVEL_ORDER[level] < LEVEL_ORDER[currentLevel]) return;
  const payload = { t: ts(), level, msg, ...(meta || {}) };
  if (config.format === 'json') {
    // eslint-disable-next-line no-console
    console.log(JSON.stringify(payload));
    if (logFileFd) {
      fs.writeSync(logFileFd, JSON.stringify(payload) + '\n');
    }
  } else {
    const base = `${payload.t} ${level.toUpperCase()} ${msg}`;
    const rest = { ...payload } as any;
    delete rest.t; delete rest.level; delete rest.msg;
    const metaStr = Object.keys(rest).length ? ' ' + JSON.stringify(rest) : '';
    // eslint-disable-next-line no-console
    console.log(color(level, base) + metaStr);
    if (logFileFd) {
      fs.writeSync(logFileFd, JSON.stringify(payload) + '\n');
    }
  }
}

export function shouldEmitProgress(key: string) {
  const now = performance.now();
  const last = lastProgress[key] || 0;
  if (now - last < config.progressIntervalMs) return false;
  lastProgress[key] = now;
  return true;
}

export function debug(msg: string, meta?: Record<string, any>) {
  log("debug", msg, meta);
}
export function info(msg: string, meta?: Record<string, any>) {
  log("info", msg, meta);
}
export function warn(msg: string, meta?: Record<string, any>) {
  log("warn", msg, meta);
}
export function error(msg: string, meta?: Record<string, any>) {
  log("error", msg, meta);
}

export function startStep(name: string, meta?: Record<string, any>): StepTimer {
  const start = performance.now();
  info(`start:${name}`, meta);
  return {
    end: () => {
      const durMs = performance.now() - start;
      info(`end:${name}`, { ms: Math.round(durMs), ...meta });
    },
    eta: (done: number, total: number) => {
      if (total <= 0) return;
      const elapsed = performance.now() - start;
      const rate = done > 0 ? elapsed / done : 0;
      const remaining = done > 0 ? rate * (total - done) : 0;
      if (shouldEmitProgress(name)) {
        info(`progress:${name}`, {
          done,
          total,
          pct: Number(((done / total) * 100).toFixed(2)),
          etaMs: Math.round(remaining),
        });
      }
    },
  };
}
