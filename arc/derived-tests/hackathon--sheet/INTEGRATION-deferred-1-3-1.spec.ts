import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-1-3-1: import treats first row as data and strips only the final csv extension from the file name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); const name=`${h.unique()}.part`; await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from('Region,Sales,Status\nEast,1200,Open\nNorth,800,Closed')}); await h.button(dialog,'Confirm import').click();
  await expect(h.tab(page,'Sheet1')).toHaveAttribute('aria-selected','true'); await expect(page.getByRole('tab')).toHaveCount(1); const address=page.url();
  await h.ordinary(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'1200',C2:'Open',A3:'North',B3:'800',C3:'Closed'}); await h.edit(page,'A1','ordinary-first-row');
  await page.goto('/'); await page.reload(); await expect(page.getByRole('link',{name,exact:true})).toBeVisible(); await page.goto(address); await h.values(page,{A1:'ordinary-first-row',A2:'East',A3:'North'});
});
