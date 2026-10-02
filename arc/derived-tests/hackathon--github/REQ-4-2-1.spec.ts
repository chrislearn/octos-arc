import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-1: branch commit history displays exact message, author and relative timestamp", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Commits').click(); await expect(h.text(page,'Document search flow').first()).toBeVisible(); await expect(h.text(page,'alice-dev').first()).toBeVisible(); await expect(page.getByText(/\bago\b/).first()).toBeVisible();
});

test("REQ-4-2-1: branch history keeps newest-first order and file history excludes unrelated commits", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const address=await h.repo(page); await h.link(page,'Commits').click();
  const history=await h.historyLinks(page);
  expect(history.indexOf('Document search flow')).toBeLessThan(history.indexOf('Initialize empty repository'));
  await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
  await page.goto(address); await h.link(page,'README.md').click(); await h.link(page,'Commits').click();
  await h.persisted(page,async()=>{
    await expect(h.link(page,'Document search flow')).toBeVisible();
    await expect(h.link(page,'Initialize empty repository')).toHaveCount(0);
  });
});
