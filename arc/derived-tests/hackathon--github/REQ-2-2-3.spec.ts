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

test("REQ-2-2-3: selftest Sign in remains a link on the sign-in page and after protected organization reentry", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click();
  await expect(h.link(page,'Sign in')).toHaveCount(1); await expect(h.link(page,'Sign in')).toBeVisible();
  await expect(h.button(page,'Sign in')).toBeVisible();
  await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await expect(h.link(page,'Acme Demo')).toBeVisible(); const listAddress=page.url();
  await h.link(page,'Acme Demo').click(); await h.link(page,'People').click();
  await expect(h.text(page,'protected-member')).toBeVisible(); const peopleAddress=page.url();
  await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click();
  await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible(); const teamAddress=page.url();
  await h.signOut(page);
  for (const address of [listAddress,peopleAddress,teamAddress]) {
    await page.goto(address); await expect(h.link(page,'Sign in')).toBeVisible();
    await expect(h.button(page,'Account menu')).toHaveCount(0);
    await expect(h.text(page,'protected-member')).toHaveCount(0);
  }
});

test("REQ-2-2-3: selftest member role pointer selection submits and duplicate errors keep the form open", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'New organization').click(); const organization=h.unique('member-ui');
  await h.field(page,'Organization name').fill(organization); await h.field(page,'Display name').fill(organization);
  await h.button(page,'Create organization').click(); await h.link(page,'People').click();
  await expect(h.button(page,'Add member')).toBeVisible();

  await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer');
  await h.field(page,'Role').click(); await page.getByRole('option',{name:'Member',exact:true}).click({timeout:5000});
  await h.button(page,'Add member').click(); await expect(h.text(page,'bob-reviewer')).toBeVisible();
  await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
  await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer');
  await h.button(page,'Add member').click(); await expect(h.text(page,'Account is already a member')).toBeVisible();
  await expect(h.field(page,'Username or email')).toHaveValue('bob-reviewer');
  await h.field(page,'Username or email').fill('unknown-reviewer'); await h.button(page,'Add member').click();
  await expect(h.text(page,'Account not found')).toBeVisible(); await expect(h.field(page,'Username or email')).toHaveValue('unknown-reviewer');
  await h.button(page,'Cancel').click(); await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
});

test("REQ-2-2-3: selftest member role keyboard selection persists the selected Member role", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'New organization').click(); const organization=h.unique('member-ui');
  await h.field(page,'Organization name').fill(organization); await h.field(page,'Display name').fill(organization);
  await h.button(page,'Create organization').click(); await h.link(page,'People').click();
  await expect(h.button(page,'Add member')).toBeVisible();

  await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer');
  await h.field(page,'Role').press('ArrowDown'); await page.keyboard.press('m'); await page.keyboard.press('Enter');
  await h.chosen(page,'Role','Member'); await h.button(page,'Add member').click();
  const member=page.getByRole('listitem').filter({has:h.text(page,'bob-reviewer')});
  await h.persisted(page,async()=>{await expect(member).toHaveCount(1);await expect(h.text(member,'Member')).toBeVisible();});
});

test("REQ-2-2-3: member roles are associated with each account when multiple members share Member role", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
  await h.link(page,'New organization').click(); const organization=h.unique('member-roles');
  await h.field(page,'Organization name').fill(organization); await h.field(page,'Display name').fill(organization);
  await h.button(page,'Create organization').click(); await h.link(page,'People').click();
  for (const name of ['bob-reviewer','org-member']) {
    await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill(name);
    await h.choose(page,'Role','Member'); await h.button(page,'Add member').click();
    await expect(h.text(page,name)).toBeVisible();
  }
  await h.persisted(page,async()=>{
    for (const name of ['bob-reviewer','org-member']) {
      const member=page.getByRole('listitem').filter({has:h.text(page,name)});
      await expect(member).toHaveCount(1); await expect(h.text(member,'Member')).toBeVisible();
    }
    await expect(h.text(page,'Pending invitation')).toHaveCount(0);
  });
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
