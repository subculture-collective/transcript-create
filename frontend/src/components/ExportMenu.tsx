import { track } from '../services';

type Props = {
  videoId: string;
  youtubeId?: string;
  isPro?: boolean;
  onRequireUpgrade: () => void;
};

export default function ExportMenu({ videoId, isPro, onRequireUpgrade }: Props) {
  function guard(e: React.MouseEvent, payload: any) {
    if (!isPro) {
      e.preventDefault();
      onRequireUpgrade();
      return;
    }
    track({ type: 'export_click', payload });
  }
  return (
    <details className="relative inline-block group">
      <summary className="inline-flex cursor-pointer list-none rounded border px-2 py-1 hover:bg-gray-50">
        Export
      </summary>
      <div className="absolute z-10 mt-1 w-56 rounded border bg-white p-2 shadow-lg">
        <div className="mb-1 text-xs font-medium text-gray-500">Native transcript</div>
        <div className="flex flex-wrap gap-2">
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'srt', source: 'native' })}
            href={`/api/videos/${videoId}/transcript.srt`}
            download={`video-${videoId}.srt`}
          >
            SRT
          </a>
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'vtt', source: 'native' })}
            href={`/api/videos/${videoId}/transcript.vtt`}
            download={`video-${videoId}.vtt`}
          >
            VTT
          </a>
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'json', source: 'native' })}
            href={`/api/videos/${videoId}/transcript.json`}
            download={`video-${videoId}.json`}
          >
            JSON
          </a>
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'pdf', source: 'native' })}
            href={`/api/videos/${videoId}/transcript.pdf`}
            download={`video-${videoId}.pdf`}
          >
            PDF
          </a>
        </div>
        <div className="mt-2 mb-1 text-xs font-medium text-gray-500">YouTube captions</div>
        <div className="flex flex-wrap gap-2">
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'srt', source: 'youtube' })}
            href={`/api/videos/${videoId}/youtube-transcript.srt`}
            download={`video-${videoId}.youtube.srt`}
          >
            SRT
          </a>
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'vtt', source: 'youtube' })}
            href={`/api/videos/${videoId}/youtube-transcript.vtt`}
            download={`video-${videoId}.youtube.vtt`}
          >
            VTT
          </a>
          <a
            className="rounded border px-2 py-1 hover:bg-gray-50"
            onClick={(e) => guard(e, { videoId, format: 'json', source: 'youtube' })}
            href={`/api/videos/${videoId}/youtube-transcript.json`}
            download={`video-${videoId}.youtube.json`}
          >
            JSON
          </a>
        </div>
        <div className="mt-2 mb-1 text-xs font-medium text-gray-500">Per-section</div>
        <div className="text-xs text-gray-600">
          Use the inline copy link next to any segment, or select text to build a custom pack
          (coming soon).
        </div>
      </div>
    </details>
  );
}
