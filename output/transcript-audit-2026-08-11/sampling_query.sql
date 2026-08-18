WITH eligible AS (
    SELECT
        v.id,
        v.youtube_id,
        v.title,
        v.uploaded_at,
        v.duration_seconds,
        ntile(40) OVER (ORDER BY v.uploaded_at, v.id) AS time_bucket
    FROM videos v
    WHERE v.state = 'completed'
      AND v.uploaded_at IS NOT NULL
      AND v.duration_seconds >= 600
      AND EXISTS (SELECT 1 FROM segments s WHERE s.video_id = v.id)
      AND EXISTS (SELECT 1 FROM youtube_transcripts yt WHERE yt.video_id = v.id)
), sampled AS (
    SELECT *, row_number() OVER (PARTITION BY time_bucket ORDER BY md5(id::text)) AS bucket_row
    FROM eligible
), positions(position_label, position_ratio) AS (
    VALUES ('early', 0.05::numeric), ('first_quarter', 0.27::numeric),
           ('middle', 0.50::numeric), ('third_quarter', 0.73::numeric), ('late', 0.95::numeric)
), targets AS (
    SELECT
        s.*,
        p.position_label,
        p.position_ratio,
        round(s.duration_seconds * 1000 * p.position_ratio)::integer AS target_ms
    FROM sampled s CROSS JOIN positions p
    WHERE s.bucket_row = 1
)
SELECT json_build_object(
    'video_id', t.id,
    'youtube_id', t.youtube_id,
    'title', t.title,
    'uploaded_at', t.uploaded_at,
    'duration_seconds', t.duration_seconds,
    'position_label', t.position_label,
    'position_ratio', t.position_ratio,
    'target_ms', t.target_ms,
    'window_start_ms', greatest(0, t.target_ms - 30000),
    'window_end_ms', least(t.duration_seconds * 1000, t.target_ms + 30000),
    'native_start_ms', native.native_start_ms,
    'native_end_ms', native.native_end_ms,
    'native_text', coalesce(native.native_text, ''),
    'native_segment_count', coalesce(native.native_segment_count, 0),
    'native_hallucination_count', coalesce(native.native_hallucination_count, 0),
    'native_avg_logprob', native.native_avg_logprob,
    'youtube_start_ms', captions.youtube_start_ms,
    'youtube_end_ms', captions.youtube_end_ms,
    'youtube_text', coalesce(captions.youtube_text, ''),
    'youtube_segment_count', coalesce(captions.youtube_segment_count, 0)
)::text
FROM targets t
LEFT JOIN LATERAL (
    SELECT
        min(s.start_ms) AS native_start_ms,
        max(s.end_ms) AS native_end_ms,
        left(string_agg(s.text, ' ' ORDER BY s.start_ms), 4000) AS native_text,
        count(*) AS native_segment_count,
        count(*) FILTER (WHERE s.likely_hallucination = true) AS native_hallucination_count,
        avg(s.avg_logprob) AS native_avg_logprob
    FROM segments s
    WHERE s.video_id = t.id
      AND s.end_ms >= greatest(0, t.target_ms - 30000)
      AND s.start_ms <= least(t.duration_seconds * 1000, t.target_ms + 30000)
) native ON true
LEFT JOIN LATERAL (
    SELECT
        min(ys.start_ms) AS youtube_start_ms,
        max(ys.end_ms) AS youtube_end_ms,
        left(string_agg(ys.text, ' ' ORDER BY ys.start_ms), 4000) AS youtube_text,
        count(*) AS youtube_segment_count
    FROM youtube_transcripts yt
    JOIN youtube_segments ys ON ys.youtube_transcript_id = yt.id
    WHERE yt.video_id = t.id
      AND ys.end_ms >= greatest(0, t.target_ms - 30000)
      AND ys.start_ms <= least(t.duration_seconds * 1000, t.target_ms + 30000)
) captions ON true
ORDER BY t.uploaded_at, t.youtube_id, t.position_ratio;
