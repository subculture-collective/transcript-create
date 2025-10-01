import { execa } from 'execa';
import fs from 'fs-extra';
import path from 'path';
import { ChunkInfo, ChunkManifest } from './types';
import { info, startStep } from './log';

export interface ChunkOptions {
    chunkSec: number;
    overlapSec: number;
    dryRun?: boolean;
}

export async function chunkAudio(
    videoId: string,
    audioPath: string,
    outDir: string,
    opts: ChunkOptions
): Promise<string> {
    await fs.ensureDir(outDir);

    // Validate input presence (size check deferred until after dry-run branch)
    if (!(await fs.pathExists(audioPath))) {
        throw new Error(
            `Input audio not found: ${audioPath}. Expected a real WAV file at artifacts/${videoId}/audio.wav. ` +
                `If you previously ran with --dry-run, replace the placeholder and rerun with --force.`
        );
    }

    const manifest: ChunkManifest = {
        videoId,
        audioPath,
        chunkSec: opts.chunkSec,
        overlapSec: opts.overlapSec,
        chunks: [],
    };

    if (opts.dryRun) {
        info('chunk.dryRun', { videoId, chunkSec: opts.chunkSec, overlapSec: opts.overlapSec });
        const manifestPath = path.join(outDir, 'manifest.json');
        await fs.writeJson(manifestPath, manifest, { spaces: 2 });
        return manifestPath;
    }

    // Now enforce non-empty audio for real runs
    const stat = await fs.stat(audioPath);
    if (stat.size === 0) {
        throw new Error(
            `Input audio is empty (0 bytes): ${audioPath}. Ensure you downloaded/conversion succeeded.`
        );
    }

    // Probe duration using ffprobe
    const probe = await execa('ffprobe', [
        '-v',
        'error',
        '-show_entries',
        'format=duration',
        '-of',
        'default=noprint_wrappers=1:nokey=1',
        audioPath,
    ]);
    const parsed = parseFloat(probe.stdout);
    if (!isFinite(parsed) || Number.isNaN(parsed)) {
        throw new Error(
            `ffprobe could not determine duration for ${audioPath}. Raw output: ${probe.stdout}`
        );
    }
    const durationSec = Math.max(0, parsed);
    const chunkSec = Math.max(1, Math.floor(opts.chunkSec));
    const overlapSec = Math.max(0, Math.floor(opts.overlapSec));

    info('chunk.probe', { audioPath, durationSec });
    const chunks: ChunkInfo[] = [];
    let start = 0;
    let index = 0;
    const totalExpected = Math.ceil(durationSec / chunkSec) || 1;
    const timer = startStep('chunk.split', { videoId, durationSec, chunkSec, overlapSec });
    while (start < durationSec) {
        const end = Math.min(durationSec, start + chunkSec);
        const filename = `chunk_${String(index).padStart(4, '0')}.wav`;
        const outPath = path.resolve(path.join(outDir, filename));
        const segmentDur = Math.max(0, end - start);

        if (segmentDur < 0.05) {
            // Too small to bother; break to avoid zero-length chunks
            break;
        }

        // Use accurate seeking by placing -ss after -i. Explicitly set audio codec/format to WAV PCM 16k mono.
        try {
            await execa('ffmpeg', [
                '-y',
                '-loglevel',
                'error',
                '-hide_banner',
                '-nostdin',
                '-i',
                audioPath,
                '-ss',
                String(start),
                '-t',
                String(segmentDur),
                '-vn',
                '-sn',
                '-ac',
                '1',
                '-ar',
                '16000',
                '-acodec',
                'pcm_s16le',
                '-f',
                'wav',
                outPath,
            ]);
        } catch (e: any) {
            throw new Error(
                `ffmpeg failed while extracting segment index=${index} start=${start} dur=${segmentDur}. ` +
                    `Check that ${audioPath} is a valid audio file. Underlying error: ${
                        e?.shortMessage || e
                    }`
            );
        }

        // Sanity check produced chunk
        const chStat = await fs.stat(outPath);
        if (chStat.size === 0) {
            throw new Error(
                `Created empty chunk at ${outPath}. This suggests the source audio had no samples in the range [${start}, ${end}).`
            );
        }
        chunks.push({
            chunkIndex: index,
            path: outPath,
            globalStart: start,
            globalEnd: end,
        });
        timer.eta(index + 1, totalExpected);
        // If we've reached the end (allow tiny epsilon), stop to avoid looping on the final overlap window
        if (end >= durationSec - 1e-6) {
            break;
        }

        // Advance with overlap for the next window
        start = end - overlapSec;
        if (start < 0) start = 0;
        index += 1;
    }

    timer.end();
    manifest.chunks = chunks;
    info('chunk.complete', { videoId, count: chunks.length, durationSec });
    const manifestPath = path.join(outDir, 'manifest.json');
    await fs.writeJson(manifestPath, manifest, { spaces: 2 });
    return manifestPath;
}
