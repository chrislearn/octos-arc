import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-1: branch commit history displays exact message, author and relative timestamp", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Commits').click(); await expect(h.text(page,'Document search flow').first()).toBeVisible(); await expect(h.text(page,'alice-dev').first()).toBeVisible(); await expect(page.getByText(/\bago\b/).first()).toBeVisible();
});
