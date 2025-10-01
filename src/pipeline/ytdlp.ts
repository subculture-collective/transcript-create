import { execa } from 'execa';
import { ENV } from './env';

export interface ChannelListOptions {
    limit?: number; // max videos
}

export async function listChannelVideoIds(
    channelIdOrUrl: string,
    opts: ChannelListOptions = {}
): Promise<string[]> {
    // Accept channel ID or full URL; construct a URL if just ID
    const url = channelIdOrUrl.startsWith('http')
        ? channelIdOrUrl
        : `https://www.youtube.com/channel/${channelIdOrUrl}/videos`;

    const args = ['--flat-playlist', '-J', url];

    async function tryExec(cmd: string, a: string[]) {
        return execa(cmd, a, { stdio: 'pipe' });
    }
    const attempts: Array<[string, string[]]> = [];
    attempts.push([ENV.ytdlpBin, args]);
    if (ENV.ytdlpBin !== 'yt-dlp') attempts.push(['yt-dlp', args]);
    if (ENV.ytdlpPythonBin)
        attempts.push([ENV.ytdlpPythonBin, ['-m', 'yt_dlp', ...args]]);
    attempts.push(['python3', ['-m', 'yt_dlp', ...args]]);

    let stdout = '';
    const errors: string[] = [];
    let success = false;
    for (const [cmd, a] of attempts) {
        try {
            const res = await tryExec(cmd, a);
            stdout = res.stdout;
            success = true;
            break;
        } catch (e: any) {
            const msg = e?.stderr || e?.stdout || e?.message || String(e);
            errors.push(`[${cmd}] ${msg}`);
            continue;
        }
    }
    if (!success) {
        throw new Error(
            `All yt-dlp attempts failed for channel listing. Errors:\n${errors.join(
                '\n---\n'
            )}`
        );
    }
    const json = JSON.parse(stdout);
    const entries: any[] = json?.entries || [];
    const ids = entries.map((e) => e?.id || e?.url || '').filter(Boolean);
    return typeof opts.limit === 'number' ? ids.slice(0, opts.limit) : ids;
}
