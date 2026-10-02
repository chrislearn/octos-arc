import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-4-4: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"file-contributor"); await h.repo(page,'file-management-demo'); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('pw-file')}.md`,content=h.unique('file-content'),message=`Add ${name}`; await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill(content); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await expect(h.text(page,content)).toBeVisible(); await h.link(page,'Commits').click(); await expect(h.link(page,message)).toBeVisible();
});

test("REQ-4-4: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,"file-contributor"); await h.repo(page,'file-management-demo'); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.field(page,'Commit message').fill(''); await h.button(page,'Commit changes').click(); await expect(h.fileValidationReason(page).first()).toBeVisible();
});

test("REQ-4-4: slash branch web writes edits and history remain isolated from main", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'branch-contributor'); const address=await h.repo(page,'branch-switch-demo');
  const branch=`audit/${h.unique('write')}`, name=h.unique('slash-file')+'.md';
  const path=`docs/${name}`, content=h.unique('saved-content'), edited=h.unique('edited-content');
  const message=h.unique('slash-commit'), editMessage=h.unique('slash-edit');
  await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill(branch);
  await page.getByRole('option',{name:`Create branch: ${branch}`,exact:true}).click();
  await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
  const branchAddress=page.url();
  await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
  await h.field(page,'File name').fill(path); await h.field(page,'File contents').fill(content);
  await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click();
  await h.persisted(page,async()=>{
    await expect(h.text(page,content)).toBeVisible(); await expect(h.renderedSubstring(page,`Branch ${branch}`).first()).toBeVisible();
  });
  await h.button(page,'Edit').click(); await expect(h.field(page,'File name')).toHaveValue(path);
  await expect(h.field(page,'File contents')).toHaveValue(content); await h.field(page,'File contents').fill(edited);
  await h.field(page,'Commit message').fill(editMessage); await h.button(page,'Commit changes').click();
  await h.persisted(page,()=>expect(h.text(page,edited)).toBeVisible());
  await h.link(page,'docs').click(); await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
  await h.link(page,name).click(); await expect(h.text(page,edited)).toBeVisible();
  await h.link(page,'Commits').click(); await expect(h.link(page,editMessage)).toBeVisible(); await expect(h.link(page,message)).toBeVisible();
  await page.goto(branchAddress); await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
  await h.link(page,'Commits').click(); await expect(h.link(page,editMessage)).toBeVisible();
  await page.goto(address); await expect(h.button(page,'Branch main')).toBeVisible();
  await expect(h.link(page,'docs')).toHaveCount(0); await h.link(page,'Commits').click();
  await expect(h.link(page,message)).toHaveCount(0); await expect(h.link(page,editMessage)).toHaveCount(0);
});

test("REQ-4-4: file creation persists exact contents", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); await h.repo(page,h.fixtureRepo('file-create')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('pw-file')}.md`,message=`Add ${name}`;
    await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('Persisted file contents'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await h.persisted(page, () => expect(h.text(page,'Persisted file contents').first()).toBeVisible());
});

test("REQ-4-4: invalid path rejects even with a valid commit message", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-invalid-path')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
    await expect(h.text(page,'Invalid file path').first()).toBeVisible(); await page.goto(address); await h.persisted(page,()=>expect(h.link(page,'invalid.md')).toHaveCount(0));
});

test("REQ-4-4: empty commit message rejects even with a valid file path", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-invalid-message')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('valid')}.md`;
    await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click();
    await expect(h.text(page,'Commit message is required').first()).toBeVisible(); await page.goto(address); await h.persisted(page,()=>expect(h.link(page,name)).toHaveCount(0));
});

test("REQ-4-4: guide: editing creates a real commit and an old revision retains its original bytes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('guide-file-edit-history'));
    let original=''; const message=h.unique('edit-history');
    await test.step('Remember an immutable revision before the write',async()=>{
      await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); original=page.url();
      await expect(page.locator('body')).toContainText('export const search = "search flow";');
    });
    await test.step('Edit through the actual file command, then reopen the saved result',async()=>{
      await page.goto(address); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.button(page,'Edit').click();
      await h.field(page,'File contents').fill('export const search = "quality guide edit";');
      await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click();
      await h.persisted(page,()=>expect(h.text(page,'export const search = "quality guide edit";')).toBeVisible());
    });
    await test.step('History gains that commit while the earlier snapshot stays immutable',async()=>{
      await h.link(page,'Commits').click(); await expect(h.link(page,message)).toBeVisible(); await page.goto(original);
      await h.persisted(page,async()=>{
        await expect(page.locator('body')).toContainText('export const search = "search flow";');
        await expect(page.locator('body')).not.toContainText('quality guide edit');
      });
    });
});

test("REQ-4-4: issue-viewer cannot commit files on a readable repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'issue-viewer'); const address=await h.repo(page,h.fixtureRepo('file-denied-issue-viewer'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address); await expect(h.link(page,'README.md')).toBeVisible();
    const name=h.unique('denied')+'.md',add=h.button(page,'Add file');
    if(await add.count() && await add.isVisible() && await add.isEnabled()) {
      await add.click(); const create=page.getByRole('menuitem',{name:'Create new file',exact:true});
      if(await create.count() && await create.isVisible() && await create.isEnabled()) {
        await create.click();
        for(const [label,value] of [['File name',name],['File contents','Must not be saved'],['Commit message','Attempt unauthorized write']]) {
          const field=h.field(page,label); if(await field.count() && await field.isEditable()) await field.fill(value);
        }
        const commit=h.button(page,'Commit changes'); if(await commit.count() && await commit.isEnabled()) await h.attemptSubmission(page,commit);
      }
    }
    await page.goto(address); await expect(h.link(page,name)).toHaveCount(0); await h.link(page,'Commits').click();
    await expect.poll(()=>h.historyLinks(page)).toEqual(history); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
});

test("REQ-4-4: triage-collaborator cannot commit files on a readable repository", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'triage-collaborator'); const address=await h.repo(page,h.fixtureRepo('file-denied-triage-collaborator'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address); await expect(h.link(page,'README.md')).toBeVisible();
    const name=h.unique('denied')+'.md',add=h.button(page,'Add file');
    if(await add.count() && await add.isVisible() && await add.isEnabled()) {
      await add.click(); const create=page.getByRole('menuitem',{name:'Create new file',exact:true});
      if(await create.count() && await create.isVisible() && await create.isEnabled()) {
        await create.click();
        for(const [label,value] of [['File name',name],['File contents','Must not be saved'],['Commit message','Attempt unauthorized write']]) {
          const field=h.field(page,label); if(await field.count() && await field.isEditable()) await field.fill(value);
        }
        const commit=h.button(page,'Commit changes'); if(await commit.count() && await commit.isEnabled()) await h.attemptSubmission(page,commit);
      }
    }
    await page.goto(address); await expect(h.link(page,name)).toHaveCount(0); await h.link(page,'Commits').click();
    await expect.poll(()=>h.historyLinks(page)).toEqual(history); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
});

test("REQ-4-4: absolute file path is rejected without advancing history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-path-absolute'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address);
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('/invalid.md'); await h.field(page,'File contents').fill('Rejected replacement');
    await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
    await expect(h.containsValue(page,'Invalid file path').first()).toBeVisible();
    await page.goto(address); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
    await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
});

test("REQ-4-4: existing-file file path is rejected without advancing history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-path-existing-file'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address);
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('README.md'); await h.field(page,'File contents').fill('Rejected replacement');
    await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
    await expect(h.containsValue(page,'Invalid file path').first()).toBeVisible();
    await page.goto(address); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
    await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
});

test("REQ-4-4: directory file path is rejected without advancing history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-path-directory'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address);
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('src'); await h.field(page,'File contents').fill('Rejected replacement');
    await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
    await expect(h.containsValue(page,'Invalid file path').first()).toBeVisible();
    await page.goto(address); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
    await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
});

test("REQ-4-4: overlong trimmed commit message leaves files and history unchanged", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-message-too-long'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address);
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    const name=h.unique('rejected')+'.md'; await h.field(page,'File name').fill(name);
    await h.field(page,'File contents').fill('Must not be committed'); await h.field(page,'Commit message').fill('x'.repeat(73));
    await h.button(page,'Commit changes').click(); await expect(h.field(page,'File name')).toBeVisible();
    await page.goto(address); await expect(h.link(page,name)).toHaveCount(0); await h.link(page,'Commits').click();
    await expect.poll(()=>h.historyLinks(page)).toEqual(history); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
});

test("REQ-4-4: context REQ-4-4: invalid path and empty message cannot change files or history", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-invalid-node')); await h.link(page,'Commits').click(); const before=await h.historyLinks(page); await page.goto(address); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click(); await expect(h.fileValidationReason(page).first()).toBeVisible(); await page.goto(address); await expect(h.link(page,'invalid.md')).toHaveCount(0); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page),{message:'Rejected commit must preserve history'}).toEqual(before); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(before);
});

test("REQ-4-4: context REQ-4-4: successful file write adds a commit while an earlier revision keeps its original bytes", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.signIn(page,'file-contributor'); const address=await h.repo(page,h.fixtureRepo('file-history-node')); await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); const original=page.url();
    await page.goto(address); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.button(page,'Edit').click(); const message=h.unique('Update');
    await h.field(page,'File contents').fill('export const search = "new immutable snapshot";'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await expect(h.text(page,'export const search = "new immutable snapshot";')).toBeVisible();
    await h.link(page,'Commits').click(); await expect(h.link(page,message)).toBeVisible(); await page.goto(original);
    await h.persisted(page,async()=>{ await expect(page.locator('body')).toContainText('export const search = "search flow";'); await expect(page.locator('body')).not.toContainText('new immutable snapshot'); });
});

test("REQ-4-4: context REQ-2-3: guide: direct team grant changes effective permissions without hierarchy inheritance or account deletion", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const member=await browser.newContext(), owner=await browser.newContext(), child=await browser.newContext();
    try {
      const bob=await member.newPage(), adminOwner=await owner.newPage(), childMember=await child.newPage();
      let address='';
      await test.step('A direct team member has Write while a child-team member keeps only direct Read',async()=>{
        await h.signIn(bob,'bob-reviewer'); address=await h.repo(bob,h.fixtureRepo('guide-team-access-node')); await expect(h.button(bob,'Add file')).toBeVisible();
        await h.signIn(childMember,'issue-viewer'); await childMember.goto(address); await expect(childMember.getByRole('heading').filter({hasText:h.fixtureRepo('guide-team-access-node')})).toBeVisible(); await expect(h.button(childMember,'Add file')).toHaveCount(0);
      });
      await test.step('Replacing the team Write grant with Read revokes writes in an already-open session',async()=>{
        await h.signIn(page,'repo-admin'); await h.repo(page,h.fixtureRepo('guide-team-access-node')); await h.settings(page,'Manage access');
        const row=page.getByRole('row',{name:/frontend-team/}); await h.choose(row,'Role','Read'); await h.button(row,'Save').click();
        await h.persisted(page,()=>expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Read'));
        await bob.reload(); await expect(bob.getByRole('heading').filter({hasText:h.fixtureRepo('guide-team-access-node')})).toBeVisible(); await expect(h.button(bob,'Add file')).toHaveCount(0);
      });
      await test.step('Removing direct membership revokes private access but preserves the account and other grants',async()=>{
        await h.signIn(adminOwner,'org-owner'); await h.organization(adminOwner,'guide-team-access-node'); await h.link(adminOwner,'Teams').click(); await h.link(adminOwner,'frontend-team').click(); await h.link(adminOwner,'Members').click();
        await h.button(adminOwner,'Remove bob-reviewer').click(); await h.persisted(adminOwner,()=>expect(h.button(adminOwner,'Remove bob-reviewer')).toHaveCount(0));
        await bob.goto(address); await expect(h.text(bob,'Access denied').first()).toBeVisible(); await expect(h.button(bob,'Account menu')).toBeVisible();
        await childMember.reload(); await expect(childMember.getByRole('heading').filter({hasText:h.fixtureRepo('guide-team-access-node')})).toBeVisible();
        await h.signOut(bob); await h.signIn(bob,'bob-reviewer'); await bob.goto(address); await expect(h.text(bob,'Access denied').first()).toBeVisible();
      });
    } finally { await member.close(); await owner.close(); await child.close(); }
});
