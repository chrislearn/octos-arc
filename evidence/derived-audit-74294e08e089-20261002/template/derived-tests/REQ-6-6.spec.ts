import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-6: author closes and reopens PR while discussion and branches persist", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.pr(page,'pr-close'); await h.button(page,'Close pull request').click(); await expect(h.button(page,'Reopen pull request')).toBeVisible(); await h.button(page,'Reopen pull request').click(); await h.persisted(page, async () => { await expect(h.button(page,'Close pull request')).toBeVisible(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.link(page,'Files changed')).toBeVisible(); });
});

test("REQ-6-6: Read viewer has no close or reopen action", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.pr(page,'pr-close-read'); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
});
