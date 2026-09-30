import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-1-2-1: create opens exactly one blank Sheet1 with A1 selected and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const address = await h.blank(page); await expect(page.getByRole('tab')).toHaveCount(1);
  await page.reload(); await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true');
  await expect(h.cell(page, 'A1')).toHaveAttribute('aria-selected', 'true'); await h.values(page, { A1: '' });
  await page.goto('/'); await page.goto(address); await expect(page.getByRole('tab')).toHaveCount(1); await h.values(page, { A1: '' });
});

test("REQ-1-2-1: new workbook has no imported values, filter, validation or pivot from another workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); const original=page.url(); await h.validation(page,'B2','B4'); await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.pivot(page);
  await h.blank(page); await expect(page.getByRole('tab')).toHaveCount(1); await expect(h.grid(page)).toHaveAttribute('aria-multiselectable','true'); await h.selection(page,['A1'],['B1','A2','B2']);
  await h.values(page,{A1:'',B2:'',C4:''}); await expect(h.button(page,'Filter Region')).toHaveCount(0); await expect(h.button(page,'Open dropdown for B2')).toHaveCount(0); await expect(h.button(page,'Refresh pivot table')).toHaveCount(0);
  await h.edit(page,'B2','101'); await h.persisted(page,()=>h.values(page,{B2:'101'})); await page.goto(original); await expect(h.tab(page,'Pivot1')).toBeVisible(); await h.tab(page,'Sheet1').click(); await h.values(page,{B2:'10'});
});
