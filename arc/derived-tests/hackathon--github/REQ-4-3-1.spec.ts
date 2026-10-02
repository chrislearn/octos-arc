import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-3-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page,'branch-switch-demo'); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('feature-search'); await h.option(page,'feature-search'); await expect(h.button(page,'Branch feature-search')).toBeVisible(); await expect(h.link(page,'main-only.md')).toBeVisible();
});

test("REQ-4-3-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page,'branch-switch-demo'); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('missing-branch'); await expect(page.getByRole('option')).toHaveCount(0); await page.keyboard.press('Escape'); await h.persisted(page,()=>expect(h.button(page,'Branch main')).toBeVisible());
});

test("REQ-4-3-1: branch live selector switches file snapshot and persists current page branch", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('feature-search'); await h.option(page,'feature-search'); await h.persisted(page, async () => { await expect(h.button(page,'Branch feature-search')).toBeVisible(); await expect(h.link(page,'main-only.md')).toBeVisible(); });
});

test("REQ-4-3-1: unknown branch leaves original branch intact after Escape and refresh", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('unknown-branch'); await expect(h.text(page,'No matching branch').first()).toBeVisible(); await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
});
