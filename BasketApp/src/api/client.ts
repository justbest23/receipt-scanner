const BASE = 'http://basket.trog.co.za';

async function request(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...opts.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/auth/me'),
  updateProfile: (body: object) =>
    request('/auth/profile', { method: 'PATCH', body: JSON.stringify(body) }),

  // Receipts
  receipts: (skip = 0, limit = 40) => request(`/receipts?skip=${skip}&limit=${limit}`),
  receipt: (id: number) => request(`/receipts/${id}`),
  deleteReceipt: (id: number) => request(`/receipts/${id}`, { method: 'DELETE' }),
  confirmReceipt: (data: object) =>
    request('/receipts/confirm', { method: 'POST', body: JSON.stringify(data) }),

  // Scan
  scan: async (uri: string, type: string, name: string) => {
    const form = new FormData();
    form.append('file', { uri, type, name } as any);
    const res = await fetch(`${BASE}/scan`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Scan failed' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  // Analytics
  summary: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/analytics/summary${q ? '?' + q : ''}`);
  },
  stores: () => request('/analytics/stores'),

  // Spend groups
  spendGroups: () => request('/api/spend-groups'),
};
