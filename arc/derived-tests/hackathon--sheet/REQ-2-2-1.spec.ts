import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-1: seeded row insertion and deletion move complete records without editing prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await page.getByRole('link',{name:'Row operations seed',exact:true}).click();
  await h.values(page,{A1:'Label',B1:'Value',A2:'first',B2:'10',A3:'second',B3:'20'});
  await h.structure(page,'row','2','Insert 1 row above');
  await h.persisted(page,()=>h.values(page,{A1:'Label',B1:'Value',A2:'',B2:'',A3:'first',B3:'10',A4:'second',B4:'20'}));
  await h.structure(page,'row','3','Delete row');
  await h.persisted(page,()=>h.values(page,{A1:'Label',B1:'Value',A2:'',B2:'',A3:'second',B3:'20',A4:'',B4:''}));
});
