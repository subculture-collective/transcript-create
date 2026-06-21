import { track } from '../services';
import { buildApiUrl } from '../services/api';

type Props = {
  videoId: string;
  youtubeId?: string;
  isPro?: boolean;
};

export default function ExportMenu({ videoId }: Props) {
  function guard(payload: Record<string, unknown>) {
    track({ type: 'export_click', payload });
  }
  return (
    <details className="relative inline-block group">
      <summary className="btn-secondary list-none px-3 py-1.5 text-sm">
        Export
      </summary>
      <div className="absolute z-10 mt-2 w-64 rounded-[1.25rem] border border-border bg-surface/95 p-3 shadow-[0_20px_50px_rgba(0,0,0,0.45)] backdrop-blur-xl">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-subtle">Transcript</div>
        <div className="flex flex-wrap gap-2">
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={() => guard({ videoId, format: 'srt', source: 'best' })}
            href={buildApiUrl(`videos/${videoId}/transcript.srt`)}
            download={`video-${videoId}.srt`}
          >
            SRT
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={() => guard({ videoId, format: 'vtt', source: 'best' })}
            href={buildApiUrl(`videos/${videoId}/transcript.vtt`)}
            download={`video-${videoId}.vtt`}
          >
            VTT
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={() => guard({ videoId, format: 'json', source: 'best' })}
            href={buildApiUrl(`videos/${videoId}/transcript.json`)}
            download={`video-${videoId}.json`}
          >
            JSON
          </a>
          <a
            className="btn-secondary min-h-0 px-2 py-1 text-xs"
            onClick={() => guard({ videoId, format: 'pdf', source: 'whisper' })}
            href={buildApiUrl(`videos/${videoId}/transcript.pdf`)}
            download={`video-${videoId}.pdf`}
          >
            PDF
          </a>
        </div>
        <div className="mt-2 text-xs text-muted">Exports use the best transcript available for this VOD.</div>
        <div className="mt-3 mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-subtle">Per-section</div>
        <div className="text-xs text-muted">
          Use the inline copy link next to any segment, or select text to build a custom pack
          (coming soon).
        </div>
      </div>
    </details>
  );
}
