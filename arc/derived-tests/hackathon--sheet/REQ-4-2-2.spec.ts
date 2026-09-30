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
