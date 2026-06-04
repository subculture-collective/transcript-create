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

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders export button', () => {
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} />
    )

    expect(screen.getByText('Export')).toBeInTheDocument()
  })

  it('shows export formats when opened', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    expect(screen.getAllByText('SRT')).toHaveLength(1)
    expect(screen.getAllByText('VTT')).toHaveLength(1)
    expect(screen.getAllByText('JSON')).toHaveLength(1)
    expect(screen.getByText('PDF')).toBeInTheDocument()
  })

  it('allows download when user is Pro', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    const srtLinks = screen.getAllByText('SRT')
    await user.click(srtLinks[0])

    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'srt', source: 'best' },
    })
  })

  it('allows non-PDF download when user is not Pro', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={false} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    const srtLinks = screen.getAllByText('SRT')
    await user.click(srtLinks[0])

    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'srt', source: 'best' },
    })
  })

  it('allows PDF download when user is not Pro', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={false} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    await user.click(screen.getByText('PDF'))

    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'pdf', source: 'whisper' },
    })
  })

  it('has correct download links for native transcripts', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} />
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

  it('tracks different export formats correctly', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    // Test native SRT
    await user.click(screen.getAllByText('SRT')[0])
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'srt', source: 'best' },
    })

    await user.click(screen.getAllByText('VTT')[0])
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'vtt', source: 'best' },
    })

    // Test PDF
    await user.click(screen.getByText('PDF'))
    expect(services.track).toHaveBeenCalledWith({
      type: 'export_click',
      payload: { videoId: mockVideoId, format: 'pdf', source: 'whisper' },
    })
  })

  it('shows per-section export info', async () => {
    const user = userEvent.setup()
    render(
      <ExportMenu videoId={mockVideoId} isPro={true} />
    )

    const exportButton = screen.getByText('Export')
    await user.click(exportButton)

    expect(screen.getByText('Per-section')).toBeInTheDocument()
    expect(
      screen.getByText(/Use the inline copy link next to any segment/i)
    ).toBeInTheDocument()
  })
})
