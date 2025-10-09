import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../services/api'
import type { Segment, TranscriptResponse, VideoInfo, SearchHit } from '../types/api'
import { favorites } from '../services/favorites'

function secondsToYouTubeTs(s: number) {
  return Math.max(0, Math.floor(s))
}

function msToHms(ms: number) {
  const total = Math.floor(ms / 1000)
  const hh = Math.floor(total / 3600).toString().padStart(2, '0')
  const mm = Math.floor((total % 3600) / 60).toString().padStart(2, '0')
  const ss = (total % 60).toString().padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

export default function VideoPage() {
  const { videoId } = useParams()
  const [params, setParams] = useSearchParams()
  const [video, setVideo] = useState<VideoInfo | null>(null)
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null)
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [activeSegId, setActiveSegId] = useState<number | null>(null)
  const playerRef = useRef<HTMLIFrameElement | null>(null)

  const startSeconds = useMemo(() => {
    const tStr = params.get('t')
    const t = tStr ? parseInt(tStr, 10) : 0
    return Number.isFinite(t) ? t : 0
  }, [params])

  useEffect(() => {
    if (!videoId) return
    api.getVideo(videoId).then(setVideo).catch(() => setVideo(null))
    api.getTranscript(videoId).then(setTranscript).catch(() => setTranscript(null))
    const q = params.get('q')
    if (q) {
      api.search(q, { video_id: videoId }).then((r) => setHits(r.hits)).catch(() => setHits(null))
    } else {
      setHits(null)
    }
  }, [videoId])

  // Scroll to a hash if provided
  useEffect(() => {
    const hash = window.location.hash
    if (hash) {
      const el = document.querySelector(hash)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [transcript])

  function jumpTo(ms: number) {
    const s = Math.floor(ms / 1000)
    setParams((prev: URLSearchParams) => {
      const p = new URLSearchParams(prev as unknown as string)
      p.set('t', String(s))
      return p
    })
    const iframe = playerRef.current
    if (iframe) {
      // YouTube iframe supports changing the URL with a new start param
      const src = new URL(iframe.src)
      src.searchParams.set('start', String(s))
      iframe.src = src.toString()
    }
  }

  function onClickSegment(seg: Segment, id: number) {
    setActiveSegId(id)
    jumpTo(seg.start_ms)
    // update hash for deep-linking this segment
    history.replaceState(null, '', `#seg-${id}`)
  }

  function copyLink(segIdx: number, startMs: number) {
    const s = Math.floor(startMs / 1000)
    const url = `${location.origin}/v/${videoId}?t=${s}#seg-${segIdx}`
    navigator.clipboard?.writeText(url)
  }

  const videoUrl = useMemo(() => {
    if (!video) return null
    const t = secondsToYouTubeTs(startSeconds)
    const url = new URL(`https://www.youtube.com/embed/${video.youtube_id}`)
    url.searchParams.set('start', String(t))
    url.searchParams.set('autoplay', '0')
    url.searchParams.set('enablejsapi', '1')
    return url.toString()
  }, [video, startSeconds])

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <div className="lg:col-span-7">
        <div className="aspect-video w-full overflow-hidden rounded-lg border bg-black">
          {videoUrl ? (
            <iframe ref={playerRef} className="h-full w-full" src={videoUrl} title={video?.title ?? 'Video'} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen />
          ) : (
            <div className="flex h-full items-center justify-center text-gray-400">Loading player…</div>
          )}
        </div>
        <div className="mt-3 text-sm text-gray-600">
          {video?.title ?? 'Untitled video'}
        </div>
      </div>
      <div className="lg:col-span-5">
        <h2 className="mb-3 font-semibold">Transcript</h2>
        {!transcript && <div className="text-gray-500">Loading transcript…</div>}
        {transcript && (
          <ol className="space-y-1">
            {transcript.segments.map((seg, idx) => {
              const id = idx + 1
              const match = hits?.find(h => h.start_ms >= seg.start_ms && h.start_ms < seg.end_ms)
              return (
                <li
                  id={`seg-${id}`}
                  key={id}
                  className={`rounded-md p-2 hover:bg-blue-50 ${activeSegId === id || match ? 'bg-blue-50 ring-1 ring-blue-300' : ''}`}
                >
                  <button onClick={() => onClickSegment(seg, id)} className="text-left">
                    <div className="mb-1 text-xs text-gray-500">{msToHms(seg.start_ms)} – {msToHms(seg.end_ms)}</div>
                    <p>{seg.text}</p>
                  </button>
                  <div className="mt-2 flex items-center gap-3 text-xs text-gray-600">
                    <button className="hover:text-gray-900" onClick={() => copyLink(id, seg.start_ms)}>Copy link</button>
                    <button className="hover:text-gray-900" onClick={() => favorites.toggle({ videoId: videoId!, segIndex: id, startMs: seg.start_ms, endMs: seg.end_ms, text: seg.text })}>
                      {favorites.has({ videoId: videoId!, segIndex: id }) ? 'Unfavorite' : 'Favorite'}
                    </button>
                  </div>
                  {match && (
                    <div className="mt-2 rounded bg-yellow-50 p-2 text-xs text-yellow-900">
                      <div className="mb-1 font-medium">Match</div>
                      <div className="prose prose-xs max-w-none" dangerouslySetInnerHTML={{ __html: match.snippet }} />
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </div>
  )
}
