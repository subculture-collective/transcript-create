import { useCallback, useEffect, useState } from 'react';
import { http } from '../../services/api';

type UserRow = {
  id: string;
  email?: string | null;
  name?: string | null;
  avatar_url?: string | null;
  created_at: string;
};

export default function AdminUsers() {
  const [items, setItems] = useState<UserRow[]>([]);
  const [q, setQ] = useState('');

  const fetchUsers = useCallback(async () => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    const res = await http
      .get('admin/users', { searchParams: params })
      .json<{ items: UserRow[] }>();
    setItems(res.items);
  }, [q]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  return (
    <div>
      <div className="mb-4 flex items-end gap-2">
        <div>
          <label className="block text-sm">Search</label>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="rounded border px-2 py-1"
          />
        </div>
        <button className="btn" onClick={fetchUsers}>
          Apply
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b bg-stone-100">
              <th className="px-2 py-1 text-left">ID</th>
              <th className="px-2 py-1 text-left">Email</th>
              <th className="px-2 py-1 text-left">Name</th>
              <th className="px-2 py-1 text-left">Created</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id} className="border-b">
                <td className="px-2 py-1">{u.id}</td>
                <td className="px-2 py-1">{u.email}</td>
                <td className="px-2 py-1">{u.name}</td>
                <td className="px-2 py-1">{new Date(u.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
