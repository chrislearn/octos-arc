import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-2-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.canonicalRepo(page);await h.link(page,'Commits').click(); await expect(h.link(page,'Document search flow')).toBeVisible(); await expect(h.containsValue(page,'alice-dev').first()).toBeVisible(); await expect(page.getByText(/ago/).first()).toBeVisible();
});

test("REQ-4-2-1: stage2 feedback: homepage Commits follows the selected repository and retains each row author", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.choose(page,'Workspace repository','Acme Demo/acme-docs'); await h.link(page,'Commits').click();
  for(const title of ['Document search flow','Initialize empty repository']) {
    const row=page.getByRole('listitem').filter({has:h.link(page,title)});
    await expect(row.getByText('alice-dev',{exact:true})).toBeVisible(); await expect(row).toContainText(/ago/);
  }
  await page.reload();
  for(const title of ['Document search flow','Initialize empty repository']) {
    const row=page.getByRole('listitem').filter({has:h.link(page,title)});
    await expect(row.getByText('alice-dev',{exact:true})).toBeVisible();
  }
});

test("REQ-4-2-1: branch commit history displays exact message, author and relative timestamp", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.repo(page); await h.link(page,'Commits').click(); await expect(h.text(page,'Document search flow').first()).toBeVisible(); await expect(h.text(page,'alice-dev').first()).toBeVisible(); await expect(page.getByText(/\bago\b/).first()).toBeVisible();
});

test("REQ-4-2-1: branch history keeps newest-first order and file history excludes unrelated commits", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const address=await h.repo(page); await h.link(page,'Commits').click();
    const history=await h.historyLinks(page);
    expect(history.indexOf('Document search flow')).toBeLessThan(history.indexOf('Initialize empty repository'));
    await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
    await page.goto(address); await h.link(page,'README.md').click(); await h.link(page,'Commits').click();
    await h.persisted(page,async()=>{
      await expect(h.link(page,'Document search flow')).toBeVisible();
      await expect(h.link(page,'Initialize empty repository')).toHaveCount(0);
    });
});
