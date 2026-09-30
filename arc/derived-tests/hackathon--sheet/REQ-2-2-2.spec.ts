import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-2: seeded column insertion and deletion move complete records without editing prerequisites", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await page.getByRole('link',{name:'Column operations seed',exact:true}).click();
  await h.values(page,{A1:'first',A2:'alpha',B1:'second',B2:'beta',C1:'third',C2:'gamma'});
  await h.structure(page,'column','B','Insert 1 column left');
  await h.persisted(page,()=>h.values(page,{A1:'first',A2:'alpha',B1:'',B2:'',C1:'second',C2:'beta',D1:'third',D2:'gamma'}));
  await h.structure(page,'column','C','Delete column');
  await h.persisted(page,()=>h.values(page,{A1:'first',A2:'alpha',B1:'',B2:'',C1:'third',C2:'gamma',D1:'',D2:''}));
});
