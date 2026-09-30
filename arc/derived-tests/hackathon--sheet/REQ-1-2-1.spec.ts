import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-2-1: create opens exactly one blank Sheet1 with A1 selected and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const address = await h.blank(page); await expect(page.getByRole('tab')).toHaveCount(1);
  await page.reload(); await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true');
  await expect(h.cell(page, 'A1')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' });
  await page.goto('/'); await page.goto(address); await expect(page.getByRole('tab')).toHaveCount(1); await h.values(page, { A1: '' });
});
