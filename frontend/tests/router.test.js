import assert from 'node:assert/strict';
import test from 'node:test';

import { getRouteFromLocation, pushRoute, VALID_TABS } from '../src/router.js';

test('router parses default root route', () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: { pathname: '/', search: '', hash: '' },
    history: { pushState: () => {}, replaceState: () => {} },
    dispatchEvent: () => {},
  };

  const route = getRouteFromLocation();
  assert.equal(route.tab, 'overview');
  assert.equal(route.callId, '');

  globalThis.window = originalWindow;
});

test('router parses drilldown route with query call_id', () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      pathname: '/drilldown',
      search: '?call_id=call-1234',
      hash: '',
    },
    history: { pushState: () => {}, replaceState: () => {} },
    dispatchEvent: () => {},
  };

  const route = getRouteFromLocation();
  assert.equal(route.tab, 'drilldown');
  assert.equal(route.callId, 'call-1234');

  globalThis.window = originalWindow;
});

test('router parses hash route fallback', () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      pathname: '/',
      search: '',
      hash: '#/benchmark',
    },
    history: { pushState: () => {}, replaceState: () => {} },
    dispatchEvent: () => {},
  };

  const route = getRouteFromLocation();
  assert.equal(route.tab, 'benchmark');

  globalThis.window = originalWindow;
});

test('router handles pushRoute with path updates', () => {
  const originalWindow = globalThis.window;
  let pushed = null;
  globalThis.window = {
    location: { pathname: '/', search: '', hash: '' },
    history: {
      pushState: (state, title, url) => {
        pushed = { state, title, url };
      },
      replaceState: () => {},
    },
    dispatchEvent: () => {},
  };

  pushRoute('drilldown', 'call-999');
  assert.deepEqual(pushed, {
    state: { tab: 'drilldown', callId: 'call-999' },
    title: '',
    url: '/drilldown?call_id=call-999',
  });

  globalThis.window = originalWindow;
});
