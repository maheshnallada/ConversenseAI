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
