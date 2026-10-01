import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("INTEGRATION-team-access: guide: direct team grant changes effective permissions without hierarchy inheritance or account deletion", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const member=await browser.newContext(), owner=await browser.newContext(), child=await browser.newContext();
  try {
    const bob=await member.newPage(), adminOwner=await owner.newPage(), childMember=await child.newPage();
    let address='';
    await test.step('A direct team member has Write while a child-team member keeps only direct Read',async()=>{
      await h.signIn(bob,'bob-reviewer'); address=await h.repo(bob,h.fixtureRepo('guide-team-access')); await expect(h.button(bob,'Add file')).toBeVisible();
      await h.signIn(childMember,'spec-read'); await childMember.goto(address); await expect(childMember.getByRole('heading').filter({hasText:h.fixtureRepo('guide-team-access')})).toBeVisible(); await expect(h.button(childMember,'Add file')).toHaveCount(0);
    });
    await test.step('Replacing the team Write grant with Read revokes writes in an already-open session',async()=>{
      await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('guide-team-access')); await h.settings(page,'Manage access');
      const row=page.getByRole('row',{name:/frontend-team/}); await row.getByRole('combobox',{name:'Role',exact:true}).selectOption({label:'Read'}); await h.button(row,'Save').click();
      await h.persisted(page,()=>expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Read'));
      await bob.reload(); await expect(bob.getByRole('heading').filter({hasText:h.fixtureRepo('guide-team-access')})).toBeVisible(); await expect(h.button(bob,'Add file')).toHaveCount(0);
    });
    await test.step('Removing direct membership revokes private access but preserves the account and other grants',async()=>{
      await h.signIn(adminOwner,'spec-owner'); await h.organization(adminOwner,'guide-team-access'); await h.link(adminOwner,'Teams').click(); await h.link(adminOwner,'frontend-team').click(); await h.link(adminOwner,'Members').click();
      await h.button(adminOwner,'Remove bob-reviewer').click(); await h.persisted(adminOwner,()=>expect(h.button(adminOwner,'Remove bob-reviewer')).toHaveCount(0));
      await bob.goto(address); await expect(h.text(bob,'Access denied').first()).toBeVisible(); await expect(h.button(bob,'Account menu')).toBeVisible();
      await childMember.reload(); await expect(childMember.getByRole('heading').filter({hasText:h.fixtureRepo('guide-team-access')})).toBeVisible();
      await h.signOut(bob); await h.signIn(bob,'bob-reviewer'); await bob.goto(address); await expect(h.text(bob,'Access denied').first()).toBeVisible();
    });
  } finally { await member.close(); await owner.close(); await child.close(); }
});
