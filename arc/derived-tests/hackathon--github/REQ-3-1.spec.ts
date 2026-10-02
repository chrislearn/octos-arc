import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill("acme-docs"); await search.press('Enter'); await expect(h.link(page,'acme-docs')).toHaveCount(1); await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-3-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill("secret-research"); await search.press('Enter'); await expect(h.text(page,'No results')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
});

test("REQ-3-1: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill("no-such-repository"); await search.press('Enter'); await expect(page.getByText(/No results|No repositories/)).toBeVisible();
});

test("REQ-3-1: requirement scenario 4", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill("acme-docs"); await search.press('Enter'); await expect(h.link(page,'acme-docs')).toHaveCount(1); await h.link(page,'acme-docs').click(); await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible());
});

test("REQ-3-1: global search opens public identity and excludes private repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible()); await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('secret-research'); await search.press('Enter'); await expect(h.link(page,'secret-research')).toHaveCount(0);
});

test("REQ-3-1: empty repository search is repeatable without stale results", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for(let i=0;i<2;i++){ await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-repository'); await search.press('Enter'); await expect(h.text(page,'No results').first()).toBeVisible(); await expect(h.link(page,'acme-docs')).toHaveCount(0); }
});

test("REQ-3-1: guide: public scenario prerequisites are searchable before downstream operations", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner');
    const repos=['regression-team-members','regression-file-create','regression-file-history','regression-issue-create','regression-pr-ready','regression-review-request'];
    for(const name of repos) await test.step(`Prerequisite repository ${name} exists with its owner`,async()=>{
      await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true});
      await search.fill(name); await search.press('Enter');
      const entry=h.link(page,name); await expect(entry).toBeVisible();
      const owner='regression-org-'+name.slice('regression-'.length);
      const row=entry.locator(`xpath=ancestor::*[contains(.,"${owner}")][1]`);
      await expect(row).toContainText(owner);
    });
});
