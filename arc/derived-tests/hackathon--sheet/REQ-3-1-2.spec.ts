import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1-2: plain paste clears middle and trailing empty fields and preserves outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'C2','replace'); await h.edit(page,'D3','tail'); await h.edit(page,'E5','outside');
  await h.paste(page,'B2','East\t\t1200\nNorth\t800\t');
  await h.persisted(page,()=>h.values(page,{B2:'East',C2:'',D2:'1200',B3:'North',C3:'800',D3:'',E5:'outside'}));
});
