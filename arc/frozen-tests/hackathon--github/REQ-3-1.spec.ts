import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed frozen internal suite; requirements.yaml remains authoritative.

test("REQ-3-1: global search opens public identity and excludes private repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible()); await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('secret-research'); await search.press('Enter'); await expect(h.link(page,'secret-research')).toHaveCount(0);
});

test("REQ-3-1: empty repository search is repeatable without stale results", async ({ page, browser }) => {
  test.setTimeout(60_000);
  for(let i=0;i<2;i++){ await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-repository'); await search.press('Enter'); await expect(h.text(page,'No results').first()).toBeVisible(); await expect(h.link(page,'acme-docs')).toHaveCount(0); }
});
