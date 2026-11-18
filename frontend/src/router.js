export const VALID_TABS = [
  'overview',
  'interactions',
  'drilldown',
  'benchmark',
  'import-calls',
  'scaling',
];

/**
 * Parse current URL (path, hash, and search params) to extract active tab and callId.
 */
export function getRouteFromLocation() {
  if (typeof window === 'undefined') {
    return { tab: 'overview', callId: '' };
  }

  let pathname = window.location.pathname || '/';
  let search = window.location.search || '';

  // Support hash routing fallback: #/drilldown?call_id=xxx
  if (window.location.hash && window.location.hash.startsWith('#/')) {
    const rawHash = window.location.hash.slice(1); // remove '#'
    const [hPath, hSearch] = rawHash.split('?');
    pathname = hPath || '/';
    if (hSearch) search = `?${hSearch}`;
  }

  const cleanPath = pathname.replace(/\/+$/, '') || '/';
  const params = new URLSearchParams(search);
  const callId = params.get('call_id') || params.get('callId') || '';

  let tab = 'overview';
  const segment = cleanPath.startsWith('/') ? cleanPath.slice(1) : cleanPath;

  if (VALID_TABS.includes(segment)) {
    tab = segment;
  } else if (cleanPath === '/' || cleanPath === '/dashboard') {
    tab = 'overview';
  }

  return { tab, callId };
}

/**
 * Push or replace current URL without full page reload.
 */
export function pushRoute(tab, callId = '', replace = false) {
  if (typeof window === 'undefined') return;

  const validTab = VALID_TABS.includes(tab) ? tab : 'overview';
  let path = validTab === 'overview' ? '/' : `/${validTab}`;

  if (validTab === 'drilldown' && callId) {
    path = `/drilldown?call_id=${encodeURIComponent(callId)}`;
  }

  const currentPathWithSearch =
    (window.location.pathname || '/') + (window.location.search || '');

  if (currentPathWithSearch === path) return;

  const state = { tab: validTab, callId };
  if (replace) {
    window.history.replaceState(state, '', path);
  } else {
    window.history.pushState(state, '', path);
  }

  // Dispatch custom route change event for components listening
  window.dispatchEvent(new CustomEvent('conversense:routechange', { detail: state }));
}
