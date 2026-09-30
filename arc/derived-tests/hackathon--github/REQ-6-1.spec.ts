import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-1: Admin stores exact branch protection toggles and reload displays summaries", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('protection-create')); await h.settings(page,'Branches'); await h.button(page,'Add branch protection rule').click(); await h.field(page,'Branch name pattern').fill('main'); await page.getByRole('checkbox',{name:'Require 1 approval',exact:true}).check(); await page.getByRole('checkbox',{name:'Require status check test',exact:true}).check(); await h.button(page,'Create').click(); await h.persisted(page, async () => { await expect(h.visibleText(page,'main').first()).toBeVisible(); await expect(h.visibleText(page,'1 approval').first()).toBeVisible(); await expect(h.visibleText(page,'Require status check test').first()).toBeVisible(); });
});

test("REQ-6-1: non-Admin cannot create protection rule", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.repo(page,h.fixtureRepo('protection-read')); if(await h.link(page,'Settings').count()){ await h.link(page,'Settings').click(); if(await h.link(page,'Branches').count()) await h.link(page,'Branches').click(); } await expect(h.button(page,'Add branch protection rule')).toHaveCount(0);
});
