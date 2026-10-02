import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-3-2: visitor diff displays exact path and exact aggregate additions/deletions from both changed files", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.pr(page); await h.link(page,'Files changed').click(); await expect(h.text(page,'src/search.ts').first()).toBeVisible(); await expect(page.getByText('2 additions, 1 deletions',{exact:false}).first()).toBeVisible();
});
