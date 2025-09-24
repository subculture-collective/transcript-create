export function toVideoId(videoOrUrl: string): string {
  // Extracts YouTube video ID from URL or returns the input if it looks like an ID
  const urlMatch = videoOrUrl.match(/[?&]v=([a-zA-Z0-9_-]{6,})/);
  if (urlMatch) return urlMatch[1];
  const short = videoOrUrl.match(/youtu\.be\/([a-zA-Z0-9_-]{6,})/);
  if (short) return short[1];
  return videoOrUrl;
}
