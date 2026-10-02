import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-2-3: copy exact displayed HTTPS clone value without modifying repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.copyClone(page,"HTTPS"); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});

test("REQ-3-2-3: copy exact displayed SSH clone value without modifying repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.copyClone(page,"SSH"); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
});
