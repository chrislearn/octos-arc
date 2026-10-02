import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); await expect(h.text(page,'src/search.ts')).toBeVisible(); await expect(page.getByText(/Changed files/)).toBeVisible(); await expect(page.getByText(/\d+ additions/)).toBeVisible(); await expect(page.getByText(/\d+ deletions/)).toBeVisible();
});

test("REQ-4-2-2: visitor commit diff reads changed file and exact additions/deletions from the parent snapshot", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); const address=page.url(); await page.goto(address); await expect(h.text(page,'src/search.ts').first()).toBeVisible(); await expect(page.getByText(/Changed files/).first()).toBeVisible(); await expect(page.getByText('2 additions, 0 deletions',{exact:false}).first()).toBeVisible();
});
