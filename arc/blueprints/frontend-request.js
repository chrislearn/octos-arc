// Optional JSON request helper; use fetch directly for non-JSON endpoints.
export async function requestJson(url, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body != null && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(url, {...options, headers});
  if (!response.ok) throw new Error(await response.text() || `HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}
