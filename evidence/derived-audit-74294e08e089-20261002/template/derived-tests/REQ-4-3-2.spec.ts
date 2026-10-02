import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-3-2: Write branch creation defaults to current head and switches immediately", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('branch-create')); await h.button(page,'Branch main').click(); const name=h.unique('pw-branch'); await h.field(page,'Find branch').fill(name); await h.option(page,`Create branch: ${name}`); await h.persisted(page, () => expect(h.button(page,`Branch ${name}`)).toBeVisible()); await expect(h.link(page,'README.md')).toBeVisible();
});

test("REQ-4-3-2: invalid branch is rejected live and never created", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('branch-invalid')); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('invalid..branch'); await expect(h.text(page,'Invalid branch').first()).toBeVisible(); await expect(page.getByRole('option',{name:'Create branch: invalid..branch',exact:true})).toHaveCount(0); await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
});

test("REQ-4-3-2: spec-read cannot create branch reference", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"spec-read"); await h.repo(page,h.fixtureRepo('branch-permission-'+"spec-read"));
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch');
  const create=page.getByRole('option',{name:'Create branch: pw-denied-branch',exact:true}); if(await create.count() && await create.isEnabled()) await create.click();
  await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch'); await expect(page.getByRole('option',{name:'pw-denied-branch',exact:true})).toHaveCount(0);
});

test("REQ-4-3-2: spec-triage cannot create branch reference", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"spec-triage"); await h.repo(page,h.fixtureRepo('branch-permission-'+"spec-triage"));
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch');
  const create=page.getByRole('option',{name:'Create branch: pw-denied-branch',exact:true}); if(await create.count() && await create.isEnabled()) await create.click();
  await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch'); await expect(page.getByRole('option',{name:'pw-denied-branch',exact:true})).toHaveCount(0);
});
