import ClipExportControls from './ClipExportControls';
import { Link } from 'react-router-dom';
import { useSite } from '../../services/site';
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import type { Segment } from '../../types/api';
import type { YouTubePlayerHandle } from '../YouTubePlayer';
import {
  buildPassageShareLink,
  buildPassageLink,
  formatPassageTime,
  parsePassageTime,
  passageRangeError,
  type PassageRange,
} from '../../features/passages/range';
import { normalizeTranscriptText } from '../../features/videoTranscript/transcript';

type Props = {
  videoId: string;
  title: string;
  initialRange: PassageRange;
  durationMs?: number;
  segments: Segment[];
  playerRef: RefObject<YouTubePlayerHandle | null>;
  onClose: () => void;
  onShowPlayer?: () => void;
};

export default function PassagePanel({
  videoId,
  title,
  initialRange,
  durationMs,
  segments,
  playerRef,
  onClose,
  onShowPlayer,
}: Props) {
  const site = useSite();
  const [start, setStart] = useState(
    Number.isFinite(initialRange.startMs) ? formatPassageTime(initialRange.startMs) : ''
  );
  const [end, setEnd] = useState(
    Number.isFinite(initialRange.endMs) ? formatPassageTime(initialRange.endMs) : ''
  );
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const startMs = parsePassageTime(start);
  const endMs = parsePassageTime(end);
  const error = passageRangeError(startMs, endMs, durationMs);
  const range = !error && startMs !== null && endMs !== null ? { startMs, endMs } : null;
  const link = range
    ? `${window.location.origin}${site.public_passages_enabled ? buildPassageShareLink(videoId, range) : buildPassageLink(videoId, range)}`
    : '';
  const context = useMemo(() => {
    if (startMs === null || endMs === null || error) return { entries: [], omitted: 0 };
    const first = segments.findIndex((s) => s.end_ms > startMs && s.start_ms < endMs);
    if (first < 0) return { entries: [], omitted: 0 };
    let last = first;
    while (last + 1 < segments.length && segments[last + 1].start_ms < endMs) last++;
    const selectedEnd = Math.min(last + 1, first + 200);
    return {
      entries: [
        ...segments.slice(Math.max(0, first - 1), selectedEnd),
        ...segments.slice(last + 1, last + 2),
      ],
      omitted: last + 1 - selectedEnd,
    };
  }, [startMs, endMs, segments, error]);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
    headingRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, []);

  function updateTime(which: 'start' | 'end', value: string) {
    playerRef.current?.pause();
    setFeedback('');
    (which === 'start' ? setStart : setEnd)(value);
  }

  function setPlaybackBoundary(which: 'start' | 'end') {
    const seconds = playerRef.current?.getCurrentTime();
    if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
      setFeedback('Playback time is unavailable. Enter a time manually or wait for the player.');
      return;
    }
    updateTime(which, formatPassageTime(Math.round(seconds * 1000)));
  }

  async function copyLink() {
    if (!range) return;
    try {
      await navigator.clipboard.writeText(link);
      setFeedback('Passage link copied.');
    } catch {
      setFeedback('Copy is unavailable. Select and copy the passage link below.');
    }
  }

  async function share() {
    if (!range) return;
    setBusy(true);
    try {
      await navigator.share({
        title: `${title} · ${formatPassageTime(range.startMs)}–${formatPassageTime(range.endMs)}`,
        url: link,
      });
      setFeedback('Link handed to your sharing app.');
    } catch (error) {
      setFeedback(
        error instanceof Error && error.name === 'AbortError'
          ? 'Sharing cancelled.'
          : 'Sharing is unavailable. Copy the passage link instead.'
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="passage-panel rounded-xl border border-accent/40 bg-panel p-4 sm:p-6"
      aria-labelledby="passage-heading"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2
            id="passage-heading"
            ref={headingRef}
            tabIndex={-1}
            className="text-lg font-semibold text-ink"
          >
            Share a passage
          </h2>
          <p className="mt-1 text-sm text-muted">
            Choose a range, preview it, and share its context.
          </p>
        </div>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            playerRef.current?.pause();
            onClose();
          }}
        >
          Close passage
        </button>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {(['start', 'end'] as const).map((which) => (
          <div key={which}>
            <label className="block text-sm font-semibold text-ink" htmlFor={`passage-${which}`}>
              {which === 'start' ? 'Start time' : 'End time'}
            </label>
            <input
              id={`passage-${which}`}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 font-mono text-ink"
              value={which === 'start' ? start : end}
              onChange={(e) => updateTime(which, e.target.value)}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'passage-error passage-time-help' : 'passage-time-help'}
            />
            <button
              type="button"
              className="btn-ghost mt-1 text-xs"
              onClick={() => setPlaybackBoundary(which)}
            >
              Set {which} from playback
            </button>
          </div>
        ))}
      </div>
      <p id="passage-time-help" className="mt-2 text-xs text-muted">
        Use hours:minutes:seconds, or seconds. Milliseconds are optional.
      </p>
      {error ? (
        <p id="passage-error" className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : (
        <p className="mt-2 text-sm text-accent">
          Duration:{' '}
          {((endMs! - startMs!) / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })}{' '}
          seconds
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-ghost text-xs"
          disabled={!range || !segments.some((s) => s.start_ms < range.startMs)}
          onClick={() => {
            const previous = [...segments]
              .reverse()
              .find((s) => range && s.start_ms < range.startMs);
            if (previous) updateTime('start', formatPassageTime(previous.start_ms));
          }}
        >
          Include previous segment
        </button>
        <button
          type="button"
          className="btn-ghost text-xs"
          disabled={
            !range ||
            !segments.some((s) => s.end_ms > range.endMs && (!durationMs || s.end_ms <= durationMs))
          }
          onClick={() => {
            const next = segments.find(
              (s) => range && s.end_ms > range.endMs && (!durationMs || s.end_ms <= durationMs)
            );
            if (next) updateTime('end', formatPassageTime(next.end_ms));
          }}
        >
          Include next segment
        </button>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {site.atproto_enabled && range && (
          <a
            className="btn-secondary"
            href={`/at.html?passage=${encodeURIComponent(buildPassageShareLink(videoId, range))}`}
          >
            Share to Bluesky
          </a>
        )}
        {site.community_enabled && range && (
          <Link
            className="btn-secondary"
            to={`/community?video_id=${encodeURIComponent(videoId)}&start_ms=${range.startMs}&end_ms=${range.endMs}`}
          >
            Discuss passage
          </Link>
        )}
        <button
          type="button"
          className="btn-primary"
          disabled={!range}
          onClick={() => {
            if (!range) return;
            onShowPlayer?.();
            playerRef.current?.previewRange(range.startMs / 1000, range.endMs / 1000);
            setFeedback('Preview requested. Playback stops at the end of the passage.');
          }}
        >
          Preview passage
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!range}
          onClick={() => {
            if (!range) return;
            onShowPlayer?.();
            playerRef.current?.seekTo(range.endMs / 1000, { play: true });
            setFeedback('Continuing after the passage.');
          }}
        >
          Continue after passage
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!range}
          onClick={() => void copyLink()}
        >
          Copy passage link
        </button>
        {typeof navigator.share === 'function' && (
          <button
            type="button"
            className="btn-secondary"
            disabled={!range || busy}
            onClick={() => void share()}
          >
            Share passage
          </button>
        )}
      </div>
      {site.clip_exports_enabled && range && (
        <ClipExportControls
          key={`${videoId}:${range.startMs}:${range.endMs}`}
          videoId={videoId}
          range={range}
        />
      )}
      {feedback && (
        <p className="mt-3 text-sm text-ink" role="status">
          {feedback}
        </p>
      )}
      {range && (
        <label className="mt-4 block text-xs text-muted">
          Passage link
          <input
            className="mt-1 w-full rounded-lg border border-border bg-surface p-2 text-sm text-ink"
            readOnly
            value={link}
            onFocus={(event) => event.currentTarget.select()}
          />
        </label>
      )}
      <div className="mt-5 border-t border-border pt-4">
        <h3 className="text-sm font-semibold text-ink">Passage in context</h3>
        <p className="mt-1 text-xs text-muted">
          Highlighted transcript segments overlap your selection. Transcript and playback timing can
          be approximate; check the source before quoting.
        </p>
        <div
          className="mt-3 max-h-64 space-y-3 overflow-y-auto"
          aria-label="Passage in context"
          tabIndex={0}
        >
          {context.omitted > 0 && (
            <p className="text-sm text-muted">
              Showing the first 200 selected transcript segments and surrounding context.{' '}
              {context.omitted.toLocaleString()} more segments are included in the shared range; use
              the full transcript to read them.
            </p>
          )}
          {context.entries.map((segment, index) => {
            const selected =
              range && segment.end_ms > range.startMs && segment.start_ms < range.endMs;
            return (
              <p key={`${segment.start_ms}:${index}`} className="text-sm leading-6 text-muted">
                <span className="mr-2 font-mono text-xs">
                  {formatPassageTime(segment.start_ms)}
                </span>
                {selected ? (
                  <mark className="rounded bg-accent/20 text-ink">
                    {normalizeTranscriptText(segment.text)}
                  </mark>
                ) : (
                  normalizeTranscriptText(segment.text)
                )}
              </p>
            );
          })}
          {!context.entries.length && (
            <p className="text-sm text-muted">
              {error
                ? 'Correct the range to show its context.'
                : 'No transcript text is available for this range. The source player may still be available.'}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
