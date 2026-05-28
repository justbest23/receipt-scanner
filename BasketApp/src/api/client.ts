const BASE = 'https://basket.trog.co.za';

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
  updateReceipt: (id: number, data: object) =>
    request(`/receipts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

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

  // Meals / Recipes
  recipes: () => request('/meals/recipes'),
  recipe: (id: number) => request(`/meals/recipes/${id}`),
  createRecipe: (data: object) =>
    request('/meals/recipes', { method: 'POST', body: JSON.stringify(data) }),
  importRecipeUrl: (url: string) =>
    request('/meals/recipes/import-url', { method: 'POST', body: JSON.stringify({ url }) }),
  deleteRecipe: (id: number) => request(`/meals/recipes/${id}`, { method: 'DELETE' }),
  addIngredient: (recipeId: number, data: object) =>
    request(`/meals/recipes/${recipeId}/ingredients`, { method: 'POST', body: JSON.stringify(data) }),
  deleteIngredient: (ingredientId: number) =>
    request(`/meals/ingredients/${ingredientId}`, { method: 'DELETE' }),
  setInstructions: (recipeId: number, instructions: string) =>
    request(`/meals/recipes/${recipeId}/instructions`, { method: 'POST', body: JSON.stringify({ instructions }) }),
  shoppingList: (recipeIds: number[]) =>
    request(`/meals/shopping?recipe_ids=${recipeIds.join(',')}`),

  // Households
  households: () => request('/households'),
  household: (id: number) => request(`/households/${id}`),
  householdAnalytics: (id: number) => request(`/households/${id}/analytics`),
  householdHistory: (id: number, skip = 0, limit = 40) =>
    request(`/households/${id}/history?skip=${skip}&limit=${limit}`),
  createHousehold: (name: string) =>
    request('/households', { method: 'POST', body: JSON.stringify({ name }) }),
  joinHousehold: (code: string) =>
    request('/households/join', { method: 'POST', body: JSON.stringify({ code }) }),
  deleteHousehold: (id: number) => request(`/households/${id}`, { method: 'DELETE' }),
  leaveHousehold: (id: number) => request(`/households/${id}/leave`, { method: 'DELETE' }),
  generateInvite: (id: number) => request(`/households/${id}/invite`, { method: 'POST' }),
  deleteInvite: (id: number) => request(`/households/${id}/invite`, { method: 'DELETE' }),
  removeMember: (householdId: number, userId: number) =>
    request(`/households/${householdId}/members/${userId}`, { method: 'DELETE' }),
  updateMemberRole: (householdId: number, userId: number, role: string) =>
    request(`/households/${householdId}/members/${userId}`, { method: 'PATCH', body: JSON.stringify({ role }) }),

  // Spend Groups
  spendGroups: () => request('/api/spend-groups'),
  spendGroup: (id: number) => request(`/api/spend-groups/${id}`),
  spendGroupBalance: (id: number) => request(`/api/spend-groups/${id}/balance`),
  createSpendGroup: (data: object) =>
    request('/api/spend-groups', { method: 'POST', body: JSON.stringify(data) }),
  updateSpendGroup: (id: number, data: object) =>
    request(`/api/spend-groups/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteSpendGroup: (id: number) => request(`/api/spend-groups/${id}`, { method: 'DELETE' }),
  addSpendMember: (groupId: number, username: string) =>
    request(`/api/spend-groups/${groupId}/members`, { method: 'POST', body: JSON.stringify({ username }) }),
  removeSpendMember: (groupId: number, userId: number) =>
    request(`/api/spend-groups/${groupId}/members/${userId}`, { method: 'DELETE' }),
};
