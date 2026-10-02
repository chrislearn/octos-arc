import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-2-2-3: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.memberOrganization(page);await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('new-member'); await h.choose(page,'Role','Member'); await h.button(page,'Add member').last().click(); await h.persisted(page,()=>expect(h.text(page,'new-member').first()).toBeVisible()); const other=await browser.newContext({baseURL:new URL(page.url()).origin}); try {const p=await other.newPage(); await h.signIn(p,'new-member'); await h.button(p,'Account menu').click(); await h.link(p,'Your organizations').click(); await expect(h.link(p,'Acme Demo')).toBeVisible(); await h.link(p,'Acme Demo').click(); await h.link(p,'Repositories').click(); await expect(h.link(p,'secret-research')).toHaveCount(0);} finally {await other.close();}
});

test("REQ-2-2-3: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"org-owner"); await h.memberOrganization(page);await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('existing-member'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account is already a member')).toBeVisible(); await h.field(page,'Username or email').fill('unknown-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account not found')).toBeVisible(); await page.reload(); await expect(h.text(page,'existing-member')).toHaveCount(1);
});

test("REQ-2-2-3: People denies visitors and nonmembers while an ordinary member can view members", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'People').click();
  await expect(h.text(page,'protected-member')).toBeVisible(); const address=page.url();
  await h.signOut(page); await page.goto(address);
  await h.persisted(page,async()=>{
    await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
    await expect(h.text(page,'protected-member')).toHaveCount(0); await expect(h.text(page,'bob-reviewer')).toHaveCount(0);
  });
  await h.signIn(page,'alice-dev'); await page.goto(address);
  await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
  await expect(h.text(page,'protected-member')).toHaveCount(0);
  await h.signOut(page); await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'People').click();
  await h.persisted(page,()=>expect(h.text(page,'protected-member')).toBeVisible());
});

test("REQ-2-2-3: adding Member is immediate, listed after own login, but grants no private access", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'member-add'); await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('new-member'); await h.choose(page,'Role','Member'); await h.button(page,'Add member').last().click();
    await h.persisted(page, () => expect(h.text(page,'new-member').first()).toBeVisible()); await expect(h.text(page,'Pending')).toHaveCount(0); await expect(h.text(page,'Awaiting')).toHaveCount(0);
    await h.repo(page,h.fixtureRepo('member-add')); const privateAddress=page.url(); await h.signOut(page); await h.signIn(page,'new-member'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await expect(h.text(page,h.orgName('member-add')).first()).toBeVisible(); await page.goto(privateAddress); await expect(h.text(page,'Access denied').first()).toBeVisible();
});

test("REQ-2-2-3: unknown and duplicate member keep form open and do not duplicate membership", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.organization(page,'member-invalid'); await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('unknown-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account not found').first()).toBeVisible();
    await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account is already a member').first()).toBeVisible(); await expect(h.field(page,'Username or email')).toBeVisible(); await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
});
