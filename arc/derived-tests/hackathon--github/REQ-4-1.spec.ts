import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-1: visitor directory/file navigation persists exact path content", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.persisted(page, () => expect(h.text(page,'export const search = "search flow";')).toBeVisible()); await expect(page.locator('body')).toContainText('src'); await h.repo(page); await h.link(page,'README.md').click(); await h.persisted(page,()=>expect(h.text(page,'Document search flow').first()).toBeVisible());
});
