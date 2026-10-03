import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-6-2-4: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"pr-contributor"); await h.canonicalRepo(page);await h.link(page,'Compare').click(); await expect(h.text(page,'src/search.ts')).toBeVisible(); await h.choose(page,'Compare','draft-create-feature'); await h.button(page,'Compare changes').click(); await h.button(page,'Create draft pull request').click(); const title=h.unique('pw-draft'); await h.field(page,'Title').fill(title); await h.button(page,'Create draft pull request').click(); await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Draft').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeDisabled();});
});

test("REQ-6-2-4: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"draft-author"); await h.scenarioPr(page,"Draft onboarding update","acme-docs"); await h.button(page,'Ready for review').click(); const confirm=h.button(page,'Confirm'); if(await confirm.isVisible()) await confirm.click(); await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:'Draft onboarding update',exact:true})).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'draft-feature').first()).toBeVisible();});
});

test("REQ-6-2-4: stage3 feedback: a fresh session can create a draft through the default comparison after an ordinary PR", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const account=await h.register(page); await h.signIn(page,account.username);
  await h.link(page,'New repository').click(); const repository=h.unique('comparison-defaults');
  await h.field(page,'Repository name').fill(repository);
  await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check();
  await h.button(page,'Create repository').click(); await expect(h.button(page,'Branch main')).toBeVisible();
  const repositoryAddress=page.url(); const branches=[h.unique('ordinary'),h.unique('draft')];
  for(const branch of branches) {
    await page.goto(repositoryAddress); await h.button(page,'Branch main').click();
    await h.field(page,'Find branch').fill(branch); await h.option(page,`Create branch: ${branch}`);
    await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('change.md'); await h.field(page,'File contents').fill(branch);
    await h.field(page,'Commit message').fill('Change '+branch); await h.button(page,'Commit changes').click();
    await expect(page.locator('pre')).toHaveText(branch);
  }
  await page.goto(repositoryAddress); await h.link(page,'Compare').click();
  await h.chosen(page,'Compare',branches[0]); const explicitComparison=page.url();
  await h.button(page,'Create pull request').click(); const ordinary=h.unique('Ordinary PR');
  await h.field(page,'Title').fill(ordinary); await h.button(page,'Create pull request').click();
  await expect(page.getByRole('heading',{name:ordinary,exact:true})).toBeVisible(); const ordinaryAddress=page.url();
  const fresh=await browser.newContext();
  try {
    const draftPage=await fresh.newPage(); await h.signIn(draftPage,account.username);
    await draftPage.goto(repositoryAddress); await h.link(draftPage,'Compare').click();
    // Do not manually choose the draft seed branch: that hid the original bug.
    await h.chosen(draftPage,'Compare',branches[1]);
    await h.button(draftPage,'Create draft pull request').click(); const draft=h.unique('Draft PR');
    await h.field(draftPage,'Title').fill(draft); await h.button(draftPage,'Create draft pull request').click();
    await h.persisted(draftPage,async()=>{
      await expect(draftPage.getByRole('heading',{name:draft,exact:true})).toBeVisible();
      await expect(h.text(draftPage,'Draft')).toBeVisible(); await expect(h.button(draftPage,'Merge pull request')).toBeDisabled();
    });
  } finally { await fresh.close(); }
  // Explicit user selections must stay unchanged, and duplicate creation remains rejected.
  await page.goto(explicitComparison); await h.chosen(page,'Compare',branches[0]);
  await h.button(page,'Create pull request').click(); const duplicate=h.unique('Duplicate PR');
  await h.field(page,'Title').fill(duplicate); await h.button(page,'Create pull request').click();
  await expect(page.getByText('A pull request already exists for these branches',{exact:true})).toBeVisible();
  await page.goto(ordinaryAddress); await expect(page.getByRole('heading',{name:ordinary,exact:true})).toBeVisible();
  await h.link(page,'Pull requests').click(); await expect(h.link(page,duplicate)).toHaveCount(0);
});

test("REQ-6-2-4: Draft creation is persistent and has present disabled merge action", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.compare(page,'pr-draft-create'); await h.button(page,'Create draft pull request').click(); const title=h.unique('pw-draft'); await h.field(page,'Title').fill(title); await h.button(page,'Create draft pull request').click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Draft').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeDisabled(); });
});

test("REQ-6-2-4: author marks Draft ready without changing title or branches", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.pr(page,'pr-ready','Draft onboarding update'); await h.button(page,'Ready for review').click(); const confirm=h.button(page,'Confirm'); if(await confirm.isVisible()) await confirm.click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Draft onboarding update',exact:true})).toBeVisible(); await expect(h.text(page,'Draft')).toHaveCount(0); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'draft-feature').first()).toBeVisible(); await expect(h.text(page,'main').first()).toBeVisible(); await expect(h.text(page,'Ready for review').first()).toBeVisible(); });
});
