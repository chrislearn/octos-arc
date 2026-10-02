import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-protection: Admin changes current compare-commit check pending to success and persists setter", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); await h.pr(page,'check-success'); await expect(h.text(page,'test: pending').first()).toBeVisible(); const address=page.url(), visitor=await browser.newContext();
  try { const observed=await visitor.newPage(); await observed.goto(address); await expect(h.text(observed,'test: pending').first()).toBeVisible();
  await h.choose(page,'test','success'); await h.action(page,['Save','Update']).click();
  await h.persisted(page,()=>expect(h.text(page,'test: success').first()).toBeVisible());
  await observed.reload(); await h.persisted(observed,async()=>{ await expect(h.text(observed,'test: success').first()).toBeVisible(); await expect(h.containsValue(observed,'spec-admin').first()).toBeVisible(); });
  } finally { await visitor.close(); }
});
