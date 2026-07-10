import type { FormEvent } from 'react';

type Props = {
  initialQuery: string;
  onSearch: (query: string) => void;
};

export default function TranscriptSearchBar({ initialQuery, onSearch }: Props) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    onSearch(String(data.get('transcript-search') ?? '').trim());
  }

  return (
    <form className="transcript-search" onSubmit={handleSubmit} role="search">
      <label htmlFor="transcript-search" className="sr-only">
        Search inside this VOD
      </label>
      <span
        className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-subtle"
        aria-hidden="true"
      >
        <svg
          className="h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </span>
      <input
        id="transcript-search"
        name="transcript-search"
        type="search"
        defaultValue={initialQuery}
        placeholder="Find a phrase in this episode"
        className="h-12 w-full rounded-lg border border-border bg-canvas/60 pl-11 pr-28 text-ink placeholder:text-subtle focus:border-accent focus:ring-2 focus:ring-accent/20"
        aria-label="Search inside this VOD"
      />
      <button
        className="absolute right-1.5 top-1.5 h-9 rounded-md bg-ink px-4 text-xs font-bold uppercase tracking-[0.12em] text-canvas transition-colors hover:bg-accent"
        type="submit"
      >
        Find
      </button>
    </form>
  );
}
