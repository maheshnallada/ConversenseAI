// API client for Conversense AI backend services

const BASE_URL = '/api/v1';

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    ...options.headers,
  };

  if (!(options.body instanceof FormData) && !(options.body instanceof Blob)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errDetail = `${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      errDetail = errJson.detail || errJson.message || errDetail;
    } catch {
      // ignore
    }
    const error = new Error(errDetail);
    error.status = res.status;
    throw error;
  }

  return res.json();
}

export const api = {
  // Analytics
  getOverview: (tenant = 'health_campaign') =>
    request('/analytics/overview', { headers: { 'X-Tenant-Id': tenant } }),

  getQuality: (tenant = 'health_campaign') =>
    request('/analytics/quality', { headers: { 'X-Tenant-Id': tenant } }),

  getCost: (tenant = 'health_campaign') =>
    request('/analytics/cost', { headers: { 'X-Tenant-Id': tenant } }),

  // Interactions
  getInteractionsList: (tenant = 'health_campaign') =>
    request('/interactions-list', { headers: { 'X-Tenant-Id': tenant } }),

  getInteractionsPage: (params = {}, tenant = 'health_campaign') => {
    const q = new URLSearchParams(params).toString();
    return request(`/interactions?${q}`, { headers: { 'X-Tenant-Id': tenant } });
  },

  getInteraction: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}`, { headers: { 'X-Tenant-Id': tenant } }),

  getTimeline: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/timeline`, { headers: { 'X-Tenant-Id': tenant } }),

  getEvaluations: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/evaluations`, { headers: { 'X-Tenant-Id': tenant } }),

  evaluate: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/evaluate`, {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
    }),

  getAudioUrl: (id) =>
    `${BASE_URL}/interactions/${encodeURIComponent(id)}/audio`,

  submitReview: (id, data, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/reviews`, {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: JSON.stringify(data),
    }),

  listReviews: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/reviews`, { headers: { 'X-Tenant-Id': tenant } }),

  // Ingestion
  uploadZip: async (file, tenant = 'health_campaign') => {
    const res = await fetch(`${BASE_URL}/interactions/upload-zip?tenant_id=${encodeURIComponent(tenant)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/zip' },
      body: file,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || 'Upload failed');
    }
    return res.json();
  },

  processPath: (path, tenant = 'health_campaign') =>
    request('/interactions/process-and-evaluate', {
      method: 'POST',
      body: JSON.stringify({ call_folder_path: path, tenant_id: tenant }),
    }),

  seedAll: (limit = 50, tenant = 'health_campaign') =>
    request(`/interactions/seed-all?limit=${limit}`, {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
    }),

  // Benchmark & Evaluators
  getBenchmark: (tenant = 'health_campaign') =>
    request(`/golden-dataset/benchmark?tenant_id=${encodeURIComponent(tenant)}`),

  importGolden: (csvPath = null) =>
    request('/golden-dataset/import', {
      method: 'POST',
      body: csvPath ? JSON.stringify({ csv_path: csvPath }) : undefined,
    }),

  getEvaluators: () =>
    request('/evaluators'),

  getUseCases: () =>
    request('/use-cases'),
};
