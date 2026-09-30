import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-3-3: Admin changes native default branch and old branch still exists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); const address=await h.repo(page,h.fixtureRepo('default-branch')); await h.settings(page,'Branches'); await h.field(page,'Default branch').selectOption({label:'feature-search'}); await h.button(page,'Update').click(); await h.button(page.getByRole('dialog'),'Confirm').click(); await page.goto(address); await expect(h.button(page,'Branch feature-search')).toBeVisible(); await h.button(page,'Branch feature-search').click(); await expect(page.getByRole('option',{name:'main',exact:true})).toBeVisible();
});

test("REQ-4-3-3: non-Admin default-branch edit controls are absent", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.repo(page,h.fixtureRepo('default-read')); if(await h.link(page,'Settings').count()){ await h.link(page,'Settings').click(); if(await h.link(page,'Branches').count()) await h.link(page,'Branches').click(); } await expect(h.field(page,'Default branch')).toHaveCount(0); await expect(h.button(page,'Update')).toHaveCount(0);
});
