import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import SearchPage from '../routes/SearchPage'
import { api, http } from '../services'
import { renderWithProviders } from './test-utils'

const searchParamsMock = vi.fn()
let currentSearchParams = new URLSearchParams()

vi.mock('../services', async () => {
  const actual = await vi.importActual<typeof import('../services')>('../services')
  return {
    ...actual,
    track: vi.fn(),
  }
})

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useSearchParams: () => [currentSearchParams, searchParamsMock],
  }
})

describe('SearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentSearchParams = new URLSearchParams()

    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never
      }
      return { json: vi.fn().mockResolvedValue({}) } as never
    }) as never)
  })

  it('forwards URL filters to grouped search and shows grouped actions', async () => {
    currentSearchParams = new URLSearchParams({
      q: 'rent',
      source: 'native',
      category: 'news',
      video_id: 'video-1',
      limit: '25',
      offset: '50',
    })

    const searchGroupedMock = vi.spyOn(api, 'searchGrouped').mockResolvedValue({
      total_moments: 1,
      total_videos: 1,
      groups: [
        {
          video: {
            id: 'video-1',
            youtube_id: 'abc123',
            title: 'VOD one',
            channel_name: 'Channel Alpha',
            duration_seconds: 1200,
            uploaded_at: '2026-05-10T00:00:00Z',
          },
          moments: [
            {
              id: 1,
              video_id: 'video-1',
              start_ms: 12000,
              end_ms: 18000,
              snippet: 'the <mark>rent</mark> is too high',
              source: 'whisper',
            },
          ],
        },
      ],
    } as never)

    renderWithProviders(<SearchPage />)

    await waitFor(() => {
      expect(searchGroupedMock).toHaveBeenCalledWith(
        'rent',
        expect.objectContaining({
          source: 'native',
          category: 'news',
          video_id: 'video-1',
          limit: 25,
          offset: 50,
        })
      )
    })

    await waitFor(() => {
      expect(screen.getByText('Play all matches')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Copy quote' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Save moment' })).toBeInTheDocument()
    })
  })
})
