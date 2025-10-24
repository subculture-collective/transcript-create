import { useEffect, useState } from 'react';
import { http } from '../../services/api';

type EventRow = {
  id: number;
  created_at: string;
  user_id?: string | null;
  session_token?: string | null;
  type: string;
  payload: any;
};

export default function AdminEvents() {
  const [items, setItems] = useState<EventRow[]>([]);
  const [type, setType] = useState('');
  const [email, setEmail] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [summary, setSummary] = useState<{
    by_type: Array<{ type: string; count: number }>;
    by_day: Array<{ day: string; count: number }>;
  } | null>(null);

  async function fetchEvents() {
    const params = new URLSearchParams();
    if (type) params.set('type', type);
    if (email) params.set('user_email', email);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    const res = await http
      .get('admin/events', { searchParams: params })
      .json<{ items: EventRow[] }>();
    setItems(res.items);
  }
  async function fetchSummary() {
    const params = new URLSearchParams();
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    const res = await http
      .get('admin/events/summary', { searchParams: params })
      .json<typeof summary>();
    setSummary(res as any);
  }

  useEffect(() => {
    fetchEvents();
    fetchSummary();
  }, []);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <div>
          <label className="block text-sm">Type</label>
          <input
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="rounded border px-2 py-1"
          />
        </div>
        <div>
          <label className="block text-sm">User Email</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border px-2 py-1"
          />
        </div>
        <div>
          <label className="block text-sm">Start</label>
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded border px-2 py-1"
          />
        </div>
        <div>
          <label className="block text-sm">End</label>
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded border px-2 py-1"
          />
        </div>
        <button
          className="btn"
          onClick={() => {
            fetchEvents();
            fetchSummary();
          }}
        >
          Apply
        </button>
        <a
          className="btn"
          href={`/api/admin/events.csv?${new URLSearchParams(Object.fromEntries(Object.entries({ type, user_email: email, start, end }).filter(([, v]) => !!v)))}`}
        >
          Export CSV
        </a>
      </div>
      {summary && (
        <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded border p-3">
            <h3 className="mb-2 font-semibold">By Type</h3>
            <ul className="text-sm">
              {summary.by_type.map((x) => (
                <li key={x.type} className="flex justify-between">
                  <span>{x.type}</span>
                  <span>{x.count}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded border p-3">
            <h3 className="mb-2 font-semibold">By Day</h3>
            <ul className="text-sm">
              {summary.by_day.map((x) => (
                <li key={x.day} className="flex justify-between">
                  <span>{x.day}</span>
                  <span>{x.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b bg-stone-100">
              <th className="px-2 py-1 text-left">ID</th>
              <th className="px-2 py-1 text-left">Time</th>
              <th className="px-2 py-1 text-left">User</th>
              <th className="px-2 py-1 text-left">Type</th>
              <th className="px-2 py-1 text-left">Payload</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id} className="border-b">
                <td className="px-2 py-1">{e.id}</td>
                <td className="px-2 py-1">{new Date(e.created_at).toLocaleString()}</td>
                <td className="px-2 py-1">{e.user_id || 'anon'}</td>
                <td className="px-2 py-1">{e.type}</td>
                <td className="px-2 py-1">
                  <pre className="whitespace-pre-wrap">{JSON.stringify(e.payload, null, 2)}</pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
