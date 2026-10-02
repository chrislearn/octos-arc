import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-2-1: default personal namespace creates initialized Private repository and saved README", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.link(page,'New repository').click(); const name=h.unique('pw-repo'); await h.field(page,'Repository name').fill(name); await h.field(page,'Description').fill('Repository created by Playwright'); await page.getByRole('radio',{name:'Private',exact:true}).check(); await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check(); await h.button(page,'Create repository').click();
  await h.persisted(page, async () => { await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible(); await expect(h.text(page,'Private').first()).toBeVisible(); await expect(h.link(page,'README.md')).toBeVisible(); await expect(h.text(page,'Repository created by Playwright').first()).toBeVisible(); });
});

test("REQ-3-2-1: duplicate and empty repository names retain form and create no repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.link(page,'New repository').click(); await h.field(page,'Repository name').fill('acme-docs'); await h.button(page,'Create repository').click(); await expect(h.field(page,'Repository name')).toBeVisible(); await expect(page.getByRole('heading',{name:'alice-dev/acme-docs',exact:true})).toHaveCount(0); await h.field(page,'Repository name').fill(''); await h.button(page,'Create repository').click(); await expect(h.field(page,'Repository name')).toBeVisible();
});
