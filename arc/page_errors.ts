// Observe only contexts the test itself requests. Never alter application handlers or assertions.
import { test } from '@playwright/test';
export function register() {
  test.use({ context: async ({ context }, use) => {
    let remaining = 8;
    const listeners = new Map();
    const attach = page => {
      if (listeners.has(page)) return;
      const report = message => {
        if (remaining-- > 0) console.error('__OCTOS_PAGE_ERROR__' + JSON.stringify(String(message).slice(0, 1600)));
      };
      const onError = error => report(error.stack || error);
      const onResponse = response => {
        if (response.status() < 400 || !response.request().isNavigationRequest()) return;
        if (response.frame() !== page.mainFrame()) return;
        // Keep routing evidence without credentials, query values or fragments.
        const url = new URL(response.url());
        report(`Navigation HTTP ${response.status()} ${url.origin}${url.pathname}`);
      };
      listeners.set(page, { onError, onResponse });
      page.on('pageerror', onError);
      page.on('response', onResponse);
    };
    context.pages().forEach(attach);
    context.on('page', attach);
    try { await use(context); }
    finally {
      context.off('page', attach);
      for (const [page, listener] of listeners) {
        page.off('pageerror', listener.onError);
        page.off('response', listener.onResponse);
      }
    }
  } });
}
