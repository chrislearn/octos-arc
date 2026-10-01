"""Cross-node guidance, run by final acceptance rather than a first-node gate.

Only public controls and browser-discovered addresses are used. Steps explain
the business transitions and assert both the change and the preserved state.
"""

def register(g, s):
    g('REQ-6-5', 'guide: new compare commit invalidates review/check, preserves comments and merges only after renewal', r'''
    const reviewer=await browser.newContext(), maintainer=await browser.newContext(), writer=await browser.newContext();
    try {
      const review=await reviewer.newPage(), merge=await maintainer.newPage(), write=await writer.newPage();
      const comment=h.unique('anchored'), firstSummary=h.unique('approved-old'), nextSummary=h.unique('approved-new');
      let oldRevision='';
      await test.step('Remember an immutable base revision before any mutation',async()=>{
        await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('guide-review-cycle')); await h.link(page,'Commits').click();
        await h.link(page,'Document search flow').click(); oldRevision=page.url();
        await expect(page.locator('body')).toContainText('export const search = "search flow";');
      });
      await test.step('Publish a line comment and approve the current compare commit',async()=>{
        await h.signIn(review,'bob-reviewer'); await h.pr(review,'guide-review-cycle'); await h.link(review,'Files changed').click();
        await h.button(review,'Add comment').first().click(); await h.field(review,'Comment').fill(comment); await h.button(review,'Add single comment').click();
        await h.button(review,'Review changes').click(); await h.field(review,'Summary').fill(firstSummary); await review.getByRole('radio',{name:'Approve',exact:true}).check(); await h.button(review,'Submit review').click();
        await h.persisted(review,()=>expect(h.text(review,comment).first()).toBeVisible());
      });
      await test.step('Approval and successful check together enable Maintain to merge',async()=>{
        await h.pr(page,'guide-review-cycle'); await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await expect(h.text(page,'test: success')).toBeVisible();
        await h.signIn(merge,'spec-maintain'); await h.pr(merge,'guide-review-cycle'); await expect(h.button(merge,'Merge pull request')).toBeEnabled();
      });
      await test.step('The author advances only the compare branch with a real file commit',async()=>{
        await h.signIn(write,'spec-write'); await h.repo(write,h.fixtureRepo('guide-review-cycle')); await h.button(write,'Branch main').click(); await h.option(write,'feature-search');
        await h.link(write,'src').click(); await h.link(write,'search.ts').click(); await h.button(write,'Edit').click();
        await h.field(write,'File contents').fill('export const search = "reviewed second head";'); await h.field(write,'Commit message').fill('Advance compare for renewed review'); await h.button(write,'Commit changes').click();
        await h.persisted(write,()=>expect(h.text(write,'export const search = "reviewed second head";')).toBeVisible());
      });
      await test.step('Old decisions/check no longer satisfy protection; old line comment remains Outdated',async()=>{
        await merge.reload(); await expect(h.button(merge,'Merge pull request')).toBeDisabled(); await expect(h.text(merge,'Review required by branch protection')).toBeVisible();
        await page.reload(); await expect(h.text(page,'test: pending')).toBeVisible(); await review.reload();
        await expect(h.text(review,firstSummary)).toBeVisible(); await expect(h.text(review,comment).first()).toBeVisible();
        // Outdated is required for the anchored comment. Stale review decisions
        // are proved by the merge gate; their history needs no extra UI badge.
        // Exclude the neighbouring review so its badge cannot satisfy this check.
        const marked=h.text(review,comment).first().locator(`xpath=ancestor::*[.//*[normalize-space(.)="Outdated"] and not(.//*[normalize-space(.)="${firstSummary}"])][1]`);
        await expect(h.text(marked,'Outdated').first()).toBeVisible();
      });
      await test.step('A renewed approval alone is insufficient until Admin sets the current check',async()=>{
        await h.button(review,'Review changes').click(); await h.field(review,'Summary').fill(nextSummary); await review.getByRole('radio',{name:'Approve',exact:true}).check(); await h.button(review,'Submit review').click();
        await expect(h.text(review,nextSummary)).toBeVisible(); await merge.reload(); await expect(h.button(merge,'Merge pull request')).toBeDisabled();
        await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await expect(h.text(page,'test: success')).toBeVisible();
        await merge.reload(); await expect(h.button(merge,'Merge pull request')).toBeEnabled(); await h.button(merge,'Merge pull request').click(); await h.button(merge,'Confirm merge').click(); await h.persisted(merge,()=>expect(h.text(merge,'Merged').first()).toBeVisible());
      });
      await test.step('Merged base has the new bytes, terminal status and unchanged historical revision',async()=>{
        await expect(h.button(merge,'Reopen pull request')).toHaveCount(0); await h.repo(page,h.fixtureRepo('guide-review-cycle')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
        await h.persisted(page,()=>expect(h.text(page,'export const search = "reviewed second head";')).toBeVisible());
        await page.goto(oldRevision); await expect(page.locator('body')).toContainText('export const search = "search flow";'); await expect(page.locator('body')).not.toContainText('reviewed second head');
      });
    } finally { await reviewer.close(); await maintainer.close(); await writer.close(); }
    ''', 'guide-review-cycle', file='INTEGRATION-review-cycle', requires=['REQ-1-1-2','REQ-4-2-1','REQ-4-2-2','REQ-4-4','REQ-6-1','REQ-6-3-3','REQ-6-3-4','REQ-6-5'])

    g('REQ-2-3', 'guide: direct team grant changes effective permissions without hierarchy inheritance or account deletion', r'''
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
    ''', 'guide-team-access', file='INTEGRATION-team-access', requires=['REQ-1-1-2','REQ-1-2','REQ-2-2-2','REQ-2-3','REQ-3-4','REQ-4-4'])

    g('REQ-4-4', 'successful file write adds a commit while an earlier revision keeps its original bytes', r'''
    await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-history')); await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); const original=page.url();
    await page.goto(address); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.button(page,'Edit').click(); const message=h.unique('Update');
    await h.field(page,'File contents').fill('export const search = "new immutable snapshot";'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await expect(h.text(page,'export const search = "new immutable snapshot";')).toBeVisible();
    await h.link(page,'Commits').click(); await expect(h.link(page,message)).toBeVisible(); await page.goto(original);
    await h.persisted(page,async()=>{ await expect(page.locator('body')).toContainText('export const search = "search flow";'); await expect(page.locator('body')).not.toContainText('new immutable snapshot'); });
    ''', 'file-history', file='INTEGRATION-file-history', requires=['REQ-4-4','REQ-4-2-1','REQ-4-2-2'])

    s('REQ-1-1-1', 'edited workbook state is shared by saved address across independent browser sessions', r'''
    await h.blank(page); const address=page.url(); await h.edit(page,'F8','unique-workbook-state'); await h.persisted(page,()=>h.values(page,{F8:'unique-workbook-state'}));
    const later=await browser.newContext();
    try { const p=await later.newPage(); await p.goto(address); await h.values(p,{F8:'unique-workbook-state'}); await h.edit(p,'F8','later-session-edit'); await h.values(p,{F8:'later-session-edit'}); await page.reload(); await h.values(page,{F8:'later-session-edit'}); }
    finally { await later.close(); }
    ''', file='INTEGRATION-workbook-context', requires=['REQ-1-1-1','REQ-1-2-1','REQ-3-1-1'])

    s('REQ-5-3-1', 'guide: validation, atomic paste, undo, filtered export and explicit pivot refresh preserve consistent state', r'''
    let address='';
    await test.step('Create raw records, dependent formulas and inclusive numeric rules',async()=>{
      await h.sourceData(page); address=page.url(); await h.edit(page,'E2','=B2*2'); await h.edit(page,'E3','=SUM(B2:B4)'); await h.validation(page,'B2','B4');
      await h.formula(page,'E2','=B2*2','20'); await h.formula(page,'E3','=SUM(B2:B4)','60');
    });
    await test.step('One invalid destination rejects every value and leaves all dependent results unchanged',async()=>{
      await h.paste(page,'B2','15\n101\n35'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible();
      await h.values(page,{B2:'10',B3:'20',B4:'30',E2:'20',E3:'60'});
    });
    await test.step('Valid bulk paste recalculates; undo and redo restore the whole operation',async()=>{
      await h.paste(page,'B2','15\n25\n35'); await h.values(page,{B2:'15',B3:'25',B4:'35',E2:'30',E3:'75'});
      await h.button(page,'Undo').click(); await h.values(page,{B2:'10',B3:'20',B4:'30',E2:'20',E3:'60'});
      await h.button(page,'Redo').click(); await h.values(page,{B2:'15',B3:'25',B4:'35',E2:'30',E3:'75'});
    });
    await test.step('Filtering hides records without removing them from export or pivot aggregation',async()=>{
      await h.range(page,'A1','C4'); await h.data(page,'Create filter'); await h.filterValues(page,'Region',['East']); await h.visibleRows(page,['A2','A4'],['A3']);
      expect(h.parseCSV(await h.csv(page))).toEqual([['Region','Sales','Status','',''],['East','15','Open','','30'],['North','25','Closed','','75'],['East','35','Closed','','']]);
      await h.pivot(page); await h.values(page,{A2:'East',B2:'50',A3:'North',B3:'25',A4:'Grand Total',B4:'75'});
    });
    await test.step('Source edits recalculate formulas but retain the old pivot result until Refresh',async()=>{
      await h.tab(page,'Sheet1').click(); await h.edit(page,'B2','20'); await h.values(page,{E2:'40',E3:'80'});
      await h.tab(page,'Pivot1').click(); await h.values(page,{B2:'50',B3:'25',B4:'75'}); await h.button(page,'Refresh pivot table').click(); await h.values(page,{B2:'55',B3:'25',B4:'80'});
    });
    await test.step('Deleting the value field makes refresh fail without erasing the previous result',async()=>{
      await h.tab(page,'Sheet1').click(); await h.structure(page,'column','B','Delete column'); await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click();
      await expect(h.text(page,'Pivot field is no longer available. Select a new field.').filter({visible:true}).first()).toBeVisible(); await h.values(page,{B2:'55',B3:'25',B4:'80'});
    });
    await test.step('Undo restores the source structure, formulas, rules and pivot validity together',async()=>{
      await h.tab(page,'Sheet1').click(); await h.button(page,'Undo').click(); await h.values(page,{B1:'Sales',B2:'20',B3:'25',B4:'35',E2:'40',E3:'80'});
      await h.edit(page,'B2','101'); await expect(page.getByText(/Please enter a number (?:from 0 to 100|between 0 and 100)/).first()).toBeVisible(); await h.values(page,{B2:'20',E2:'40',E3:'80'});
      await h.tab(page,'Pivot1').click(); await h.button(page,'Refresh pivot table').click(); await h.persisted(page,()=>h.values(page,{B2:'55',B3:'25',B4:'80'}));
    });
    await test.step('An independent browser reads the same durable result',async()=>{
      const later=await browser.newContext();
      try { const p=await later.newPage(); await p.goto(address); await expect(h.tab(p,'Pivot1')).toHaveAttribute('aria-selected','true'); await h.values(p,{B2:'55',B3:'25',B4:'80'}); }
      finally { await later.close(); }
    });
    ''', file='INTEGRATION-data-workflow', requires=['REQ-1-1-1','REQ-1-2-1','REQ-1-3-2','REQ-2-1-2','REQ-2-2-2','REQ-3-1-1','REQ-3-1-2','REQ-3-2-2','REQ-4-1-1','REQ-4-2-1','REQ-5-1-2','REQ-5-2-1','REQ-5-3-1'])
