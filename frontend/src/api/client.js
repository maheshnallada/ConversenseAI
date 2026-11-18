// API client for Conversense AI backend services

const BASE_URL = '/api/v1';

/**
 * @typedef {Object} BenchmarkReport
 * @property {number} total_interactions
 * @property {Object} dimension_metrics
 * @property {Object} confusion_matrices
 * @property {number} compliance_false_negatives
 * @property {number} compliance_false_positives
 * @property {number} abstention_rate
 * @property {string} summary_notes
 * @property {Object} details
 */

/**
 * @typedef {Object} GoldenRecordResult
 * @property {string} call_id
 * @property {'ready' | 'failed' | 'excluded'} evaluation_status
 * @property {string | null} evaluation_run_id
 * @property {boolean} reused
 * @property {string | null} error
 */

/**
 * @typedef {Object} GoldenBenchmarkImportResult
 * @property {string} dataset_hash
 * @property {number} records_seen
 * @property {number} labels_imported
 * @property {number} test_records_excluded
 * @property {number} evaluations_created
 * @property {number} evaluations_reused
 * @property {number} evaluations_failed
 * @property {GoldenRecordResult[]} records
 * @property {BenchmarkReport} report
 */

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

  // Call imports
  getStagedCallFolders: (tenant = 'health_campaign') =>
    request('/imports/staged-calls', {
      headers: { 'X-Tenant-Id': tenant },
    }),

  importStagedCallFolders: (folderIds, tenant = 'health_campaign') =>
    request('/imports/staged-calls', {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: JSON.stringify({ folder_ids: folderIds }),
    }),

  importCallFolderFiles: (files, tenant = 'health_campaign') => {
    const formData = new FormData();
    for (const file of files) {
      formData.append(
        'files',
        file,
        file.webkitRelativePath || file.name,
      );
    }
    return request('/imports/upload-calls', {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: formData,
    });
  },

  getInteraction: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}`, { headers: { 'X-Tenant-Id': tenant } }),

  getObservability: (id, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(id)}/observability`, {
      headers: { 'X-Tenant-Id': tenant },
    }),

  getTimeline: async (id, tenant = 'health_campaign') => {
    try {
      return await request(`/interactions/${encodeURIComponent(id)}/timeline`, {
        headers: { 'X-Tenant-Id': tenant },
      });
    } catch (error) {
      if (error.status === 404) return null;
      throw error;
    }
  },

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
  /** @returns {Promise<BenchmarkReport>} */
  getBenchmark: (tenant = 'health_campaign') =>
    request('/golden-dataset/benchmark', { headers: { 'X-Tenant-Id': tenant } }),

  /** @returns {Promise<Blob>} */
  exportBenchmarkResults: async (format = 'csv', tenant = 'health_campaign') => {
    const res = await fetch(`${BASE_URL}/golden-dataset/benchmark/export?format=${encodeURIComponent(format)}`, {
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
    return await res.blob();
  },

  /** @returns {Promise<GoldenBenchmarkImportResult>} */
  importGolden: (csvPath = null, tenant = 'health_campaign') =>
    request('/golden-dataset/import', {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: csvPath ? JSON.stringify({ csv_path: csvPath }) : undefined,
    }),

  // Scaling & Queue Operations
  getQueueStats: (tenant = 'health_campaign') =>
    request('/queue/stats', { headers: { 'X-Tenant-Id': tenant } }),

  getDLQ: (limit = 100, tenant = 'health_campaign') =>
    request(`/queue/dlq?limit=${limit}`, { headers: { 'X-Tenant-Id': tenant } }),

  replayQueueJob: (interactionId, targetStage = 'general', tenant = 'health_campaign') =>
    request('/queue/replay', {
      method: 'POST',
      headers: { 'X-Tenant-Id': tenant },
      body: JSON.stringify({ interaction_id: interactionId, target_stage: targetStage }),
    }),

  getInteractionStages: (interactionId, tenant = 'health_campaign') =>
    request(`/interactions/${encodeURIComponent(interactionId)}/stages`, {
      headers: { 'X-Tenant-Id': tenant },
    }),
};
