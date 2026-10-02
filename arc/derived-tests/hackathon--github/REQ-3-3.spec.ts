import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.persisted(page,async()=>{await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible(); await expect(h.text(page,'Public')).toBeVisible(); await expect(h.link(page,'Code')).toBeVisible();});
});

test("REQ-3-3: 7aa2e514 compatibility: public organization directory discovers each named stage 2 repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for (const name of ['acme-docs','branch-switch-demo','default-branch-demo','file-management-demo']) {
    await h.home(page); expect(await h.link(page,'Acme Demo').isVisible()).toBe(true);
    await h.link(page,'Acme Demo').click(); expect(await h.link(page,name).isVisible()).toBe(true);
    await h.link(page,name).click(); await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible();
  }
});

test("REQ-3-3: visitor public repository overview and Code navigation persist", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await expect(h.text(page,'Public').first()).toBeVisible(); await expect(h.link(page,'Code')).toBeVisible(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible());
});
