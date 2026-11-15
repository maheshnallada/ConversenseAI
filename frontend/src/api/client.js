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

  getReliability: (tenant = 'health_campaign') =>
    request('/analytics/reliability', { headers: { 'X-Tenant-Id': tenant } }),

  getUsage: (tenant = 'health_campaign') =>
    request('/analytics/usage', { headers: { 'X-Tenant-Id': tenant } }),

  // Interactions
  getInteractionsPage: (params = {}, tenant = 'health_campaign') => {
    const q = new URLSearchParams(params).toString();
    return request(`/interactions?${q}`, { headers: { 'X-Tenant-Id': tenant } });
  },

  getInteraction: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}`, { headers: { 'X-Tenant-Id': tenant } }),

  getObservability: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/observability`, {
      headers: { 'X-Tenant-Id': tenant },
    }),

  getTimeline: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/timeline`, { headers: { 'X-Tenant-Id': tenant } }),

  getEvaluations: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/evaluations`, { headers: { 'X-Tenant-Id': tenant } }),

  evaluate: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/evaluate`, {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
    }),

  getAudioUrl: async (id, tenant = 'health_campaign') => {
    const res = await fetch(`${BASE_URL}/interactions/${encodeURIComponent(id)}/audio`, {
      headers: { 'X-Tenant-Id': tenant },
    });
    if (!res.ok) {
      let errDetail = `${res.status} ${res.statusText}`;
      try {
        const errJson = await res.json();
        errDetail = errJson.detail || errJson.message || errDetail;
      } catch {
        // ignore
      }
      throw new Error(errDetail);
    }
    return URL.createObjectURL(await res.blob());
  },

  submitReview: (id, data, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/reviews`, {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: JSON.stringify(data),
    }),

  listReviews: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/reviews`, { headers: { 'X-Tenant-Id': tenant } }),

  // Benchmark
  getBenchmark: (tenant = 'health_campaign') =>
    request('/golden-dataset/benchmark', { headers: { 'X-Tenant-Id': tenant } }),

  importGolden: (csvPath = null, tenant = 'health_campaign') =>
    request('/golden-dataset/import', {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: csvPath ? JSON.stringify({ csv_path: csvPath }) : undefined,
    }),

};
