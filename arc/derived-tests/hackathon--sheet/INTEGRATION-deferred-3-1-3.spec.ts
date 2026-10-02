import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-3-1-3: complete rectangle replaces and persists exact selected ARIA cells independently per sheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.range(page, 'B2', 'C3');
  const check = async () => h.selection(page,['B2','C2','B3','C3'],['A1','A2','B1','D3']);
  await check(); await h.button(page, 'Add worksheet').click(); await h.cell(page,'D4').click(); await h.tab(page,'Sheet1').click(); await h.persisted(page, check);
  await h.cell(page,'A1').click(); await expect(h.cell(page,'B2')).toHaveAttribute('aria-selected','false');
});

test("INTEGRATION-deferred-3-1-3: reverse-direction drag replaces a saved rectangle and sorting uses only that rectangle", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','outside-a\toutside-b\toutside-c\toutside-d\noutside-e\tRegion\tSales\toutside-f\noutside-g\tEast\t20\toutside-h\noutside-i\tNorth\t10\toutside-j');
  await h.range(page,'C4','B2'); await h.selection(page,['B2','C2','B3','C3','B4','C4'],['A1','A2','A3','A4','B1','C1','D2','D3','D4']);
  await h.data(page,'Sort range'); const dialog=page.getByRole('dialog',{name:'Sort range',exact:true}); await dialog.getByRole('checkbox',{name:'Data has header row',exact:true}).check();
  await h.choose(dialog,'Sort by','Sales'); await h.choose(dialog,'Order','Ascending'); await h.button(dialog,'Sort').click();
  await h.persisted(page,()=>h.values(page,{B2:'Region',C2:'Sales',B3:'North',C3:'10',B4:'East',C4:'20',A1:'outside-a',B1:'outside-b',C1:'outside-c',D1:'outside-d',A2:'outside-e',D2:'outside-f',A3:'outside-g',D3:'outside-h',A4:'outside-i',D4:'outside-j'}));
  await h.range(page,'D5','E6'); await h.persisted(page,()=>h.selection(page,['D5','E5','D6','E6'],['B2','C2','B3','C3','C5','F6']));
});
