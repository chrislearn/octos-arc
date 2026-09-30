import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-1-3-2: CSV downloads actual values with escaping and leaves active state intact", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  await h.field(dialog,'CSV file').setInputFiles({name:`${h.unique()}.csv`,mimeType:'text/csv',buffer:Buffer.from('"中文,comma",,"quote""line\nnext"\n5,,10')}); await h.button(dialog,'Confirm import').click();
  await h.edit(page, 'A2', '5'); await h.edit(page, 'C2', '=A2*2');
  await h.formula(page, 'C2', '=A2*2', '10');
  expect(h.parseCSV(await h.csv(page))).toEqual([['中文,comma', '', 'quote"line\nnext'], ['5', '', '10']]);
  await expect(h.tab(page, 'Sheet1')).toHaveAttribute('aria-selected', 'true'); await expect(h.field(page, 'Formula bar')).toHaveValue('=A2*2');
  await h.persisted(page, () => h.formula(page, 'C2', '=A2*2', '10'));
});

test("INTEGRATION-deferred-1-3-2: export reads only active worksheet and preserves selection and original formulas", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.button(page,'Add worksheet').click(); await h.paste(page,'A1','Label\tValue\nOnly-second\t7'); await h.edit(page,'C2','=B2*3'); await h.cell(page,'C2').click();
  expect(h.parseCSV(await h.csv(page))).toEqual([['Label','Value',''],['Only-second','7','21']]);
  await expect(h.tab(page,'Sheet2')).toHaveAttribute('aria-selected','true'); await h.selection(page,['C2'],['A1','B2']); await expect(h.field(page,'Formula bar')).toHaveValue('=B2*3');
  await h.persisted(page,()=>h.formula(page,'C2','=B2*3','21')); await h.tab(page,'Sheet1').click(); expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status'],['East','10','Open'],['North','20','Closed'],['East','30','Closed']]);
});
