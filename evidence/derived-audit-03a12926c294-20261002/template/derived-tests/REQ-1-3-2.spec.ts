import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-3-2: export imported plain CSV preserves ordered escaping and active worksheet", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await page.goto('/'); await h.button(page, 'Import CSV').click();
  const name=h.unique(), dialog=page.getByRole('dialog',{name:'Import CSV',exact:true});
  await h.field(dialog,'CSV file').setInputFiles({name:`${name}.csv`,mimeType:'text/csv',buffer:Buffer.from('名称,备注,空\r\n中文,"逗号,文本",\r\nEnglish,"双""引号\n下一行",007','utf8')});
  await h.button(dialog,'Confirm import').click(); await expect(h.text(page,name).first()).toBeVisible();
  expect(h.parseCSV(await h.csv(page))).toEqual([['名称','备注','空'],['中文','逗号,文本',''],['English','双"引号\n下一行','007']]);
  await h.persisted(page,async()=>{ await expect(h.tab(page,'Sheet1')).toHaveAttribute('aria-selected','true'); await h.values(page,{A1:'名称',B2:'逗号,文本',B3:'双"引号\n下一行',C3:'007'}); });
});
