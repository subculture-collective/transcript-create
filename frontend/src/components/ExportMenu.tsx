import { track } from '../services';
import { canExportFormat, type ExportFormat, type Plan } from '../features/entitlements/policy';

type Props = {
  videoId: string;
  youtubeId?: string;
  isPro?: boolean;
  onRequireUpgrade: () => void;
};

export default function ExportMenu({ videoId, isPro, onRequireUpgrade }: Props) {
  function guard(e: React.MouseEvent, payload: Record<string, unknown>, format: ExportFormat) {
    const plan: Plan = isPro ? 'pro' : 'free';
    if (!canExportFormat({ plan, format })) {
      e.preventDefault();
      onRequireUpgrade();
      return;
    }
    track({ type: 'export_click', payload });
  }
  return (
    <details className="relative inline-block group">
      <summary className="btn-secondary list-none px-3 py-1.5 text-sm">
        Export
      </summary>
      <div className="absolute z-10 mt-1 w-56 rounded-lg border border-border bg-surface p-2 shadow-lg">
        <div className="mb-1 text-xs font-medium text-muted">Best available transcript</div>
        <div className="flex flex-wrap gap-2">
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'srt', source: 'best' }, 'srt')}
            href={`/api/videos/${videoId}/transcript.srt`}
            download={`video-${videoId}.srt`}
          >
            SRT
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'vtt', source: 'best' }, 'vtt')}
            href={`/api/videos/${videoId}/transcript.vtt`}
            download={`video-${videoId}.vtt`}
          >
            VTT
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'json', source: 'best' }, 'json')}
            href={`/api/videos/${videoId}/transcript.json`}
            download={`video-${videoId}.json`}
          >
            JSON
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'pdf', source: 'whisper' }, 'pdf')}
            href={`/api/videos/${videoId}/transcript.pdf`}
            download={`video-${videoId}.pdf`}
          >
            PDF
          </a>
        </div>
        <div className="mt-1 text-xs text-muted">Uses Whisper when ready; falls back to YouTube captions.</div>
        <div className="mt-2 mb-1 text-xs font-medium text-muted">YouTube captions</div>
        <div className="flex flex-wrap gap-2">
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'srt', source: 'youtube' }, 'srt')}
            href={`/api/videos/${videoId}/youtube-transcript.srt`}
            download={`video-${videoId}.youtube.srt`}
          >
            SRT
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'vtt', source: 'youtube' }, 'vtt')}
            href={`/api/videos/${videoId}/youtube-transcript.vtt`}
            download={`video-${videoId}.youtube.vtt`}
          >
            VTT
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={(e) => guard(e, { videoId, format: 'json', source: 'youtube' }, 'json')}
            href={`/api/videos/${videoId}/youtube-transcript.json`}
            download={`video-${videoId}.youtube.json`}
          >
            JSON
          </a>
        </div>
        <div className="mt-2 mb-1 text-xs font-medium text-muted">Per-section</div>
        <div className="text-xs text-muted">
          Use the inline copy link next to any segment, or select text to build a custom pack
          (coming soon).
        </div>
      </div>
    </details>
  );
}
