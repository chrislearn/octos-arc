// Returns parsed response JSON directly (empty success => null); rejects non-2xx.
// This is NOT a Response and does NOT add {ok,value,data,error} wrappers.
// Example: const items = await requestJson('/api/items'); setItems(items).
// Plain object/array bodies are JSON-encoded; strings are sent unchanged.
// Use fetch directly for non-JSON endpoints.
export async function requestJson(url, options = {}) {
  const input = options.body;
  const jsonBody = input != null && typeof input === 'object' &&
    (Array.isArray(input) || Object.getPrototypeOf(input) === Object.prototype ||
      Object.getPrototypeOf(input) === null);
  const body = jsonBody ? JSON.stringify(input) : input;
  const headers = new Headers(options.headers);
  if ((jsonBody || typeof body === 'string') && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(url, {...options, body, headers});
  const responseBody = await response.text();
  if (!response.ok) {
    let message = responseBody;
    try {
      const parsed = JSON.parse(responseBody);
      if (typeof parsed.error === 'string') message = parsed.error;
      else if (typeof parsed.error?.message === 'string') message = parsed.error.message;
      else if (typeof parsed.message === 'string') message = parsed.message;
    } catch { /* Preserve plain-text errors. */ }
    const error = new Error(message || response.statusText || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (!responseBody.trim()) return null;
  try {
    return JSON.parse(responseBody);
  } catch {
    const error = new Error(`Invalid JSON response (HTTP ${response.status})`);
    error.status = response.status;
    throw error;
  }
}
