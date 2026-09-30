import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-5-3-1: pivot naming reuses the first unused PivotN after a result sheet is deleted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.pivot(page); await h.tab(page,'Sheet1').click(); await h.pivot(page,'COUNT'); await expect(h.tab(page,'Pivot2')).toHaveAttribute('aria-selected','true');
  await h.sheetMenu(page,'Pivot1','Delete'); await h.button(page.getByRole('dialog',{name:'Delete worksheet',exact:true}),'Delete worksheet').click(); await h.tab(page,'Sheet1').click(); await h.pivot(page,'AVERAGE');
  await h.persisted(page,async()=>{await h.tabOrder(page,['Sheet1','Pivot2','Pivot1']);await expect(h.tab(page,'Pivot1')).toHaveAttribute('aria-selected','true');await h.values(page,{B1:'AVERAGE of Sales',B2:'20',B3:'20',B4:'20'});});
  await h.tab(page,'Pivot2').click(); await h.values(page,{B1:'COUNT of Sales',B2:'2',B3:'1',B4:'3'});
});
