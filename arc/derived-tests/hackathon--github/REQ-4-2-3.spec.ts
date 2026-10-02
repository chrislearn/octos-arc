import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-3: repository code result opens matching file with persisted code context", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click(); await h.persisted(page, () => expect(h.text(page,'Document search flow').first()).toBeVisible()); await expect(h.link(page,'README.md')).toBeVisible();
});

test("REQ-4-2-3: no code matches retain exact query across repeated searches", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for(let i=0;i<2;i++){ await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-token'); await search.press('Enter'); await h.link(page,'Code').click(); await expect(h.text(page,'No code results').first()).toBeVisible(); await expect(search).toHaveValue('no-such-token'); await expect(h.link(page,'README.md')).toHaveCount(0); }
});
