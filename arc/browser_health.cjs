// Harness-owned fresh-context probe. No spec helpers, app mutations or injected headers.
const fs = require('fs');
const path = require('path');
(async () => {
  const config = JSON.parse(fs.readFileSync(0, 'utf8'));
  const { chromium } = require(config.module);
  const report = { status: 'passed', observations: [], pages: [] };
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    for (const [index, route] of config.paths.slice(0, 3).entries()) {
      const url = new URL(route, config.baseURL);
      if (url.origin !== new URL(config.baseURL).origin) continue;
      const context = await browser.newContext();
      await context.tracing.start({ screenshots: true, snapshots: true });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(String(e.stack || e)));
      try {
        await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: 10000 });
        await page.waitForFunction(() => document.body && (
          document.body.innerText.trim().length || document.querySelector('canvas,svg,input,button')),
          null, { timeout: 5000 }).catch(() => {});
        await page.waitForTimeout(400);
        const state = await page.evaluate(() => ({
          text: document.body?.innerText.trim() || '',
          controls: document.querySelectorAll('input,button,canvas,svg,img').length
        }));
        report.pages.push({ path: url.pathname, textLength: state.text.length, controls: state.controls });
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
        await page.screenshot({ path: path.join(config.destination, `page-${index}.png`) });
        fs.writeFileSync(path.join(config.destination, `page-${index}.html`), await page.content());
      } catch (e) {
        report.status = 'unknown';
        report.observations.push({ kind: 'navigation_error', confirmed: false,
          path: url.pathname, message: String(e.message || e) });
      } finally {
        await context.tracing.stop({ path: path.join(config.destination, `trace-${index}.zip`) });
        await context.close();
      }
    }
    if (report.observations.some(e => e.confirmed)) report.status = 'failed';
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
