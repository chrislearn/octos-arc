import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

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
  await page.goto('/'); await expect(page.getByRole('link',{name:'Q3 Sales',exact:true})).toBeVisible(); const before = (await page.getByRole('link').allTextContents()).sort(); await h.button(page, 'Import CSV').click();
  const name = h.unique(), dialog = page.getByRole('dialog', { name: 'Import CSV', exact: true });
  await h.field(dialog, 'CSV file').setInputFiles({ name: `${name}.csv`, mimeType: 'text/csv', buffer: Buffer.from('A,B\n1,"unclosed') });
  await h.button(dialog, 'Confirm import').click(); await expect(h.text(page, 'Invalid CSV file format. Import failed.').first()).toBeVisible();
  await page.goto('/'); await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
  await expect.poll(async()=> (await page.getByRole('link').allTextContents()).sort()).toEqual(before); await page.reload();
  await expect(page.getByRole('link', { name, exact: true })).toHaveCount(0);
});

test("REQ-1-3-1: audit regression: complete import exposes AA columns and rows beyond the initial viewport", async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await h.button(page,'Import CSV').click(); const name=h.unique();
  const dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  const rows=Array.from({length:52},(_,r)=>Array.from({length:28},(_,c)=>`r${r+1}c${c+1}`).join(','));
  await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from(rows.join('\n'))});
  await h.button(dialog,'Confirm import').click(); await expect(h.text(page,name).first()).toBeVisible();
  await h.persisted(page,()=>h.values(page,{A1:'r1c1',Z1:'r1c26',AA1:'r1c27',AB1:'r1c28',A51:'r51c1',AA52:'r52c27',AB52:'r52c28'}));
});
