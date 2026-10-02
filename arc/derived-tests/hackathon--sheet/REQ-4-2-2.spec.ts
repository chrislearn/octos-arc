import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-2: =1/0 persists error, isolates other cells, then recovers", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=1/0");
  await h.persisted(page, () => h.formula(page,'B1',"=1/0","#DIV/0!")); await h.values(page,{A1:'6'});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page, () => h.formula(page,'B1','=A1+1','7'));
});

test("REQ-4-2-2: =#REF! persists error, isolates other cells, then recovers", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=#REF!");
  await h.persisted(page, () => h.formula(page,'B1',"=#REF!","#REF!")); await h.values(page,{A1:'6'});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page, () => h.formula(page,'B1','=A1+1','7'));
});

test("REQ-4-2-2: =UNKNOWN(A1) persists error, isolates other cells, then recovers", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=UNKNOWN(A1)");
  await h.persisted(page, () => h.formula(page,'B1',"=UNKNOWN(A1)","#NAME?")); await h.values(page,{A1:'6'});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page, () => h.formula(page,'B1','=A1+1','7'));
});

test("REQ-4-2-2: =1+ persists error, isolates other cells, then recovers", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=1+");
  await h.persisted(page, () => h.formula(page,'B1',"=1+","#ERROR!")); await h.values(page,{A1:'6'});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page, () => h.formula(page,'B1','=A1+1','7'));
});

test("REQ-4-2-2: =B1 persists error, isolates other cells, then recovers", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=B1");
  await h.persisted(page, () => h.formula(page,'B1',"=B1","#REF!")); await h.values(page,{A1:'6'});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page, () => h.formula(page,'B1','=A1+1','7'));
});

test("REQ-4-2-2: indirect cycle reports stable reference error and recovers dependencies", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','=B1'); await h.edit(page,'B1','=A1'); await h.persisted(page, () => h.values(page,{A1:'#REF!',B1:'#REF!'}));
  await h.edit(page,'B1','4'); await h.persisted(page, () => h.formula(page,'A1','=B1','4'));
});

test("REQ-4-2-2: a malformed formula does not block unrelated recalculation and fixing it recovers dependents", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','2'); await h.edit(page,'B1','=1+'); await h.edit(page,'C1','=A1*3'); await h.edit(page,'D1','=B1+1');
  await h.edit(page,'A1','4'); await h.formula(page,'B1','=1+','#ERROR!'); await h.formula(page,'C1','=A1*3','12'); await h.edit(page,'B1','=A1+2');
  await h.persisted(page,async()=>{await h.formula(page,'B1','=A1+2','6');await h.formula(page,'C1','=A1*3','12');await h.formula(page,'D1','=B1+1','7');});
});

test("REQ-4-2-2: aggregate formula keeps a stable source error and recalculates after repair", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','=1/0'); await h.edit(page,'A2','5'); await h.edit(page,'B1','=SUM(A1:A2)');
  await h.persisted(page,()=>h.formula(page,'B1','=SUM(A1:A2)','#DIV/0!'));
  await h.edit(page,'A1','15'); await h.persisted(page,()=>h.formula(page,'B1','=SUM(A1:A2)','20'));
});

test("REQ-4-2-2: a dependent formula preserves a malformed source error and recovers", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page);
  await h.edit(page,'A1','=1+'); await h.edit(page,'B1','=A1+1');
  await test.step('The source and its dependent preserve the malformed-expression error',async()=>{
    await h.persisted(page,()=>h.values(page,{A1:'#ERROR!',B1:'#ERROR!'}));
  });
  await h.edit(page,'A1','4');
  await test.step('Repairing the source recalculates and persists the dependent',async()=>{
    await h.persisted(page,()=>h.values(page,{A1:'4',B1:'5'}));
  });
});

test("REQ-4-2-2: audit regression: =A0 displays a stable #REF! and repairing it restores dependents", async ({ page }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=A0"); await h.edit(page,'C1','=B1+1');
  await h.persisted(page,async()=>{await h.formula(page,'B1',"=A0","#REF!");await h.values(page,{A1:'6',C1:"#REF!"});});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page,()=>h.values(page,{A1:'6',B1:'7',C1:'8'}));
});

test("REQ-4-2-2: audit regression: =SUM(A0:A2) displays a stable #REF! and repairing it restores dependents", async ({ page }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=SUM(A0:A2)"); await h.edit(page,'C1','=B1+1');
  await h.persisted(page,async()=>{await h.formula(page,'B1',"=SUM(A0:A2)","#REF!");await h.values(page,{A1:'6',C1:"#REF!"});});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page,()=>h.values(page,{A1:'6',B1:'7',C1:'8'}));
});

test("REQ-4-2-2: audit regression: =1.2.3 displays a stable #ERROR! and repairing it restores dependents", async ({ page }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=1.2.3"); await h.edit(page,'C1','=B1+1');
  await h.persisted(page,async()=>{await h.formula(page,'B1',"=1.2.3","#ERROR!");await h.values(page,{A1:'6',C1:"#ERROR!"});});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page,()=>h.values(page,{A1:'6',B1:'7',C1:'8'}));
});

test("REQ-4-2-2: audit regression: =. displays a stable #ERROR! and repairing it restores dependents", async ({ page }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','6'); await h.edit(page,'B1',"=."); await h.edit(page,'C1','=B1+1');
  await h.persisted(page,async()=>{await h.formula(page,'B1',"=.","#ERROR!");await h.values(page,{A1:'6',C1:"#ERROR!"});});
  await h.edit(page,'B1','=A1+1'); await h.persisted(page,()=>h.values(page,{A1:'6',B1:'7',C1:'8'}));
});
