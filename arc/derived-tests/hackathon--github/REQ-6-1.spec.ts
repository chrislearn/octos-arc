import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"protection-admin"); await h.repo(page,'branch-protection-demo'); await h.settings(page,'Branches'); await h.button(page,'Add branch protection rule').click(); await h.field(page,'Branch name pattern').fill('main'); await page.getByRole('checkbox',{name:'Require 1 approval',exact:true}).check(); await page.getByRole('checkbox',{name:'Require status check test',exact:true}).check(); await h.action(page,['Create','Save changes']).click(); await h.persisted(page,async()=>{await expect(h.visibleText(page,'main').first()).toBeVisible(); await expect(h.visibleText(page,'1 approval').first()).toBeVisible(); await expect(h.visibleText(page,'Require status check test').first()).toBeVisible();});
});

test("REQ-6-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"protection-viewer"); await h.repo(page,'branch-protection-demo'); await h.settings(page,'Branches'); await expect(h.button(page,'Add branch protection rule')).toHaveCount(0);
});

test("REQ-6-1: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"protection-admin"); await h.scenarioPr(page,"Protection status onboarding PR","branch-protection-demo"); await expect(h.text(page,'test: pending')).toBeVisible(); await h.choose(page,'test','success'); await h.action(page,['Save','Update']).click(); await h.persisted(page,async()=>{await expect(h.text(page,'test: success')).toBeVisible(); await expect(h.containsValue(page,'protection-admin').first()).toBeVisible();});
});

test("REQ-6-1: home workspace: a created protection rule has an unambiguous branch summary after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'repo-owner'); await h.link(page,'New repository').click();
  await h.field(page,'Repository name').fill(h.unique('protection-context'));
  await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check(); await h.button(page,'Create repository').click();
  await h.settings(page,'Branches'); await h.chosen(page,'Default branch','main');
  await h.button(page,'Add branch protection rule').click(); await h.field(page,'Branch name pattern').fill('main');
  await page.getByRole('checkbox',{name:'Require 1 approval',exact:true}).check();
  await page.getByRole('checkbox',{name:'Require status check test',exact:true}).check(); await h.action(page,['Create','Save changes']).click();
  await expect(page.getByText('main',{exact:true})).toBeVisible(); await page.reload();
  await expect(page.getByText('main',{exact:true})).toBeVisible(); await expect(h.text(page,'1 approval')).toBeVisible();
  await h.link(page,'Branches').click(); await h.chosen(page,'Default branch','main');
});

test("REQ-6-1: Admin stores exact branch protection toggles and reload displays summaries", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'repo-admin'); await h.repo(page,h.fixtureRepo('protection-create')); await h.settings(page,'Branches'); await h.button(page,'Add branch protection rule').click(); await h.field(page,'Branch name pattern').fill('main'); await page.getByRole('checkbox',{name:'Require 1 approval',exact:true}).check(); await page.getByRole('checkbox',{name:'Require status check test',exact:true}).check(); await h.action(page,['Create','Save changes']).click(); await h.persisted(page, async () => { await expect(h.visibleText(page,'main').first()).toBeVisible(); await expect(h.visibleText(page,'1 approval').first()).toBeVisible(); await expect(h.visibleText(page,'Require status check test').first()).toBeVisible(); });
});

test("REQ-6-1: non-Admin cannot create protection rule", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'issue-viewer'); await h.repo(page,h.fixtureRepo('protection-read')); if(await h.link(page,'Settings').count()){ await h.link(page,'Settings').click(); if(await h.link(page,'Branches').count()) await h.link(page,'Branches').click(); } await expect(h.button(page,'Add branch protection rule')).toHaveCount(0);
});
