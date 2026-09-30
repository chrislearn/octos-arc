import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1-1: grid and formula-bar edits commit on Enter or blur and Escape cancels", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page, 'A1', 'text', true); await h.edit(page, 'B1', 'TRUE'); await h.edit(page, 'C1', '2026-09-30'); await h.edit(page, 'E1', '12.5');
  await h.cell(page, 'A1').dblclick(); await h.field(page, 'Edit A1').fill('cancelled'); await h.field(page, 'Edit A1').press('Escape'); await h.values(page, { A1: 'text' });
  await h.cell(page, 'A1').click(); await h.field(page, 'Formula bar').fill('committed-on-blur'); await h.cell(page, 'D1').click();
  await h.persisted(page, () => h.values(page, { A1: 'committed-on-blur', B1: 'TRUE', C1: '2026-09-30', E1: '12.5' }));
});

test("REQ-3-1-1: formula bar Escape cancels and grid blur commits without changing unrelated cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','original'); await h.cell(page,'A1').click(); await h.field(page,'Formula bar').fill('cancelled'); await h.field(page,'Formula bar').press('Escape');
  await h.ordinary(page,{A1:'original'}); await h.cell(page,'B2').dblclick(); await h.field(page,'Edit B2').fill('grid-blur'); await h.cell(page,'D4').click();
  await h.persisted(page,()=>h.ordinary(page,{A1:'original',B2:'grid-blur',D4:''}));
});
