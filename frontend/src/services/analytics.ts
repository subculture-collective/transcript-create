import { http } from './api'

export type EventPayload = {
  type: 'search' | 'result_click' | 'seek' | 'favorite_add' | 'favorite_remove' | 'video_open'
  payload?: Record<string, unknown>
}

const queue: EventPayload[] = []
const SAMPLE: Partial<Record<EventPayload['type'], number>> = {
  // e.g., seek: 0.5 means 50% sampled
  // seek: 0.5,
}
let timer: number | undefined

export function track(e: EventPayload) {
  const p = SAMPLE[e.type]
  if (typeof p === 'number' && Math.random() > p) return
  queue.push(e)
  scheduleFlush()
}

function scheduleFlush() {
  if (timer) return
  timer = window.setTimeout(flush, 3000)
}

async function flush() {
  const batch = queue.splice(0, queue.length)
  timer = undefined
  if (batch.length === 0) return
  try {
    await http.post('events/batch', { json: { events: batch } }).json()
  } catch {
    // ignore
  }
}

window.addEventListener('beforeunload', () => {
  if (queue.length) {
    navigator.sendBeacon?.('/api/events/batch', JSON.stringify({ events: queue }))
  }
})
