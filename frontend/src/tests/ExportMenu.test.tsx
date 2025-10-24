import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ExportMenu from '../components/ExportMenu'
import * as services from '../services'

vi.mock('../services', () => ({
  track: vi.fn(),
}))

describe('ExportMenu', () => {
  const mockVideoId = 'test-video-id'
  const mockOnRequireUpgrade = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders export button', () => {
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    expect(screen.getByText('Export')).toBeInTheDocument()
  })

  it('shows export formats when opened', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    // Native transcript formats
    expect(screen.getAllByText('SRT')).toHaveLength(2) // Native + YouTube
    expect(screen.getAllByText('VTT')).toHaveLength(2)
    expect(screen.getAllByText('JSON')).toHaveLength(2)
    expect(screen.getByText('PDF')).toBeInTheDocument()
  })

  it('allows download when user is Pro', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    const srtLinks = screen.getAllByText('SRT')
    await user.click(srtLinks[0])

    expect(mockOnRequireUpgrade).not.toHaveBeenCalled()
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'srt', source: 'native' },
    })
  })

  it('blocks download and shows upgrade modal when user is not Pro', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={false} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    const srtLinks = screen.getAllByText('SRT')
    await user.click(srtLinks[0])

    expect(mockOnRequireUpgrade).toHaveBeenCalled()
    expect(services.track).not.toHaveBeenCalled()
  })

  it('has correct download links for native transcripts', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    const srtLink = screen.getAllByText('SRT')[0].closest('a')
    expect(srtLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/transcript.srt`)
    expect(srtLink).toHaveAttribute('download', `video-${mockVideoId}.srt`)

    const vttLink = screen.getAllByText('VTT')[0].closest('a')
    expect(vttLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/transcript.vtt`)

    const jsonLink = screen.getAllByText('JSON')[0].closest('a')
    expect(jsonLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/transcript.json`)

    const pdfLink = screen.getByText('PDF').closest('a')
    expect(pdfLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/transcript.pdf`)
  })

  it('has correct download links for YouTube transcripts', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    // YouTube captions are the second set
    const srtLink = screen.getAllByText('SRT')[1].closest('a')
    expect(srtLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/youtube-transcript.srt`)

    const vttLink = screen.getAllByText('VTT')[1].closest('a')
    expect(vttLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/youtube-transcript.vtt`)

    const jsonLink = screen.getAllByText('JSON')[1].closest('a')
    expect(jsonLink).toHaveAttribute('href', `/api/videos/${mockVideoId}/youtube-transcript.json`)
  })

  it('tracks different export formats correctly', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    // Test native SRT
    await user.click(screen.getAllByText('SRT')[0])
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'srt', source: 'native' },
    })

    // Test YouTube VTT
    await user.click(screen.getAllByText('VTT')[1])
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'vtt', source: 'youtube' },
    })

    // Test PDF
    await user.click(screen.getByText('PDF'))
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'pdf', source: 'native' },
    })
  })

  it('shows per-section export info', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} onRequireUpgrade={mockOnRequireUpgrade} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    expect(screen.getByText('Per-section')).toBeInTheDocument()
    expect(
      screen.getByText(/Use the inline copy link next to any segment/i)
    ).toBeInTheDocument()
  })
})
