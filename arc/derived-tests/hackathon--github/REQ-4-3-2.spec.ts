import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-3-2: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"branch-contributor"); await h.repo(page,'branch-switch-demo'); await h.button(page,'Branch main').click(); const name=h.unique('pw-branch'); await h.field(page,'Find branch').fill(name); await h.option(page,`Create branch: ${name}`); await h.persisted(page,()=>expect(h.button(page,`Branch ${name}`)).toBeVisible());
});

test("REQ-4-3-2: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"branch-contributor"); await h.repo(page,'branch-switch-demo'); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('invalid..branch'); await expect(h.text(page,'Invalid branch')).toBeVisible(); await expect(page.getByRole('option',{name:'Create branch: invalid..branch',exact:true})).toHaveCount(0);
});

test("REQ-4-3-2: legal slash branch survives creation reload switching and nested file browsing", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'branch-contributor'); await h.repo(page,'branch-switch-demo');
  const branch=`audit/${h.unique('slash')}`;
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill(branch);
  await page.getByRole('option',{name:`Create branch: ${branch}`,exact:true}).click();
  await h.persisted(page,()=>expect(h.button(page,`Branch ${branch}`)).toBeVisible());
  await h.button(page,`Branch ${branch}`).click(); await h.option(page,'main');
  await expect(h.button(page,'Branch main')).toBeVisible();
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill(branch); await h.option(page,branch);
  await h.persisted(page,()=>expect(h.button(page,`Branch ${branch}`)).toBeVisible());
  await h.link(page,'src').click(); await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
  await h.link(page,'search.ts').click();
  await h.persisted(page,async()=>{
    await expect(h.text(page,'export const search = "search flow";')).toBeVisible();
    await expect(h.renderedSubstring(page,`Branch ${branch}`).first()).toBeVisible();
  });
});

test("REQ-4-3-2: Write branch creation defaults to current head and switches immediately", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.repo(page,h.fixtureRepo('branch-create')); await h.button(page,'Branch main').click(); const name=h.unique('pw-branch'); await h.field(page,'Find branch').fill(name); await h.option(page,`Create branch: ${name}`); await h.persisted(page, () => expect(h.button(page,`Branch ${name}`)).toBeVisible()); await expect(h.link(page,'README.md')).toBeVisible();
});

test("REQ-4-3-2: invalid branch is rejected live and never created", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.repo(page,h.fixtureRepo('branch-invalid')); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('invalid..branch'); await expect(h.text(page,'Invalid branch').first()).toBeVisible(); await expect(page.getByRole('option',{name:'Create branch: invalid..branch',exact:true})).toHaveCount(0); await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
});

test("REQ-4-3-2: issue-viewer cannot create branch reference", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"issue-viewer"); await h.repo(page,h.fixtureRepo('branch-permission-'+"issue-viewer"));
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch');
    const create=page.getByRole('option',{name:'Create branch: pw-denied-branch',exact:true}); if(await create.count() && await create.isEnabled()) await create.click();
    await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch'); await expect(page.getByRole('option',{name:'pw-denied-branch',exact:true})).toHaveCount(0);
});

test("REQ-4-3-2: triage-collaborator cannot create branch reference", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"triage-collaborator"); await h.repo(page,h.fixtureRepo('branch-permission-'+"triage-collaborator"));
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch');
    const create=page.getByRole('option',{name:'Create branch: pw-denied-branch',exact:true}); if(await create.count() && await create.isEnabled()) await create.click();
    await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch'); await expect(page.getByRole('option',{name:'pw-denied-branch',exact:true})).toHaveCount(0);
});
