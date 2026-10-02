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

test("REQ-3-2-1: overlapping cut preserves the complete target and only clears the uncovered source", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','first\tsecond\tthird'); await h.values(page,{A1:'first',B1:'second',C1:'third'});
  await h.range(page,'A1','B1'); await page.keyboard.press('Control+x'); await h.cell(page,'B1').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,()=>h.values(page,{A1:'',B1:'first',C1:'second'}));
});

test("REQ-3-2-1: external clipboard replacement after cut pastes new text and preserves the cut source", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','original\tneighbor'); await h.values(page,{A1:'original',B1:'neighbor'});
  await h.cell(page,'A1').click(); await page.keyboard.press('Control+x'); await h.paste(page,'C1','external',true);
  await h.persisted(page,()=>h.values(page,{A1:'original',B1:'neighbor',C1:'external'}));
});

test("REQ-3-2-1: copy preserves exact ordinary text in both rectangles after reload", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.paste(page,'A1','  alpha  beta  \t007\n中文  值 \t tail '); await h.edit(page,'F6','outside');
  await h.range(page,'A1','B2'); await page.keyboard.press('Control+c'); await h.cell(page,'C3').click(); await page.keyboard.press('Control+v');
  await h.persisted(page,()=>h.ordinary(page,{A1:'  alpha  beta  ',B1:'007',A2:'中文  值 ',B2:' tail ',C3:'  alpha  beta  ',D3:'007',C4:'中文  值 ',D4:' tail ',F6:'outside'}));
});
