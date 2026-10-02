import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'src').click(); await h.link(page,'README.md').click(); await h.persisted(page,()=>expect(h.text(page,'Document search flow')).toBeVisible());
});

test("REQ-4-1: reference navigation: file pages retain repository tabs and one file-specific Commits entry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page); await h.link(page,'README.md').click();
  await expect(h.link(page,'Issues')).toBeVisible(); await expect(h.link(page,'Commits')).toHaveCount(1);
  await h.link(page,'Commits').click(); await expect(h.link(page,'Document search flow')).toBeVisible();
  await h.link(page,'Code').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-4-1: visitor directory/file navigation persists exact path content", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.persisted(page, () => expect(h.text(page,'export const search = "search flow";')).toBeVisible()); await expect(page.locator('body')).toContainText('src'); await h.repo(page); await h.link(page,'README.md').click(); await h.persisted(page,()=>expect(h.text(page,'Document search flow').first()).toBeVisible());
});
