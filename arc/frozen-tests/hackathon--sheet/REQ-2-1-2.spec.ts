import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-2-1-2: switch restores each sheet formula and selected cell and last active sheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'B2', '=2+3'); await h.cell(page, 'B2').click();
  await h.button(page, 'Add worksheet').click(); await h.edit(page, 'C3', 'other'); await h.cell(page, 'C3').click();
  await h.tab(page, 'Sheet1').click(); await expect(h.cell(page, 'B2')).toHaveAttribute('aria-selected', 'true'); await h.formula(page, 'B2', '=2+3', '5');
  await h.tab(page, 'Sheet2').click(); await h.persisted(page, async () => { await expect(h.tab(page, 'Sheet2')).toHaveAttribute('aria-selected', 'true'); await expect(h.cell(page, 'C3')).toHaveAttribute('aria-selected', 'true'); await expect(h.field(page, 'Formula bar')).toHaveValue('other'); });
  await h.tab(page, 'Sheet1').click(); await h.values(page, { B2: '5', C3: '' });
});
