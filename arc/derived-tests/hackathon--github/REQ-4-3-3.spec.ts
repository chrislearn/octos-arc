import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-3-3: Admin changes native default branch and old branch still exists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); const address=await h.repo(page,h.fixtureRepo('default-branch')); await h.settings(page,'Branches'); await h.field(page,'Default branch').selectOption({label:'feature-search'}); await h.button(page,'Update').click(); await h.button(page.getByRole('dialog'),'Confirm').click(); await page.goto(address); await expect(h.button(page,'Branch feature-search')).toBeVisible(); await h.button(page,'Branch feature-search').click(); await expect(page.getByRole('option',{name:'main',exact:true})).toBeVisible();
});

test("REQ-4-3-3: non-Admin default-branch edit controls are absent", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-read'); await h.repo(page,h.fixtureRepo('default-read')); if(await h.link(page,'Settings').count()){ await h.link(page,'Settings').click(); if(await h.link(page,'Branches').count()) await h.link(page,'Branches').click(); } const selector=h.field(page,'Default branch'); if(await selector.isVisible()) await expect(selector).toBeDisabled(); await h.unavailable(page,'Update');
});

test("REQ-4-3-3: guide: required release branch is persisted as default without changing main", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-admin'); const address=await h.repo(page,h.fixtureRepo('guide-default-release'));
  await test.step('Select the existing branch named by the original scenario',async()=>{
    await h.settings(page,'Branches'); await h.field(page,'Default branch').selectOption({label:'release'});
    await h.button(page,'Update').click(); await h.button(page.getByRole('dialog'),'Confirm').click();
  });
  await test.step('A direct reopen uses release and main still retains its bytes',async()=>{
    await page.goto(address); await h.persisted(page,()=>expect(h.button(page,'Branch release')).toBeVisible());
    await h.button(page,'Branch release').click(); await h.option(page,'main');
    await h.link(page,'src').click(); await h.link(page,'search.ts').click();
    await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
  });
});
