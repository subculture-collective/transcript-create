import * as dotenv from 'dotenv';
dotenv.config();

export const ENV = {
    databaseUrl:
        process.env.DATABASE_URL ||
        'postgres://postgres:postgres@localhost:5432/transcripts',
    artifactsRoot: process.env.ARTIFACTS_ROOT || 'artifacts',
    chunkSec: Number(process.env.CHUNK_SEC || 1800),
    overlapSec: Number(process.env.OVERLAP_SEC || 8),
    force: (process.env.FORCE || 'false') === 'true',
    // Optional: image for whisperx runner; if empty, falls back to local python
    whisperxImage: process.env.WHISPERX_IMAGE || '',
    // Optional: override docker binary name/path
    dockerBin: process.env.DOCKER_BIN || 'docker',
    // Optional: override yt-dlp binary name/path
    ytdlpBin: process.env.YTDLP_BIN || 'yt-dlp',
    // Optional: explicit python interpreter with yt_dlp installed for fallback (e.g. .venv/bin/python)
    ytdlpPythonBin: process.env.YTDLP_PYTHON_BIN || '.venv/bin/python',
    // Optional: extra docker run args (space-separated), e.g. "--device /dev/kfd --device /dev/dri --group-add video --group-add render"
    dockerAdditionalArgs: process.env.DOCKER_ADDITIONAL_ARGS || '',
    logLevel: process.env.LOG_LEVEL || 'info',
    transcribeRetries: Number(process.env.TRANSCRIBE_RETRIES || 2),
    transcribeRetryBaseMs: Number(process.env.TRANSCRIBE_RETRY_BASE_MS || 1000),
    ytdlpCookiesFile: process.env.YTDLP_COOKIES_FILE || '',
    ytdlpUserAgent: process.env.YTDLP_USER_AGENT || '',
    ytdlpExtraArgs: process.env.YTDLP_EXTRA_ARGS || '',
    // Watchdog timeout (seconds) for a single chunk transcription. 0 disables.
    transcribeChunkTimeoutSec: Number(process.env.TRANSCRIBE_CHUNK_TIMEOUT_SEC || 0),
    // Global semaphore limiting total concurrent chunk containers across ALL videos. 0/blank disables.
    transcribeGlobalConcurrency: Number(process.env.TRANSCRIBE_GLOBAL_CONCURRENCY || 0),
    // Hugging Face credentials / cache passthrough
    hfToken: process.env.HF_TOKEN || '',
    hfHome: process.env.HF_HOME || '',
    disableDb: (process.env.DISABLE_DB || 'false').toLowerCase() === 'true',
};
