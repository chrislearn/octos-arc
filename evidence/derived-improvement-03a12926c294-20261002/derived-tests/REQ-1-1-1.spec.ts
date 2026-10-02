import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-1-1: home entry, saved address and later browser session identify the same workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); const entry = page.getByRole('link', { name: 'Q3 Sales', exact: true });
  await expect(entry).toBeVisible(); await entry.click(); const address = page.url();
  await h.values(page, { A1: 'Region' }); await expect(h.tab(page, 'Sheet1')).toBeVisible();
  await h.persisted(page, () => h.values(page, { A1: 'Region' }));
  const later = await browser.newContext();
  try { const other = await later.newPage(); await other.goto(address); await h.values(other, { A1: 'Region' }); }
  finally { await later.close(); }
});
