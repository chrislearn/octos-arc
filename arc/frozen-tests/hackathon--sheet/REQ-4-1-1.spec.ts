import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-4-1-1: formula =(2+3)*4-6/2 uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=(2+3)*4-6/2");
  await h.persisted(page, () => h.formula(page,'B1',"=(2+3)*4-6/2","17"));
});

test("REQ-4-1-1: formula =sUm(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=sUm(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=sUm(A1:A4)","30"));
});

test("REQ-4-1-1: formula =AVERAGE(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=AVERAGE(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=AVERAGE(A1:A4)","15"));
});

test("REQ-4-1-1: formula =COUNT(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=COUNT(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=COUNT(A1:A4)","2"));
});

test("REQ-4-1-1: formula =MIN(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=MIN(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=MIN(A1:A4)","10"));
});

test("REQ-4-1-1: formula =MAX(A1:A4) uses numeric cells and ignores blanks/text", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','10'); await h.edit(page,'A2','20'); await h.edit(page,'A4','text'); await h.edit(page,'B1',"=MAX(A1:A4)");
  await h.persisted(page, () => h.formula(page,'B1',"=MAX(A1:A4)","20"));
});

test("REQ-4-1-1: MAX ignores blank cells rather than using zero when every numeric input is negative", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.edit(page,'A1','-20'); await h.edit(page,'A3','-10'); await h.edit(page,'A4','text'); await h.edit(page,'B1','=mAx(A1:A4)');
  await h.persisted(page,()=>h.formula(page,'B1','=mAx(A1:A4)','-10'));
});
