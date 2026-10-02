import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.persisted(page,async()=>{await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible(); await expect(h.text(page,'Public')).toBeVisible(); await expect(h.link(page,'Code')).toBeVisible();});
});

test("REQ-3-3: visitor public repository overview and Code navigation persist", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await expect(h.text(page,'Public').first()).toBeVisible(); await expect(h.link(page,'Code')).toBeVisible(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible());
});
