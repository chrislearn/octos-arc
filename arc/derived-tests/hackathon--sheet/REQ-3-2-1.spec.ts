import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-2-1: plain copy preserves source and cut clears source only after target paste", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','alpha\t1\nbeta\t2'); await h.edit(page,'J10','outside');
  await h.range(page,'A1','B2'); await page.keyboard.press('Control+c'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
  await h.values(page,{A1:'alpha',B1:'1',A2:'beta',B2:'2',C3:'alpha',D3:'1',C4:'beta',D4:'2',J10:'outside'});
  await h.range(page,'A1','B2'); await page.keyboard.press('Control+x'); await h.values(page,{A1:'alpha',B1:'1',A2:'beta',B2:'2'});
  await h.cell(page,'F6').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,()=>h.values(page,{A1:'',B1:'',A2:'',B2:'',C3:'alpha',D3:'1',C4:'beta',D4:'2',F6:'alpha',G6:'1',F7:'beta',G7:'2',J10:'outside'}));
});
