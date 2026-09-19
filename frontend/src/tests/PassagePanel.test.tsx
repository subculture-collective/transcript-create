import { createRef } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PassagePanel from '../components/video/PassagePanel';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';

const segments = [
  { start_ms: 0, end_ms: 10000, text: 'Before the passage.' },
  { start_ms: 10000, end_ms: 20000, text: 'The selected passage.' },
  { start_ms: 20000, end_ms: 30000, text: 'After the passage.' },
];
function setup(initialRange = { startMs: 10000, endMs: 20000 }) {
  const playerRef = createRef<YouTubePlayerHandle>();
  playerRef.current = {
    previewRange: vi.fn(),
    seekTo: vi.fn(),
    pause: vi.fn(),
    play: vi.fn(),
    togglePlay: vi.fn(),
    getCurrentTime: vi.fn(() => 12.125),
  };
  const onClose = vi.fn();
  render(
    <PassagePanel
      videoId="video-1"
      title="Test recording"
      initialRange={initialRange}
      durationMs={30000}
      segments={segments}
      playerRef={playerRef}
      onClose={onClose}
    />
  );
  return { player: playerRef.current, onClose };
}

describe('PassagePanel', () => {
  beforeEach(() => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
    vi.mocked(navigator.clipboard.writeText).mockReset().mockResolvedValue(undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it('shows selected text with surrounding context, adjusts a range, previews and copies a reproducible URL', async () => {
    const { player } = setup();
    const context = screen.getByLabelText('Passage in context');
    expect(within(context).getByText('The selected passage.').tagName).toBe('MARK');
    expect(within(context).getByText(/Before the passage/)).toBeInTheDocument();
    expect(within(context).getByText(/After the passage/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('End time'), { target: { value: '25.500' } });
    fireEvent.click(screen.getByRole('button', { name: 'Preview passage' }));
    expect(player.previewRange).toHaveBeenCalledWith(10, 25.5);
    fireEvent.click(screen.getByRole('button', { name: 'Copy passage link' }));
    expect(await screen.findByText('Passage link copied.')).toBeInTheDocument();
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('/api/share/videos/video-1?start_ms=10000&end_ms=25500')
    );
    fireEvent.click(screen.getByRole('button', { name: 'Continue after passage' }));
    expect(player.seekTo).toHaveBeenCalledWith(25.5, { play: true });
  });

  it('extends a selection to adjacent transcript segments', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Include previous segment' }));
    expect(screen.getByLabelText('Start time')).toHaveValue('00:00:00');
    expect(screen.getByRole('button', { name: 'Include previous segment' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Include next segment' }));
    expect(screen.getByLabelText('End time')).toHaveValue('00:00:30');
    expect(screen.getByRole('button', { name: 'Include next segment' })).toBeDisabled();
  });

  it('bounds rendered context for long selections without shortening the shared range', () => {
    const longSegments = Array.from({ length: 1000 }, (_, index) => ({
      start_ms: index * 1000,
      end_ms: (index + 1) * 1000,
      text: `Transcript segment ${index}.`,
    }));
    render(
      <PassagePanel
        videoId="long-video"
        title="Long recording"
        initialRange={{ startMs: 1000, endMs: 999000 }}
        durationMs={1000000}
        segments={longSegments}
        playerRef={createRef<YouTubePlayerHandle>()}
        onClose={vi.fn()}
      />
    );
    const context = screen.getByLabelText('Passage in context');
    expect(context.querySelectorAll('mark')).toHaveLength(200);
    expect(context).toHaveTextContent('798 more segments');
    expect(context).toHaveTextContent('Transcript segment 999.');
    expect((screen.getByLabelText('Passage link') as HTMLInputElement).value).toContain(
      'end_ms=999000'
    );
  });

  it('disables sharing and preview for invalid input rather than silently clamping it', () => {
    setup({ startMs: NaN, endMs: NaN });
    expect(screen.getByRole('alert')).toHaveTextContent('Enter valid');
    expect(screen.getByRole('button', { name: 'Preview passage' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Start time'), { target: { value: '12' } });
    fireEvent.change(screen.getByLabelText('End time'), { target: { value: '11' } });
    expect(screen.getByRole('alert')).toHaveTextContent('after');
    fireEvent.change(screen.getByLabelText('End time'), { target: { value: '31' } });
    expect(screen.getByRole('alert')).toHaveTextContent('within');
    expect(screen.getByRole('button', { name: 'Copy passage link' })).toBeDisabled();
    expect(screen.queryByLabelText('Passage link')).not.toBeInTheDocument();
  });

  it('sets a boundary from playback and reports unavailable playback honestly', () => {
    const { player } = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Set start from playback' }));
    expect(screen.getByLabelText('Start time')).toHaveValue('00:00:12.125');
    vi.mocked(player.getCurrentTime).mockReturnValue(null);
    fireEvent.click(screen.getByRole('button', { name: 'Set end from playback' }));
    expect(screen.getByRole('status')).toHaveTextContent('Playback time is unavailable');
  });

  it('provides manual copying on clipboard denial', async () => {
    vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('denied'));
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Copy passage link' }));
    expect(await screen.findByText(/Select and copy the passage link below/)).toBeInTheDocument();
    expect((screen.getByLabelText('Passage link') as HTMLInputElement).value).toContain(
      'end_ms=20000'
    );
    expect(screen.queryByRole('button', { name: 'Share passage' })).not.toBeInTheDocument();
  });

  it('treats native sharing cancellation as cancellation, without copying or claiming publication', async () => {
    const share = vi.fn().mockRejectedValue(new DOMException('cancelled', 'AbortError'));
    Object.defineProperty(navigator, 'share', { configurable: true, value: share });
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Share passage' }));
    expect(await screen.findByText('Sharing cancelled.')).toBeInTheDocument();
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
  });
});
