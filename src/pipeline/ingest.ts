import { execa } from 'execa';
import fs from 'fs-extra';
import path from 'path';
import { ENV } from './env';
import { toVideoId } from './ids';
import { SourceMeta } from './types';

export interface IngestOptions {
    artifactsRoot: string;
    force?: boolean;
    dryRun?: boolean;
}

export interface IngestResult {
    videoId: string;
    videoDir: string;
    audioPath: string; // expected audio path
    sourceMetaPath: string;
}

export async function ingest(
    videoOrUrl: string,
    opts: IngestOptions
): Promise<IngestResult> {
    const videoId = toVideoId(videoOrUrl);
    // Use absolute path for artifact directory to simplify container volume mapping
    const videoDir = path.resolve(opts.artifactsRoot, videoId);
    const audioPath = path.join(videoDir, 'audio.wav');
    const sourceMetaPath = path.join(videoDir, 'source.json');

    await fs.ensureDir(videoDir);

    // Reuse existing audio unless force OR detected placeholder (size 0 or <1KB)
    const exists = await fs.pathExists(audioPath);
    if (exists && !opts.force) {
        try {
            const st = await fs.stat(audioPath);
            if (st.size === 0) {
                console.log(
                    `[ingest] Detected empty placeholder audio for ${videoId}; re-downloading real audio.`
                );
            } else if (st.size < 1024) {
                console.log(
                    `[ingest] Audio smaller than 1KB (${st.size} bytes) for ${videoId}; treating as placeholder and re-downloading.`
                );
            } else {
                return { videoId, videoDir, audioPath, sourceMetaPath };
            }
        } catch (e) {
            // If stat fails, fall through to download
        }
    }

    // If dry-run just scaffold placeholder files
    if (opts.dryRun) {
        const meta: SourceMeta = { url: videoOrUrl };
        await fs.writeJson(sourceMetaPath, meta, { spaces: 2 });
        await fs.writeFile(audioPath, '');
        return { videoId, videoDir, audioPath, sourceMetaPath };
    }

    // Real run: fetch metadata + audio via yt-dlp
    try {
        // Pull JSON metadata
        let metaJson: string | undefined;
        try {
            const res = await execa(ENV.ytdlpBin, [
                '-J',
                `https://www.youtube.com/watch?v=${videoId}`,
            ]);
            metaJson = res.stdout;
        } catch (e: any) {
            if (e?.code === 'ENOENT') {
                // fallback
                const res2 = await execa('python3', [
                    '-m',
                    'yt_dlp',
                    '-J',
                    `https://www.youtube.com/watch?v=${videoId}`,
                ]);
                metaJson = res2.stdout;
            } else {
                throw e;
            }
        }
        if (!metaJson) throw new Error('Failed to obtain video metadata JSON');
        const parsed = JSON.parse(metaJson);
        const meta: SourceMeta = {
            url: parsed?.webpage_url || videoOrUrl,
            title: parsed?.title,
            channelId: parsed?.channel_id,
            publishedAt: parsed?.upload_date
                ? `${parsed.upload_date.slice(0, 4)}-${parsed.upload_date.slice(
                      4,
                      6
                  )}-${parsed.upload_date.slice(6, 8)}T00:00:00Z`
                : undefined,
            durationSec: parsed?.duration,
        };
        await fs.writeJson(sourceMetaPath, meta, { spaces: 2 });
    } catch (e) {
        // Fallback minimal metadata
        const fallback: SourceMeta = { url: videoOrUrl };
        await fs.writeJson(sourceMetaPath, fallback, { spaces: 2 });
    }

    // Download + convert to wav (mono 16k) using yt-dlp + ffmpeg via postprocessor
    // We let yt-dlp decide bestaudio then extract wav at default rate; re-normalize with ffmpeg after for consistency
    const tempOut = path.join(videoDir, `download.%(ext)s`);
    const ytArgsBase = [
        '-f',
        'bestaudio',
        '-x',
        '--audio-format',
        'wav',
        '-o',
        tempOut,
    ];
    const targetUrl = `https://www.youtube.com/watch?v=${videoId}`;
    const extra: string[] = [];
    if (ENV.ytdlpCookiesFile) {
        extra.push('--cookies', ENV.ytdlpCookiesFile);
    }
    if (ENV.ytdlpUserAgent) {
        extra.push('--user-agent', ENV.ytdlpUserAgent);
    }
    if (ENV.ytdlpExtraArgs) {
        extra.push(
            ...ENV.ytdlpExtraArgs
                .split(' ')
                .map((s) => s.trim())
                .filter(Boolean)
        );
    }
    const ytArgs = [...ytArgsBase, ...extra, targetUrl];

    async function tryCommand(cmd: string, args: string[]) {
        return execa(cmd, args, { stdio: 'pipe' });
    }

    // Preflight: attempt to show version for primary binary to give early helpful error
    try {
        await execa(ENV.ytdlpBin, ['--version']);
    } catch (e: any) {
        // Not fatal; we have fallbacks, but record context
    }

    let downloaded = false;
    const errors: string[] = [];
    const tried: string[] = [];

    const candidates: Array<[string, string[]]> = [];
    // Primary configured binary
    candidates.push([ENV.ytdlpBin, ytArgs]);
    if (ENV.ytdlpBin !== 'yt-dlp') {
        candidates.push(['yt-dlp', ytArgs]);
    }
    // Preferred python interpreter if provided
    if (ENV.ytdlpPythonBin) {
        candidates.push([ENV.ytdlpPythonBin, ['-m', 'yt_dlp', ...ytArgs]]);
    }
    // System python fallback
    candidates.push(['python3', ['-m', 'yt_dlp', ...ytArgs]]);

    for (const [cmd, args] of candidates) {
        if (downloaded) break;
        tried.push(
            cmd === 'python3' && args[0] === '-m' ? 'python3 -m yt_dlp' : cmd
        );
        try {
            await tryCommand(cmd, args);
            downloaded = true;
        } catch (e: any) {
            const msg = e?.stderr || e?.stdout || e?.shortMessage || e?.message || String(e);
            errors.push(`[${cmd}] ${msg}`);
            // Continue to next candidate
        }
    }

    if (!downloaded) {
        throw new Error(
            `All yt-dlp download attempts failed. Tried: ${tried.join(
                ', '
            )}\nErrors:\n${errors.join('\n---\n')}`
        );
    }

    // Find produced wav (yt-dlp names it download.wav)
    const produced = path.join(videoDir, 'download.wav');
    if (!(await fs.pathExists(produced))) {
        throw new Error(
            `Expected yt-dlp output ${produced} was not created. Check yt-dlp availability or network.`
        );
    }
    // Normalize to target spec (mono 16k) into audio.wav
    await execa('ffmpeg', [
        '-y',
        '-i',
        produced,
        '-ac',
        '1',
        '-ar',
        '16000',
        audioPath,
    ]);
    // Optionally remove intermediate file
    await fs.remove(produced);

    return { videoId, videoDir, audioPath, sourceMetaPath };
}
