import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-1-3-1: CSV import preserves every ordered field, Unicode, quotes and embedded newline", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await h.button(page, 'Import CSV').click(); const name = h.unique();
  const dialog = page.getByRole('dialog', { name: 'Import CSV', exact: true });
  await h.field(dialog, 'CSV file').setInputFiles({ name: `${name}.csv`, mimeType: 'text/csv', buffer: Buffer.from('名称,备注,值,空\r\n中文,"逗号,文本",12,\r\nEnglish,"双""引号\n下一行",007,', 'utf8') });
  await h.button(dialog, 'Confirm import').click(); await expect(h.text(page, name).first()).toBeVisible();
  await h.persisted(page, () => h.ordinary(page, { A1: '名称', B1: '备注', C1: '值', D1: '空', A2: '中文', B2: '逗号,文本', C2: '12', D2: '', A3: 'English', B3: '双"引号\n下一行', C3: '007', D3: '' }));
});

test("REQ-1-3-1: unclosed CSV quote leaves no partial workbook", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); const before = await page.getByRole('link').allTextContents(); await h.button(page, 'Import CSV').click();
  const name = h.unique(), dialog = page.getByRole('dialog', { name: 'Import CSV', exact: true });
  await h.field(dialog, 'CSV file').setInputFiles({ name: `${name}.csv`, mimeType: 'text/csv', buffer: Buffer.from('A,B\n1,"unclosed') });
  await h.button(dialog, 'Confirm import').click(); await expect(h.text(page, 'Invalid CSV file format. Import failed.').first()).toBeVisible();
  await page.goto('/'); await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
  expect(await page.getByRole('link').allTextContents()).toEqual(before); await page.reload();
  await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
});

test("REQ-1-3-1: import treats first row as data and strips only the final csv extension from the file name", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); const name=`${h.unique()}.part`; await h.button(page,'Import CSV').click(); const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from('Region,Sales,Status\nEast,1200,Open\nNorth,800,Closed')}); await h.button(dialog,'Confirm import').click();
  await expect(h.tab(page,'Sheet1')).toHaveAttribute('aria-selected','true'); await expect(page.getByRole('tab')).toHaveCount(1); const address=page.url();
  await h.ordinary(page,{A1:'Region',B1:'Sales',C1:'Status',A2:'East',B2:'1200',C2:'Open',A3:'North',B3:'800',C3:'Closed'}); await h.edit(page,'A1','ordinary-first-row');
  await page.goto('/'); await page.reload(); await expect(page.getByRole('link',{name,exact:true})).toBeVisible(); await page.goto(address); await h.values(page,{A1:'ordinary-first-row',A2:'East',A3:'North'});
});
