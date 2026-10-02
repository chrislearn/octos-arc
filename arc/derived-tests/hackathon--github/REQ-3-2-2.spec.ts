import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-3-2-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"fork-user"); await h.canonicalRepo(page);await h.button(page,'Fork').click(); const name=h.unique('pw-fork'); await h.field(page,'Repository name').fill(name); await h.button(page,'Create fork').click(); await h.persisted(page,async()=>{await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible(); await expect(page.getByText(/Forked from/).first()).toBeVisible(); await expect(h.link(page,'README.md')).toBeVisible();});
});

test("REQ-3-2-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"fork-user"); await h.canonicalRepo(page);await h.button(page,'Fork').click(); await h.field(page,'Repository name').fill('acme-docs-fork'); await h.button(page,'Create fork').click(); await expect(page.getByText(/Repository name already exists/)).toBeVisible();
});

test("REQ-3-2-2: fork records source relationship and independent readable history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.repo(page); await h.button(page,'Fork').click(); const name=h.unique('pw-fork'); await h.field(page,'Repository name').fill(name); await h.button(page,'Create fork').click();
    await h.persisted(page, async () => { await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible(); await expect(h.text(page,'Forked from acme-docs').first()).toBeVisible(); await expect(h.link(page,'README.md')).toBeVisible(); }); await h.link(page,'Commits').click(); await expect(h.text(page,'Document search flow').first()).toBeVisible();
});

test("REQ-3-2-2: conflicting fork name cannot open or modify an existing repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page); await h.repo(page); await h.button(page,'Fork').click(); await h.field(page,'Repository name').fill('acme-docs-fork'); await h.button(page,'Create fork').click(); await expect(h.field(page,'Repository name')).toBeVisible(); await expect(page.getByRole('heading',{name:'alice-dev/acme-docs-fork',exact:true})).toHaveCount(0);
});
