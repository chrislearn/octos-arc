import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-deferred-1-2-2: renaming is scoped to current workbook and updates refreshed home record", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.blank(page); const first=h.unique(); await h.renameWorkbook(page,first); const address=page.url(); await h.edit(page,'A1','keep-original-data');
  await h.blank(page); const second=h.unique(); await h.renameWorkbook(page,second); await h.edit(page,'A1','keep-second-data');
  await page.goto(address); const renamed=h.unique(); await h.renameWorkbook(page,`  ${renamed}  `); await page.goto('/'); await page.reload();
  await expect(page.getByRole('link',{name:first,exact:true})).toHaveCount(0); await expect(page.getByRole('link',{name:renamed,exact:true})).toBeVisible(); await expect(page.getByRole('link',{name:second,exact:true})).toBeVisible();
  await h.reopen(page,renamed); await h.values(page,{A1:'keep-original-data'}); await h.reopen(page,second); await h.values(page,{A1:'keep-second-data'});
});
