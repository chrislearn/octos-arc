import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();await h.link(page,'Acme Demo').click(); await h.link(page,'Repositories').click(); await expect(h.link(page,'acme-docs')).toBeVisible();
});

test("REQ-2-1-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalOrganization(page);await h.link(page,'Repositories').click(); await h.field(page,'Find a repository').fill('secret-research'); await expect(h.link(page,'secret-research')).toHaveCount(0);
});

test("REQ-2-1-1: organization live repository filter exposes public result and hides private result", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.organization(page); await h.link(page,'Repositories').click(); await h.field(page,'Find a repository').fill('acme-docs'); await expect(h.link(page,'acme-docs')).toBeVisible();
    await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible(); await page.goBack(); await expect(h.link(page,'acme-docs')).toBeVisible();
    await h.field(page,'Find a repository').fill('secret-research'); await expect(h.link(page,'secret-research')).toHaveCount(0);
});
