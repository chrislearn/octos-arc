import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-1-1: append blank worksheets in order and activate each new A1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);
  for(const name of ['Sheet2','Sheet3']) { await h.button(page,'Add worksheet').click(); await expect(h.tab(page,name)).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); await expect(h.cell(page,'A1')).toHaveAttribute('aria-selected','true'); }
  await h.persisted(page,async()=>{ await h.tabOrder(page,['Sheet1','Sheet2','Sheet3']); await expect(h.tab(page,'Sheet3')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:''}); });
});
