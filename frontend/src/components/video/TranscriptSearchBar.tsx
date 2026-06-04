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
    <form className="grid gap-3 sm:grid-cols-[1fr_auto]" onSubmit={handleSubmit}>
      <label htmlFor="transcript-search" className="sr-only">
        Search inside this VOD
      </label>
      <input
        id="transcript-search"
        name="transcript-search"
        type="search"
        defaultValue={initialQuery}
        placeholder="Search inside this VOD..."
        className="form-control"
        aria-label="Search inside this VOD"
      />
      <button className="btn-primary" type="submit">
        Search VOD
      </button>
    </form>
  );
}
