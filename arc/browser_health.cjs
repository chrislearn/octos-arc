// Harness-owned fresh-context probe. No spec helpers, app mutations or injected headers.
const fs = require('fs');
const path = require('path');
(async () => {
  const config = JSON.parse(fs.readFileSync(0, 'utf8'));
  const { chromium } = require(config.module);
  const report = { status: 'passed', observations: [], pages: [], unchecked: [] };
  const declared = (config.dynamicPatterns || []).filter(pattern => typeof pattern === 'string');
  const routes = [...config.paths];
  const discovered = new Set();
  const sameOrigin = new URL(config.baseURL).origin;
  const matchesDeclared = pathname => declared.some(pattern => {
    const parts = pattern.split('/').map(part => part.startsWith(':') ? '[^/]+' : part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    return new RegExp(`^${parts.join('/')}/?$`).test(pathname);
  });
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const started = Date.now();
    for (let index = 0; index < routes.length; index++) {
      const route = routes[index];
      if (Date.now() - started > (config.budgetMs || 40000) - 15000) {
        report.unchecked.push(...routes.slice(index));
        if (report.status === 'passed') report.status = 'unknown';
        break;
      }
      const url = new URL(route, config.baseURL);
      if (url.origin !== new URL(config.baseURL).origin) continue;
      const context = await browser.newContext();
      await context.tracing.start({ screenshots: true, snapshots: true });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(String(e.stack || e)));
      try {
        const response = await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: 10000 });
        if (response && response.status() >= 400) report.observations.push({
          kind: 'document_http_error', confirmed: false, path: url.pathname,
          message: `Document returned ${response.status()} at ${url.pathname}; verify route/auth preconditions`
        });
        await page.waitForFunction(() => document.body && (
          document.body.innerText.trim().length || document.querySelector('canvas,svg,input,button')),
          null, { timeout: 5000 }).catch(() => {});
        await page.waitForFunction(() => !/^(loading[.\s…]*|please wait[.\s…]*)$/i.test(
          document.body?.innerText.trim() || ''), null, { timeout: 5000 }).catch(() => {});
        await page.waitForTimeout(400);
        const state = await page.evaluate(() => ({
          text: document.body?.innerText.trim() || '',
          controls: document.querySelectorAll('input,button,canvas,svg,img').length
        }));
        report.pages.push({ path: url.pathname, textLength: state.text.length, controls: state.controls });
        if (index < config.paths.length && routes.length < config.paths.length + 2) {
          const links = await page.locator('a[href]').evaluateAll(items => items
            .filter(item => item.getClientRects().length > 0 && !item.hasAttribute('download'))
            .map(item => item.href));
          const candidates = [];
          for (const href of links) {
            let candidate;
            try { candidate = new URL(href, url.href); } catch { continue; }
            if (candidate.origin !== sameOrigin
                || /\b(?:logout|delete|remove|reset)\b/i.test(candidate.pathname)
                || routes.includes(candidate.pathname)) continue;
            candidates.push(candidate);
          }
          candidates.sort((left, right) => Number(matchesDeclared(right.pathname)) - Number(matchesDeclared(left.pathname)));
          for (const candidate of candidates) {
            if (routes.includes(candidate.pathname)) continue;
            routes.push(candidate.pathname);
            discovered.add(candidate.pathname);
            if (routes.length >= config.paths.length + 2) break;
          }
        }
        for (const message of [...new Set(errors)].slice(0, 8)) report.observations.push({
          kind: 'pageerror', confirmed: true, path: url.pathname, message,
          reproduction: 'independent fresh browser, no spec or helper executed'
        });
        if (!errors.length && !state.text && !state.controls) report.observations.push({
          kind: 'blank_page', confirmed: true, path: url.pathname,
          message: `No rendered content or controls at ${url.pathname} after browser readiness wait`
        });
        if (/^(loading[.\s…]*|please wait[.\s…]*)$/i.test(state.text) && !errors.length)
          report.status = 'unknown';
        if ((matchesDeclared(url.pathname) || discovered.has(url.pathname)) && !errors.length) {
          await page.reload({ waitUntil: 'domcontentloaded', timeout: 10000 });
          await page.waitForFunction(() => !/^(loading[.\s…]*|please wait[.\s…]*)$/i.test(
            document.body?.innerText.trim() || ''), null, { timeout: 5000 }).catch(() => {});
          await page.waitForTimeout(400);
          const refreshed = await page.evaluate(() => ({
            text: document.body?.innerText.trim() || '',
            controls: document.querySelectorAll('input,button,canvas,svg,img').length
          }));
          report.pages.push({ path: url.pathname, phase: 'refresh',
                              textLength: refreshed.text.length, controls: refreshed.controls });
          if (!errors.length && !refreshed.text && !refreshed.controls) report.observations.push({
            kind: 'blank_page', confirmed: true, path: url.pathname,
            message: `No rendered content or controls at ${url.pathname} after refresh`
          });
          for (const message of [...new Set(errors)].slice(0, 8)) report.observations.push({
            kind: 'pageerror', confirmed: true, path: url.pathname, message,
            reproduction: 'independent fresh browser after direct refresh'
          });
        }
        await page.screenshot({ path: path.join(config.destination, `page-${index}.png`) });
        fs.writeFileSync(path.join(config.destination, `page-${index}.html`), await page.content());
      } catch (e) {
        report.status = 'unknown';
        report.observations.push({ kind: 'navigation_error', confirmed: false,
          path: url.pathname, message: String(e.message || e) });
        for (const message of [...new Set(errors)].slice(0, 8)) report.observations.push({
          kind: 'pageerror', confirmed: true, path: url.pathname, message,
          reproduction: 'independent fresh browser during navigation'
        });
      } finally {
        await context.tracing.stop({ path: path.join(config.destination, `trace-${index}.zip`) });
        await context.close();
      }
    }
    if (report.observations.some(e => e.confirmed)) report.status = 'failed';
    else if (report.observations.length) report.status = 'unknown';
  } catch (e) {
    report.status = 'unknown';
    report.observations.push({kind: 'browser_unavailable', confirmed: false, message: String(e.message || e)});
  } finally {
    if (browser) await browser.close();
  }
  process.stdout.write(JSON.stringify(report));
})().catch(e => { process.stdout.write(JSON.stringify({ status: 'unknown', observations: [
  { kind: 'collector_error', confirmed: false, message: String(e.message || e) }
]})); });
