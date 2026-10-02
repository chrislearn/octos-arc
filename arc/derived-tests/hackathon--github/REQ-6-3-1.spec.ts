import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-3-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.scenarioPr(page,"Overview onboarding PR","acme-docs"); await h.link(page,'Commits').click(); await expect(h.renderedSubstring(page,'Implement search flow').first()).toBeVisible(); await h.link(page,'Files changed').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
});

test("REQ-6-3-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.scenarioPr(page,"Overview onboarding PR","acme-docs"); await page.reload(); await expect(page.getByRole('heading',{name:'Overview onboarding PR',exact:true})).toBeVisible(); await h.link(page,'Commits').click(); await expect(h.renderedSubstring(page,'Implement search flow').first()).toBeVisible();
});

test("REQ-6-3-1: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.scenarioPr(page,"Overview onboarding PR","acme-docs"); await h.scenarioPr(page,"Overview onboarding PR","acme-docs"); await h.link(page,'Files changed').click(); await expect(page.getByRole('heading',{name:'Overview onboarding PR',exact:true})).toBeVisible(); await expect(h.text(page,'src/search.ts')).toBeVisible();
});

test("REQ-6-3-1: global search file issue and PR navigation share the prescribed organization repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const address=await h.repo(page);
  await expect(page.getByRole('heading').filter({hasText:'Acme Demo'}).filter({hasText:'acme-docs'})).toBeVisible();
  await h.link(page,'src').click(); await h.link(page,'README.md').click();
  await h.persisted(page,()=>expect(h.text(page,'Document search flow')).toBeVisible());
  await page.goto(address); await h.link(page,'Issues').click(); await h.link(page,'Improve onboarding').click();
  await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
  await page.goto(address); await h.link(page,'Pull requests').click(); await h.link(page,'Overview onboarding PR').click();
  await h.link(page,'Commits').click(); await expect(h.renderedSubstring(page,'Implement search flow').first()).toBeVisible();
  await h.link(page,'Files changed').click();
  await h.persisted(page,async()=>{
    await expect(page.getByRole('heading',{name:'Overview onboarding PR',exact:true})).toBeVisible();
    await expect(h.text(page,'src/search.ts')).toBeVisible();
  });
});

test("REQ-6-3-1: visitor PR overview, commits and changed-files navigation survives direct reopen", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.pr(page); const address=page.url(); await h.link(page,'Commits').click();
    await h.persisted(page,async()=>{
      await expect(h.renderedSubstring(page,'Implement search flow').first()).toBeVisible();
      // Compare-only history excludes ancestors already reachable from base.
      await expect(h.renderedSubstring(page,'Initialize empty repository')).toHaveCount(0);
      await expect(h.renderedSubstring(page,'Document search flow')).toHaveCount(0);
    });
    await h.link(page,'Files changed').click(); await expect(page.getByText(/Changed files/).first()).toBeVisible(); await page.goto(address); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.link(page,'Commits')).toBeVisible(); await expect(h.link(page,'Files changed')).toBeVisible(); });
});

test("REQ-6-3-1: context REQ-5-3-3: PR milestone toggles without cross-repository choices or deleting history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'pr-maintainer'); await h.repo(page,'foreign-milestone-repo'); await h.pr(page,'pr-milestone-node');
    await h.button(page,'Milestone').click(); await expect(page.getByRole('option',{name:'foreign-milestone',exact:true})).toHaveCount(0);
    await h.option(page,'v1.0'); await h.persisted(page,()=>expect(h.metadataValue(page,'Milestone','v1.0').first()).toBeVisible());
    await h.button(page,'Milestone').click(); await h.option(page,'None');
    await h.persisted(page,()=>expect(h.metadataValue(page,'Milestone','v1.0')).toHaveCount(0));
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();
    const discussion=page.getByRole('article').filter({hasText:'Please review this update.'});
    await expect(discussion).toHaveCount(1); await expect(discussion).toContainText('Please review this update.');
    await expect(discussion).toContainText('file-contributor');
});

test("REQ-6-3-1: context REQ-5-3-3: issue-viewer cannot change a PR milestone", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'issue-viewer'); await h.pr(page,'pr-milestone-denied-issue-viewer-node');
    await h.unavailable(page,'Milestone'); await h.persisted(page,()=>expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});

test("REQ-6-3-1: context REQ-5-3-3: file-contributor cannot change a PR milestone", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.pr(page,'pr-milestone-denied-file-contributor-node');
    await h.unavailable(page,'Milestone'); await h.persisted(page,()=>expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible());
});
