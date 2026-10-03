import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click(); await expect(h.renderedSubstring(page,'search flow').first()).toBeVisible();
});

test("REQ-4-2-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-token'); await search.press('Enter'); await h.link(page,'Code').click(); await expect(page.getByText(/No code results/)).toBeVisible(); await expect(search).toHaveValue('no-such-token');
});

test("REQ-4-2-3: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click(); await expect(h.renderedSubstring(page,'search flow').first()).toBeVisible(); await page.reload(); await expect(h.renderedSubstring(page,'search flow').first()).toBeVisible(); await expect(h.link(page,'README.md')).toBeVisible();
});

test("REQ-4-2-3: requirement scenario 4", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);const address=page.url(); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-token'); await search.press('Enter'); await h.link(page,'Code').click(); await expect(page.getByText(/No code results/)).toBeVisible(); await expect(search).toHaveValue('no-such-token'); await page.goto(address); await search.fill('no-such-token'); await search.press('Enter'); await h.link(page,'Code').click(); await expect(page.getByText(/No code results/)).toBeVisible();
});

test("REQ-4-2-3: stage2 feedback: a search match remains visible with its full file after reload and filename navigation", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'README.md').click(); const content=await page.locator('pre').textContent();
  await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true});
  await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click();
  const address=page.url();
  for(let i=0;i<3;i++) {
    await expect(h.text(page,'search flow')).toBeVisible(); expect(await page.locator('pre').textContent()).toBe(content);
    if(i===0) await page.reload(); else if(i===1) await h.link(page,'README.md').click();
  }
  await page.goto(address); await expect(h.text(page,'search flow')).toBeVisible();
});

test("REQ-4-2-3: repository code result opens matching file with persisted code context", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click(); await h.persisted(page, () => expect(h.text(page,'Document search flow').first()).toBeVisible()); await expect(h.link(page,'README.md')).toBeVisible();
});

test("REQ-4-2-3: no code matches retain exact query across repeated searches", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for(let i=0;i<2;i++){ await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-token'); await search.press('Enter'); await h.link(page,'Code').click(); await expect(h.text(page,'No code results').first()).toBeVisible(); await expect(search).toHaveValue('no-such-token'); await expect(h.link(page,'README.md')).toHaveCount(0); }
});
