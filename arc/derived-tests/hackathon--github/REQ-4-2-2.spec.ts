import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); await expect(h.text(page,'src/search.ts')).toBeVisible(); await expect(page.getByText(/Changed files/)).toBeVisible(); await expect(page.getByText(/\d+ additions/)).toBeVisible(); await expect(page.getByText(/\d+ deletions/)).toBeVisible();
});

test("REQ-4-2-2: 7aa2e514 compatibility: the public repository chain exposes its named commit before opening the diff", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
  expect(await h.link(page,'Commits').isVisible()).toBe(true); await h.link(page,'Commits').click();
  expect(await h.link(page,'Document search flow').isVisible()).toBe(true);
  await h.link(page,'Document search flow').click(); await expect(h.renderedSubstring(page,'Document search flow').first()).toBeVisible();
  await expect(h.text(page,'src/search.ts').first()).toBeVisible();
});

test("REQ-4-2-2: reference navigation: commit detail retains repository context and returns to code after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page); await h.link(page,'Commits').click();
  await h.link(page,'Document search flow').click(); await page.reload();
  await expect(page.getByRole('heading',{name:'Document search flow',exact:true})).toBeVisible();
  await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(page.getByText(/(?:Commit|Revision)\s+\S+/).first()).toBeVisible();
  await h.link(page,'Code').click(); await expect(h.link(page,'README.md')).toBeVisible();
});

test("REQ-4-2-2: visitor commit diff reads changed file and exact additions/deletions from the parent snapshot", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); const address=page.url(); await page.goto(address); await expect(h.text(page,'src/search.ts').first()).toBeVisible(); await expect(page.getByText(/Changed files/).first()).toBeVisible(); await expect(page.getByText('3 additions, 0 deletions',{exact:false}).first()).toBeVisible();
});
