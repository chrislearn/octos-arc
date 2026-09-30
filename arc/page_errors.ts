// Observe only contexts the test itself requests. Never alter application handlers or assertions.
import { test } from '@playwright/test';
export function register() {
  test.use({ context: async ({ context }, use, testInfo) => {
    // Keep only modifier shortcuts, never typed text or clipboard contents.
    // This runs before the app installs its handlers and does not cancel events.
    await context.addInitScript(() => {
      const shortcuts: Array<{ key: string; ctrl: boolean; meta: boolean; target: string; at: number }> = [];
      (window as any).__octosShortcutEvents = shortcuts;
      document.addEventListener('keydown', event => {
        if (!event.ctrlKey && !event.metaKey) return;
        if (!['c', 'x', 'v', 'z', 'y'].includes(event.key.toLowerCase())) return;
        shortcuts.push({ key: event.key, ctrl: event.ctrlKey, meta: event.metaKey,
          target: event.target instanceof Element ? event.target.tagName : '', at: Date.now() });
        if (shortcuts.length > 8) shortcuts.shift();
      }, true);
    });
    const observations: any[] = [];
    const counts = new Map<string, number>();
    const observe = (kind, page, message, extra = {}) => {
      const count = counts.get(kind) || 0;
      counts.set(kind, count + 1);
      if (count >= 20) return;
      let url = '';
      try { const value = new URL(page.url()); url = value.origin + value.pathname; } catch (_) {}
      observations.push({ kind, url, message: String(message).slice(0, 4000),
        timestamp: Date.now(), ...extra });
    };
    let remaining = 8;
    const responseShapes = new Map();
    const listeners = new Map();
    const mutationRequests = new Map();
    const attach = page => {
      if (listeners.has(page)) return;
      const report = message => {
        if (remaining-- > 0) console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(String(message).slice(0, 1600)));
      };
      const onError = error => { observe('pageerror', page, error.stack || error); report(error.stack || error); };
      const onRequestFailed = request => observe('request_failed', page,
        request.failure()?.errorText || 'request failed', { resourceType: request.resourceType() });
      const onRequest = request => {
        if (!['PUT', 'POST', 'PATCH', 'DELETE'].includes(request.method())
            || !['fetch', 'xhr'].includes(request.resourceType())) return;
        try {
          const url = new URL(request.url());
          if (!url.pathname.startsWith('/api/') || url.origin !== new URL(page.url()).origin) return;
          const recent = mutationRequests.get(page) || [];
          recent.push({ at: Date.now(), method: request.method(), path: url.pathname });
          if (recent.length > 16) recent.shift();
          mutationRequests.set(page, recent);
        } catch (_) { /* The page may be navigating. */ }
      };
      // A generated app does most of its work over fetch/XHR, so a failing API
      // call is what empties a list; reporting navigations alone said nothing
      // about it. One line per distinct method+status+path: a view that reloads
      // would otherwise spend the whole budget on the same failure.
      const reported = new Set();
      const onResponse = response => {
        try { if (response.frame() !== page.mainFrame()) return; }
        catch (_) { return; } // Service worker responses have no frame.
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
        observe('http_response', page, line, {status: response.status(), method: request.method(), path: url.pathname});
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
        observe('console_error', page, text);
        if (reported.has(text) || logged-- <= 0) return;
        reported.add(text);
        report('Console error: ' + text);
      };
      listeners.set(page, { onError, onResponse, onConsole, onRequestFailed, onRequest });
      page.on('pageerror', onError);
      page.on('request', onRequest);
      page.on('response', onResponse);
      page.on('console', onConsole);
      page.on('requestfailed', onRequestFailed);
    };
    context.pages().forEach(attach);
    context.on('page', attach);
    try { await use(context); }
    finally {
      await testInfo.attach('arc-runtime-observations', {
        body: Buffer.from(JSON.stringify(observations)), contentType: 'application/json'
      });
      if (testInfo.status !== testInfo.expectedStatus) {
        // The URL is needed to distinguish a missing control from a transition
        // that had not mounted yet. Keep path only; queries can carry secrets.
        for (const page of context.pages().slice(0, 2)) {
          try {
            const url = new URL(page.url());
            console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(
              `Page URL at failure: ${url.origin}${url.pathname}`));
          } catch (_) { /* A page may already have closed. */ }
          try {
            const shortcuts = await page.evaluate(() => (window as any).__octosShortcutEvents || []);
            if (shortcuts.length) {
              console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(
                `Shortcut keydown events before failure: ${JSON.stringify(shortcuts.map(
                  ({at, ...event}) => event))}`));
              const after = (mutationRequests.get(page) || []).filter(
                request => request.at >= shortcuts[shortcuts.length - 1].at);
              console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(
                `Same-origin /api mutation requests after final shortcut keydown: ${after.length
                  ? after.map(({method, path}) => `${method} ${path}`).join(', ') : 'none'}`));
            }
          } catch (_) { /* Optional diagnostics cannot change the verdict. */ }
        }
        for (const shape of responseShapes.values()) {
          if (shape && remaining-- > 0) console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(shape));
        }
      }
      context.off('page', attach);
      for (const [page, listener] of listeners) {
        page.off('pageerror', listener.onError);
        page.off('request', listener.onRequest);
        page.off('response', listener.onResponse);
        page.off('console', listener.onConsole);
        page.off('requestfailed', listener.onRequestFailed);
      }
    }
  } });
}
