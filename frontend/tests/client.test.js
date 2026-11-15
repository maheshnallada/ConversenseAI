import assert from 'node:assert/strict';
import test from 'node:test';

import { api } from '../src/api/client.js';

test('getTimeline treats an unavailable timeline as optional', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: 'Timeline not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });

  assert.equal(await api.getTimeline('interaction-1'), null);
});

test('staged call listing sends the requested tenant', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify({ calls: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  assert.deepEqual(
    await api.getStagedCallFolders('tenant-import'),
    { calls: [] },
  );
  assert.equal(captured.url, '/api/v1/imports/staged-calls');
  assert.equal(captured.options.headers['X-Tenant-Id'], 'tenant-import');
});

test('staged call import sends folder IDs and the requested tenant', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify({ total_calls: 1 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await api.importStagedCallFolders(['folder-1'], 'tenant-import');

  assert.equal(captured.url, '/api/v1/imports/staged-calls');
  assert.equal(captured.options.method, 'POST');
  assert.equal(captured.options.headers['X-Tenant-Id'], 'tenant-import');
  assert.deepEqual(JSON.parse(captured.options.body), { folder_ids: ['folder-1'] });
});

test('call folder upload preserves relative filenames without setting JSON content type', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify({ total_calls: 1 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  const file = new File(['call manifest'], 'call.json', {
    type: 'application/json',
  });
  Object.defineProperty(file, 'webkitRelativePath', {
    value: 'health-call/call.json',
  });

  await api.importCallFolderFiles([file], 'tenant-import');

  assert.equal(captured.url, '/api/v1/imports/upload-calls');
  assert.equal(captured.options.method, 'POST');
  assert.equal(captured.options.headers['X-Tenant-Id'], 'tenant-import');
  assert.equal(captured.options.headers['Content-Type'], undefined);
  assert.ok(captured.options.body instanceof FormData);
  assert.equal(captured.options.body.getAll('files')[0].name, 'health-call/call.json');
});
