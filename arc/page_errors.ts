// Observe only contexts the test itself requests. Never alter application handlers or assertions.
import { test } from '@playwright/test';
export function register() {
  test.use({ context: async ({ context }, use, testInfo) => {
    let remaining = 8;
    const responseShapes = new Map();
    const listeners = new Map();
    const attach = page => {
      if (listeners.has(page)) return;
      const report = message => {
        if (remaining-- > 0) console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(String(message).slice(0, 1600)));
      };
      const onError = error => report(error.stack || error);
      // A generated app does most of its work over fetch/XHR, so a failing API
      // call is what empties a list; reporting navigations alone said nothing
      // about it. One line per distinct method+status+path: a view that reloads
      // would otherwise spend the whole budget on the same failure.
      const reported = new Set();
      const onResponse = response => {
        if (response.frame() !== page.mainFrame()) return;
        const request = response.request();
        // Keep routing evidence without credentials, query values or fragments.
        const url = new URL(response.url());
        const where = `${url.origin}${url.pathname}`;
        if (response.status() < 400) {
          // Successful HTTP with the wrong client interpretation can silently
          // empty a view. Record only structure, never record values/query data.
          const key = `${request.method()} ${where}`;
          if (response.status() < 200 || response.status() === 204 || responseShapes.size >= 3
              || responseShapes.has(key) || !['fetch', 'xhr'].includes(request.resourceType())
              || !response.headers()['content-type']?.includes('application/json')) return;
          const size = Number(response.headers()['content-length']);
          if (!Number.isFinite(size) || size <= 0 || size > 65536) return;
          responseShapes.set(key, null);
          response.json().then(body => {
            const shape = Array.isArray(body) ? `array(length=${body.length})`
              : body && typeof body === 'object' ? `object(keys=${Object.keys(body).slice(0, 12).join(',')})`
              : body === null ? 'null' : typeof body;
            responseShapes.set(key, `Response schema ${key}: ${shape}`);
          }).catch(() => {});
          return;
        }
        const line = request.isNavigationRequest()
          ? `Navigation HTTP ${response.status()} ${where}`
          : `Request HTTP ${response.status()} ${request.method()} ${where}`;
        if (reported.has(line)) return;
        reported.add(line);
        report(line);
      };
      // An app that catches its own failure renders a placeholder and throws
      // nothing, so `pageerror` never fires and only the symptom survives. Take
      // its error log, on a small budget of its own so ordinary chatter cannot
      // crowd out the page errors and failed requests above.
      let logged = 3;
      const onConsole = message => {
        const text = String(message.text());
        // The browser's own note for a failed request; `onResponse` already
        // reports those with their method, status and path.
        if (message.type() !== 'error' || text.startsWith('Failed to load resource')) return;
        if (reported.has(text) || logged-- <= 0) return;
        reported.add(text);
        report('Console error: ' + text);
      };
      listeners.set(page, { onError, onResponse, onConsole });
      page.on('pageerror', onError);
      page.on('response', onResponse);
      page.on('console', onConsole);
    };
    context.pages().forEach(attach);
    context.on('page', attach);
    try { await use(context); }
    finally {
      if (testInfo.status !== testInfo.expectedStatus) {
        // The URL is needed to distinguish a missing control from a transition
        // that had not mounted yet. Keep path only; queries can carry secrets.
        for (const page of context.pages().slice(0, 2)) {
          try {
            const url = new URL(page.url());
            console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(
              `Page URL at failure: ${url.origin}${url.pathname}`));
          } catch (_) { /* A page may already have closed. */ }
        }
        for (const shape of responseShapes.values()) {
          if (shape && remaining-- > 0) console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(shape));
        }
      }
      context.off('page', attach);
      for (const [page, listener] of listeners) {
        page.off('pageerror', listener.onError);
        page.off('response', listener.onResponse);
        page.off('console', listener.onConsole);
      }
    }
  } });
}
