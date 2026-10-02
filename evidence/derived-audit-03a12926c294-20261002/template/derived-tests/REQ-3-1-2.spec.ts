import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-1-2: plain paste clears middle and trailing empty fields and preserves outside cells", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'C2','replace'); await h.edit(page,'D3','tail'); await h.edit(page,'E5','outside');
  await h.paste(page,'B2','East\t\t1200\nNorth\t800\t');
  await h.persisted(page,()=>h.values(page,{B2:'East',C2:'',D2:'1200',B3:'North',C3:'800',D3:'',E5:'outside'}));
});

test("REQ-3-1-2: context REQ-2-2-1: row insert/delete moves complete records and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.structure(page, "row", "2", "Insert 1 row above");
  await h.persisted(page, () => h.values(page, {"A2": "", "B2": "", "C2": "", "A3": "East", "B3": "10", "C3": "Open", "A4": "North", "B4": "20", "C4": "Closed", "A5": "East", "B5": "30", "C5": "Closed"}));
  await h.structure(page, "row", "2", "Delete row");
  await h.persisted(page, () => h.values(page, {"A1": "Region", "B1": "Sales", "C1": "Status", "A2": "East", "B2": "10", "C2": "Open", "A3": "North", "B3": "20", "C3": "Closed", "A4": "East", "B4": "30", "C4": "Closed"}));
});

test("REQ-3-1-2: context REQ-2-2-1: insert below a populated anchor keeps the anchor row", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);
  await test.step('Populate the anchor and the following complete record',async()=>{
    await h.paste(page,'A1','anchor\t10\nnext\t20');
    await h.values(page,{A1:'anchor',B1:'10',A2:'next',B2:'20'});
  });
  await h.structure(page,'row','1','Insert 1 row below');
  await test.step('The blank row follows the unchanged anchor, including after reload',async()=>{
    await h.persisted(page,()=>h.values(page,{A1:'anchor',B1:'10',A2:'',B2:'',A3:'next',B3:'20'}));
  });
});

test("REQ-3-1-2: context REQ-2-2-2: column insert/delete moves complete records and persists", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.sourceData(page); await h.structure(page, "column", "B", "Insert 1 column left");
  await h.persisted(page, () => h.values(page, {"A1": "Region", "B1": "", "B2": "", "C1": "Sales", "C2": "10", "D1": "Status", "D2": "Open", "C3": "20", "D3": "Closed", "C4": "30", "D4": "Closed"}));
  await h.structure(page, "column", "B", "Delete column");
  await h.persisted(page, () => h.values(page, {"A1": "Region", "B1": "Sales", "C1": "Status", "A2": "East", "B2": "10", "C2": "Open", "A3": "North", "B3": "20", "C3": "Closed", "A4": "East", "B4": "30", "C4": "Closed"}));
});

test("REQ-3-1-2: context REQ-2-2-2: insert right of a populated anchor keeps the anchor column", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);
  await test.step('Populate the anchor and the following complete column',async()=>{
    await h.paste(page,'A1','anchor\tnext\noutside-anchor\toutside-next');
    await h.values(page,{A1:'anchor',B1:'next',A2:'outside-anchor',B2:'outside-next'});
  });
  await h.structure(page,'column','A','Insert 1 column right');
  await test.step('The blank column follows the unchanged anchor, including after reload',async()=>{
    await h.persisted(page,()=>h.values(page,{A1:'anchor',B1:'',C1:'next',A2:'outside-anchor',B2:'',C2:'outside-next'}));
  });
});
