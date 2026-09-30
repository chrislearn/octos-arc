import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-1-2-2: trim and save workbook name updates editor and home entry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page, 'Rename workbook').click(); const name = h.unique();
  const original = await h.field(page, 'Workbook name').inputValue(); expect(original.trim()).not.toBe('');
  await h.field(page, 'Workbook name').fill(`  ${name}  `); await h.button(page, 'Save').click();
  await expect(h.text(page, name).first()).toBeVisible(); await page.goto('/');
  await page.getByRole('link', { name, exact: true }).click();
  await h.persisted(page, () => expect(h.text(page, name).first()).toBeVisible());
});

test("REQ-1-2-2: empty workbook name rejects without changing persisted name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); await h.button(page, 'Rename workbook').click(); const original = await h.field(page, 'Workbook name').inputValue();
  await h.field(page, 'Workbook name').fill('   '); await h.button(page, 'Save').click();
  await expect(h.text(page, 'Workbook name cannot be empty').first()).toBeVisible(); await page.reload();
  await h.button(page, 'Rename workbook').click(); await expect(h.field(page, 'Workbook name')).toHaveValue(original);
});

test("REQ-1-2-2: renaming is scoped to current workbook and updates refreshed home record", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const first=h.unique(); await h.renameWorkbook(page,first); const address=page.url(); await h.edit(page,'A1','keep-original-data');
  await h.blank(page); const second=h.unique(); await h.renameWorkbook(page,second); await h.edit(page,'A1','keep-second-data');
  await page.goto(address); const renamed=h.unique(); await h.renameWorkbook(page,`  ${renamed}  `); await page.goto('/'); await page.reload();
  await expect(page.getByRole('link',{name:first,exact:true})).toHaveCount(0); await expect(page.getByRole('link',{name:renamed,exact:true})).toBeVisible(); await expect(page.getByRole('link',{name:second,exact:true})).toBeVisible();
  await h.reopen(page,renamed); await h.values(page,{A1:'keep-original-data'}); await h.reopen(page,second); await h.values(page,{A1:'keep-second-data'});
});
