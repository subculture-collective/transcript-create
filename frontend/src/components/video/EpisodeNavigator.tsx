import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { VideoChapter } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';
import type { EpisodeTopic } from '../../features/videoTranscript/topics';
import { normalizeTranscriptText } from '../../features/videoTranscript/transcript';
import { useEpisodeIntelligence } from '../../features/videoTranscript/useEpisodeIntelligence';
import EpisodeOutline, { visibleOutlineChapters } from './EpisodeOutline';

export type NavigatorTab = 'chapters' | 'topics' | 'moments' | 'related';

export type SavedEpisodeMoment = { startMs: number; text: string };

type Props = {
  videoId: string;
  durationMs: number;
  chapters: VideoChapter[];
  currentMs: number | null;
  onSelectChapter: (chapter: VideoChapter) => void;
  topics: EpisodeTopic[];
  topicsLoading?: boolean;
  activeTopicKey: string | null;
  onToggleTopic: (key: string | null) => void;
  onHighlightTopic: (topic: EpisodeTopic) => void;
  onOpenMoment: (startMs: number) => void;
  savedMoments: SavedEpisodeMoment[];
  initialTab?: NavigatorTab;
  /** Show one section without the tab bar (used by the mobile sheet). */
  fixedTab?: NavigatorTab;
};

const KIND_LABEL: Record<EpisodeTopic['kind'], string> = {
  topic: 'Topic',
  tag: 'Tag',
  person: 'Person',
  search: 'Popular search',
};

function excerpt(text: string, max = 150) {
  const clean = normalizeTranscriptText(text);
  return clean.length > max ? `${clean.slice(0, max - 1).trimEnd()}…` : clean;
}

function TopicDensity({ topic, durationMs }: { topic: EpisodeTopic; durationMs: number }) {
  if (!durationMs) return null;
  return (
    <svg
      className="topic-density"
      viewBox="0 0 1000 12"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      {topic.mentions.map((mention) => (
        <rect
          key={mention.segmentIndex}
          x={Math.min(997, (mention.startMs / durationMs) * 1000)}
          y={0}
          width={3}
          height={12}
        />
      ))}
    </svg>
  );
}

export default function EpisodeNavigator({
  videoId,
  durationMs,
  chapters,
  currentMs,
  onSelectChapter,
  topics,
  topicsLoading = false,
  activeTopicKey,
  onToggleTopic,
  onHighlightTopic,
  onOpenMoment,
  savedMoments,
  initialTab,
  fixedTab,
}: Props) {
  const chapterCount = visibleOutlineChapters(chapters).length;
  const [selectedTab, setTab] = useState<NavigatorTab | null>(initialTab ?? null);
  const tab = fixedTab ?? selectedTab ?? (chapterCount > 0 ? 'chapters' : 'topics');
  const { related, quoted, error } = useEpisodeIntelligence(videoId);

  const tabs: Array<{ id: NavigatorTab; label: string; count?: number }> = [
    { id: 'chapters', label: 'Chapters', count: chapterCount },
    { id: 'topics', label: 'Topics', count: topics.length },
    { id: 'moments', label: 'Moments', count: (quoted?.length ?? 0) + savedMoments.length },
    { id: 'related', label: 'Related', count: related?.length },
  ];

  return (
    <section className="navigator" aria-label="Episode navigator">
      {!fixedTab && (
        <div className="navigator-tabs" role="tablist" aria-label="Episode navigator sections">
          {tabs.map((item) => (
            <button
              key={item.id}
              id={`navigator-tab-${item.id}`}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              aria-controls={`navigator-panel-${item.id}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
              {item.count ? <span className="navigator-tab-count">{item.count}</span> : null}
            </button>
          ))}
        </div>
      )}

      <div
        className="navigator-body"
        role={fixedTab ? undefined : 'tabpanel'}
        id={fixedTab ? undefined : `navigator-panel-${tab}`}
        aria-labelledby={fixedTab ? undefined : `navigator-tab-${tab}`}
      >
        {tab === 'chapters' &&
          (chapterCount > 0 ? (
            <EpisodeOutline
              chapters={chapters}
              currentMs={currentMs}
              onSelect={onSelectChapter}
              embedded
            />
          ) : (
            <p className="navigator-empty">Chapter landmarks are not available for this episode.</p>
          ))}

        {tab === 'topics' && (
          <div>
            {topicsLoading && topics.length === 0 && (
              <p className="navigator-empty" role="status">
                Finding archive topics in this transcript…
              </p>
            )}
            {!topicsLoading && topics.length === 0 && (
              <p className="navigator-empty">
                None of the archive’s tracked topics are mentioned in this transcript.
              </p>
            )}
            {topics.length > 0 && (
              <p className="px-4 pb-1 pt-3 text-xs leading-5 text-subtle">
                Archive topics, tags and popular searches found in this transcript. Select one to
                see where it comes up.
              </p>
            )}
            {topics.map((topic) => {
              const active = topic.key === activeTopicKey;
              return (
                <div key={topic.key} className="border-b border-border/60 last:border-b-0">
                  <button
                    type="button"
                    className="topic-row border-b-0"
                    aria-pressed={active}
                    onClick={() => onToggleTopic(active ? null : topic.key)}
                  >
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="min-w-0 truncate font-semibold text-ink">
                        {topic.label}
                        <span className="ml-2 text-[11px] font-medium text-subtle">
                          {KIND_LABEL[topic.kind]}
                        </span>
                      </span>
                      <span className="shrink-0 font-mono text-xs text-subtle">
                        {topic.count} {topic.count === 1 ? 'mention' : 'mentions'}
                      </span>
                    </span>
                    <TopicDensity topic={topic} durationMs={durationMs} />
                  </button>
                  {active && (
                    <div className="px-4 pb-3">
                      <div className="mb-2 flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="toolbar-button toolbar-button-accent"
                          onClick={() => onHighlightTopic(topic)}
                        >
                          Highlight in transcript
                        </button>
                        <Link
                          className="toolbar-button"
                          to={`/topics/${encodeURIComponent(topic.label)}`}
                        >
                          Across the archive →
                        </Link>
                      </div>
                      <ol className="space-y-1">
                        {topic.mentions.slice(0, 12).map((mention) => (
                          <li key={mention.segmentIndex}>
                            <button
                              type="button"
                              className="grid w-full grid-cols-[4.5rem_minmax(0,1fr)] gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-surface-muted"
                              onClick={() => onOpenMoment(mention.startMs)}
                            >
                              <span className="font-mono text-xs text-accent">
                                {formatTimestamp(mention.startMs)}
                              </span>
                              <span className="line-clamp-2 text-muted">
                                {excerpt(mention.text)}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ol>
                      {topic.mentions.length > 12 && (
                        <p className="mt-2 px-2 text-xs text-subtle">
                          {topic.mentions.length - 12} more passages. Use “Highlight in transcript”
                          to step through all of them.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {tab === 'moments' && (
          <div>
            <h3 className="meta-label px-4 pb-1 pt-4">Your saved moments</h3>
            {savedMoments.length === 0 ? (
              <p className="navigator-empty pt-1">
                Select any passage in the transcript and choose Save to keep it here.
              </p>
            ) : (
              savedMoments.map((moment) => (
                <button
                  key={`saved:${moment.startMs}`}
                  type="button"
                  className="moment-row"
                  onClick={() => onOpenMoment(moment.startMs)}
                >
                  <span className="font-mono text-xs text-warning">
                    ★ {formatTimestamp(moment.startMs)}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-sm text-muted">
                    {excerpt(moment.text)}
                  </span>
                </button>
              ))
            )}
            <h3 className="meta-label px-4 pb-1 pt-5">Most-quoted moments</h3>
            {error && (
              <p className="navigator-empty pt-1" role="alert">
                Quoted moments are temporarily unavailable.
              </p>
            )}
            {!error && quoted === null && (
              <p className="navigator-empty pt-1" role="status">
                Loading quoted moments…
              </p>
            )}
            {quoted?.length === 0 && (
              <p className="navigator-empty pt-1">No quoted moments have accumulated yet.</p>
            )}
            {quoted?.map((moment) => (
              <button
                key={`quoted:${moment.start_ms}:${moment.end_ms}`}
                type="button"
                className="moment-row"
                onClick={() => onOpenMoment(moment.start_ms)}
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-xs text-accent">
                    {formatTimestamp(moment.start_ms)}
                  </span>
                  <span className="text-xs text-subtle">quoted {moment.quote_count}×</span>
                </span>
                <span className="mt-1 line-clamp-3 block font-serif text-[15px] leading-6 text-ink">
                  “{excerpt(moment.snippet, 220)}”
                </span>
              </button>
            ))}
          </div>
        )}

        {tab === 'related' && (
          <div>
            {error && (
              <p className="navigator-empty" role="alert">
                Related episodes are temporarily unavailable.
              </p>
            )}
            {!error && related === null && (
              <p className="navigator-empty" role="status">
                Loading related episodes…
              </p>
            )}
            {related?.length === 0 && (
              <p className="navigator-empty">No explainable related episodes yet.</p>
            )}
            {related?.map((item) => (
              <article key={item.video.id} className="moment-row">
                <Link
                  className="font-semibold leading-5 text-ink hover:text-accent"
                  to={`/v/${item.video.id}`}
                >
                  {item.video.title || 'Untitled VOD'}
                </Link>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.reasons.map((reason) => (
                    <span className="source-pill" key={reason}>
                      {reason}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
