import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-4: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"visibility-admin"); const address=await h.repo(page,'visibility-demo'); await h.settings(page,'General'); await h.button(page,'Change visibility').click(); await page.getByRole('radio',{name:'Public',exact:true}).check(); await h.button(page,'Confirm visibility').click(); await expect(h.text(page,'Public')).toBeVisible(); const other=await browser.newContext({baseURL:new URL(page.url()).origin}); try {const p=await other.newPage(); await p.goto(address); await expect(p.getByRole('heading').filter({hasText:'visibility-demo'})).toBeVisible();} finally {await other.close();}
});

test("REQ-3-4: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"collaborator"); await h.repo(page,'visibility-demo'); await h.settings(page,'General'); await h.unavailable(page,'Change visibility');
});

test("REQ-3-4: 7aa2e514 compatibility: authorized accounts discover the visibility repository through the organization entry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for (const account of ['visibility-admin','collaborator']) {
    await h.signIn(page,account); await h.link(page,'Acme Demo').click();
    expect(await h.link(page,'visibility-demo').isVisible()).toBe(true);
    await h.link(page,'visibility-demo').click(); await expect(page.getByRole('heading').filter({hasText:'visibility-demo'})).toBeVisible();
    await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
  }
});

test("REQ-3-4: Admin makes Private repository Public and fresh visitor reads saved identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'repo-admin'); const address=await h.repo(page,h.fixtureRepo('visibility')); await expect(h.text(page,'Private').first()).toBeVisible(); await h.settings(page,'General'); await h.button(page,'Change visibility').click(); await page.getByRole('radio',{name:'Public',exact:true}).check(); await h.button(page,'Confirm visibility').click(); await expect(h.text(page,'Public').first()).toBeVisible();
    const visitor=await browser.newContext(); const p=await visitor.newPage(); await p.goto(address); await expect(p.getByRole('heading').filter({hasText:h.fixtureRepo('visibility')})).toBeVisible(); await expect(h.text(p,'Public').first()).toBeVisible(); await visitor.close();
});

test("REQ-3-4: non-Admin cannot activate visibility change", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.repo(page,h.fixtureRepo('visibility-read')); if(await h.link(page,'Settings').count()) { await h.link(page,'Settings').click(); if(await h.link(page,'General').count()) await h.link(page,'General').click(); } await h.unavailable(page,'Change visibility');
});
