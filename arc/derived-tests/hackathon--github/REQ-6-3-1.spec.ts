import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-3-1: visitor PR overview, commits and changed-files navigation survives direct reopen", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.pr(page); const address=page.url(); await h.link(page,'Commits').click(); await expect(page.getByText(/Commit summary/).first()).toBeVisible(); await h.link(page,'Files changed').click(); await expect(page.getByText(/Changed files/).first()).toBeVisible(); await page.goto(address); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.link(page,'Commits')).toBeVisible(); await expect(h.link(page,'Files changed')).toBeVisible(); });
});
