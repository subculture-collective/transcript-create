import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import TimelinePage from '../routes/TimelinePage'
import { api } from '../services'
import { render } from '@testing-library/react'

describe('TimelinePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('links browse this period to the matching episodes date range', async () => {
    vi.spyOn(api, 'getTimeline').mockResolvedValue([
      {
        period: '2026-05',
        label: 'May 2026',
        video_count: 2,
        total_duration_seconds: 5400,
        videos: [
          {
            id: 'video-1',
            youtube_id: 'abc123',
            title: 'Episode one',
            channel_name: 'Channel Alpha',
            duration_seconds: 1800,
          },
        ],
      },
    ] as never)

    render(
      <MemoryRouter initialEntries={['/timeline']}>
        <TimelinePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Browse this period' })).toHaveAttribute(
        'href',
        '/episodes?date_from=2026-05-01&date_to=2026-05-31'
      )
    })
  })
})
