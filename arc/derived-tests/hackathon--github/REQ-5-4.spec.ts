import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-5-4: Maintain closes and reopens issue preserving title, body and state", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-close'); await h.button(page,'Close issue').click(); await expect(h.text(page,'Closed issue').first()).toBeVisible(); await expect(h.button(page,'Reopen issue')).toBeVisible(); await h.button(page,'Reopen issue').click(); await h.persisted(page, async () => { await expect(h.button(page,'Close issue')).toBeVisible(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.text(page,'Describe the onboarding improvement.').first()).toBeVisible(); });
});

test("REQ-5-4: Read viewer has neither issue status control", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.issue(page,'issue-read'); await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0); await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
});
