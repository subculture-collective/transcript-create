import { execa } from 'execa';
import fs from 'fs-extra';
import path from 'path';
import { ENV } from './env';
import { ChunkManifest, Segment, TranscriptJson, Word } from './types';
import { info, warn, startStep, debug } from './log';

// Global semaphore (best-effort) limiting concurrent chunk containers across all videos
let GLOBAL_ACTIVE = 0;
const GLOBAL_WAITERS: Array<() => void> = [];

async function acquireGlobal(videoId: string) {
    const limit = ENV.transcribeGlobalConcurrency;
    if (!limit || limit <= 0) return;
    if (GLOBAL_ACTIVE < limit) {
        GLOBAL_ACTIVE++;
        debug('transcribe.global.acquire', { videoId, active: GLOBAL_ACTIVE, limit });
        return;
    }
    await new Promise<void>((resolve) => {
        GLOBAL_WAITERS.push(() => {
            GLOBAL_ACTIVE++;
            debug('transcribe.global.acquire.waited', { videoId, active: GLOBAL_ACTIVE, limit });
            resolve();
        });
    });
}
function releaseGlobal(videoId: string) {
    const limit = ENV.transcribeGlobalConcurrency;
    if (!limit || limit <= 0) return;
    GLOBAL_ACTIVE = Math.max(0, GLOBAL_ACTIVE - 1);
    const next = GLOBAL_WAITERS.shift();
    if (next) next(); else debug('transcribe.global.release', { videoId, active: GLOBAL_ACTIVE, limit });
}

export interface TranscribeOptions {
    language?: string;
    engine?: string; // e.g., whisperx@large-v3
    dryRun?: boolean;
}

export async function transcribeChunks(
    manifestPath: string,
    outDir: string,
    opts: TranscribeOptions
): Promise<string> {
    const manifest = (await fs.readJson(manifestPath)) as ChunkManifest;
    info('transcribe.manifest.load', { videoId: manifest.videoId, chunks: manifest.chunks.length });
    await fs.ensureDir(outDir);

    // Dry-run: write well-formed empty transcript
    if (opts.dryRun || manifest.chunks.length === 0) {
        const transcript: TranscriptJson = {
            videoId: manifest.videoId,
            source: { url: '' },
            processing: {
                createdAt: new Date().toISOString(),
                engine: opts.engine || 'whisperx@TBD',
                language: opts.language || 'en',
                chunkSec: manifest.chunkSec,
                overlapSec: manifest.overlapSec,
            },
            segments: [],
            words: [],
            snippets: [],
        };
        const transcriptPath = path.join(outDir, 'transcript.json');
        info('transcribe.dryRun', { videoId: manifest.videoId });
        await fs.writeJson(transcriptPath, transcript, { spaces: 2 });
        return transcriptPath;
    }

    const perChunkJson: string[] = [];

    if (!ENV.whisperxImage) {
        throw new Error(
            'WHISPERX_IMAGE is required for GPU/docker execution. Set it in your .env.'
        );
    }
    info('transcribe.init', { videoId: manifest.videoId, image: ENV.whisperxImage });

    const forcingCpu = ((process.env.WHISPERX_FORCE_CPU || '').toLowerCase() in {
        '1': true,
        true: true,
        yes: true,
        on: true,
    }) as any;
    let additionalArgs = ENV.dockerAdditionalArgs
        ? ENV.dockerAdditionalArgs.split(' ').filter(Boolean)
        : [];
    if (forcingCpu) {
        additionalArgs = additionalArgs.filter(
            (a) => !['/dev/kfd', '/dev/dri'].includes(a) && a !== '--device'
        );
    }

    // Preflight: ensure image exists locally (avoid confusing pull errors for local tags)
    try {
        await execa(ENV.dockerBin, ['image', 'inspect', ENV.whisperxImage]);
    } catch {
        throw new Error(
            `Docker image ${ENV.whisperxImage} not found locally. Build it first, e.g.:\n` +
            (ENV.whisperxImage.endsWith(':cpu')
                ? `  docker build -f docker/whisperx.cpu.Dockerfile -t ${ENV.whisperxImage} .`
                : `  docker build -f docker/whisperx.rocm.Dockerfile -t ${ENV.whisperxImage} .`)
        );
    }

    // Health check container using full .env passthrough (skippable)
    const skipHealth = (process.env.SKIP_HEALTH_CHECK || '').toLowerCase() in { '1': true, 'true': true, yes: true };
    if (skipHealth) {
        info('transcribe.health.skip', { videoId: manifest.videoId });
    } else {
        try {
            const envFile = path.resolve('.env');
            const hcArgs = [
                'run',
                '--rm',
                ...additionalArgs,
                ...(await fs.pathExists(envFile) ? ['--env-file', envFile] : []),
                '-v', `${path.resolve(ENV.artifactsRoot)}:${path.resolve(ENV.artifactsRoot)}`,
                ENV.whisperxImage,
                '--health',
            ];
            const { stdout } = await execa(ENV.dockerBin, hcArgs);
            info('transcribe.health', { videoId: manifest.videoId, raw: stdout });
        } catch (e: any) {
            warn('transcribe.health.fail', {
                videoId: manifest.videoId,
                exitCode: e?.exitCode,
                shortMessage: e?.shortMessage,
                stderrSnippet: (e?.stderr || '').slice(-800),
                stdoutSnippet: (e?.stdout || '').slice(-400),
            });
            throw new Error(`Failed to start WhisperX container (exit ${e?.exitCode}). See transcribe.health.fail log for details.`);
        }
    }
    const runTimer = startStep('transcribe.chunks', { videoId: manifest.videoId, total: manifest.chunks.length });
    let processed = 0;
    const concurrency = Number(process.env.TRANSCRIBE_CONCURRENCY || 1) || 1;
    const queue = [...manifest.chunks];
    const active: Promise<void>[] = [];
    

    async function runOne(chunkIndex: number) {
        const chunk = queue[chunkIndex];
        if (!chunk) return;
        const chunkOut = path.resolve(
            outDir,
            `chunk_${String(chunk.chunkIndex).padStart(4, '0')}.json`
        );
        if (!(await fs.pathExists(chunkOut)) || ENV.force) {
            info('transcribe.chunk.start', { videoId: manifest.videoId, idx: chunk.chunkIndex, path: chunk.path });
            const envFile = path.resolve('.env');
            const args = [
                'run','--rm',
                ...additionalArgs,
                ...(await fs.pathExists(envFile) ? ['--env-file', envFile] : []),
                '-v', `${path.resolve(ENV.artifactsRoot)}:${path.resolve(ENV.artifactsRoot)}`,
                ENV.whisperxImage,
                chunk.path,
                chunkOut,
            ];
            const maxAttempts = Math.max(0, ENV.transcribeRetries) + 1;
            for (let attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    await acquireGlobal(manifest.videoId);
                    const proc = execa(ENV.dockerBin, args, { all: true });
                    const timeoutSec = ENV.transcribeChunkTimeoutSec;
                    let timeoutHandle: NodeJS.Timeout | null = null;
                    if (timeoutSec && timeoutSec > 0) {
                        timeoutHandle = setTimeout(() => {
                            if (!proc.killed) {
                                proc.kill('SIGKILL');
                                warn('transcribe.chunk.timeout', { videoId: manifest.videoId, idx: chunk.chunkIndex, attempt, timeoutSec });
                            }
                        }, timeoutSec * 1000);
                    }
                    proc.all?.on('data', (d: Buffer) => {
                        const line = d.toString().trim();
                        if (!line) return;
                        debug('transcribe.chunk.log', { videoId: manifest.videoId, idx: chunk.chunkIndex, line });
                    });
                    await proc;
                    if (timeoutHandle) clearTimeout(timeoutHandle);
                    info('transcribe.chunk.done', { videoId: manifest.videoId, idx: chunk.chunkIndex, attempt });
                    releaseGlobal(manifest.videoId);
                    break; // success
                } catch (e: any) {
                    const errorMsg = e?.shortMessage || String(e);
                    warn('transcribe.chunk.fail', {
                        videoId: manifest.videoId,
                        idx: chunk.chunkIndex,
                        attempt,
                        error: errorMsg,
                        exitCode: e?.exitCode,
                        stderrSnippet: (e?.stderr || '').slice(-400),
                        stdoutSnippet: (e?.stdout || '').slice(-200),
                    });
                    releaseGlobal(manifest.videoId);
                    if (attempt === maxAttempts) {
                        warn('transcribe.chunk.giveup', { videoId: manifest.videoId, idx: chunk.chunkIndex });
                        return; // give up on this chunk
                    }
                    const backoff = ENV.transcribeRetryBaseMs * Math.pow(2, attempt - 1);
                    await new Promise((r) => setTimeout(r, backoff));
                }
            }
        }
        perChunkJson.push(chunkOut);
        processed += 1;
        runTimer.eta(processed, manifest.chunks.length);
    }

    async function schedule() {
        let idx = 0;
        while (idx < manifest.chunks.length) {
            while (active.length < concurrency && idx < manifest.chunks.length) {
                const p = runOne(idx).finally(() => {
                    const pos = active.indexOf(p);
                    if (pos >= 0) active.splice(pos, 1);
                });
                active.push(p);
                idx++;
            }
            if (active.length) await Promise.race(active);
        }
        await Promise.all(active);
    }

    await schedule();
    runTimer.end();

    // Merge per-chunk JSON into global transcript
    const allSegments: Segment[] = [];
    const allWords: Word[] = [];
    const mergeTimer = startStep('transcribe.merge', { parts: perChunkJson.length });
    for (const p of perChunkJson) {
        try {
            const t = (await fs.readJson(p)) as TranscriptJson;
            // Apply global offset based on the filename's chunk index mapping back to manifest
            const idx = Number(path.basename(p).match(/(\d+)/)?.[0] || 0);
            const offset = manifest.chunks[idx]?.globalStart ?? 0;
            if (Array.isArray(t.segments)) {
                for (const s of t.segments) {
                    allSegments.push({
                        ...s,
                        startSec: (s.startSec ?? 0) + offset,
                        endSec: (s.endSec ?? 0) + offset,
                    });
                }
            }
            if (Array.isArray(t.words)) {
                for (const w of t.words) {
                    allWords.push({
                        ...w,
                        startSec: (w.startSec ?? 0) + offset,
                        endSec: (w.endSec ?? 0) + offset,
                    });
                }
            }
        } catch (e) {
            warn('transcribe.merge.skip', { file: p, error: e instanceof Error ? e.message : String(e) });
        }
    }
    mergeTimer.end();

    // Naive sort to ensure chronological order
    allSegments.sort((a, b) => a.startSec - b.startSec);
    allWords.sort((a, b) => a.startSec - b.startSec);

    const transcript: TranscriptJson = {
        videoId: manifest.videoId,
        source: { url: '' },
        processing: {
            createdAt: new Date().toISOString(),
            engine:
                opts.engine ||
                (ENV.whisperxImage
                    ? `docker:${ENV.whisperxImage}`
                    : 'whisperx@local'),
            language: opts.language || 'en',
            chunkSec: manifest.chunkSec,
            overlapSec: manifest.overlapSec,
        },
        segments: allSegments,
        words: allWords,
        snippets: [],
    };

    const transcriptPath = path.join(outDir, 'transcript.json');
    await fs.writeJson(transcriptPath, transcript, { spaces: 2 });
    info('transcribe.complete', { videoId: manifest.videoId, segments: allSegments.length, words: allWords.length, path: transcriptPath });
    return transcriptPath;
}
