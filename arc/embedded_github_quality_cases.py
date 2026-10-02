"""Node-attached guidance that survives --exclude-integration exports.

Each mutation owns its fixture. Steps use already available public capabilities
and check real transitions rather than only a toast or a seeded value.
"""


def register(g):
    g('REQ-3-1', 'guide: public scenario prerequisites are searchable before downstream operations', r'''
    await h.signIn(page,'spec-owner');
    const repos=['spec-team-members','spec-file-create','spec-file-history','spec-issue-create','spec-pr-ready','spec-review-request'];
    for(const name of repos) await test.step(`Prerequisite repository ${name} exists with its owner`,async()=>{
      await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true});
      await search.fill(name); await search.press('Enter');
      const entry=h.link(page,name); await expect(entry).toBeVisible();
      const owner='spec-org-'+name.slice('spec-'.length);
      const row=entry.locator(`xpath=ancestor::*[contains(.,"${owner}")][1]`);
      await expect(row).toContainText(owner);
    });
    ''', requires=['REQ-1-1-2','REQ-3-1'])

    g('REQ-4-3-3', 'guide: required release branch is persisted as default without changing main', r'''
    await h.signIn(page,'spec-admin'); const address=await h.repo(page,h.fixtureRepo('guide-default-release'));
    await test.step('Select the existing branch named by the original scenario',async()=>{
      await h.settings(page,'Branches'); await h.field(page,'Default branch').selectOption({label:'release'});
      await h.button(page,'Update').click(); await h.button(page.getByRole('dialog'),'Confirm').click();
    });
    await test.step('A direct reopen uses release and main still retains its bytes',async()=>{
      await page.goto(address); await h.persisted(page,()=>expect(h.button(page,'Branch release')).toBeVisible());
      await h.button(page,'Branch release').click(); await h.option(page,'main');
      await h.link(page,'src').click(); await h.link(page,'search.ts').click();
      await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
    });
    ''', 'guide-default-release', requires=['REQ-1-1-2','REQ-4-1','REQ-4-3-1','REQ-4-3-3'])

    g('REQ-4-4', 'guide: editing creates a real commit and an old revision retains its original bytes', r'''
    await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('guide-file-edit-history'));
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
    ''', 'guide-file-edit-history', requires=['REQ-1-1-2','REQ-4-1','REQ-4-2-1','REQ-4-2-2','REQ-4-4'])

    g('REQ-5-4', 'guide: an Issue created by Write keeps comments and assignee across Maintain status changes', r'''
    const maintain=await browser.newContext(), reader=await browser.newContext();
    try {
      const manager=await maintain.newPage(), view=await reader.newPage();
      const title=h.unique('guided-issue'), comment=h.unique('guided-comment'); let address='';
      await test.step('Write creates the actual Issue and persists a discussion entry',async()=>{
        await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('guide-issue-lifecycle')); await h.link(page,'Issues').click(); await h.link(page,'New issue').click();
        await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Persist all fields through the lifecycle.'); await h.button(page,'Submit new issue').click();
        await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); address=page.url();
        await h.field(page,'Comment').fill(comment); await h.button(page,'Comment').click();
        await h.persisted(page,()=>expect(page.getByRole('article').filter({hasText:comment})).toContainText('spec-write'));
      });
      await test.step('Maintain resolves an eligible account, closes and reopens the same Issue',async()=>{
        await h.signIn(manager,'spec-maintain'); await manager.goto(address); await h.button(manager,'Assignees').click();
        await h.field(manager,'Search assignees').fill('spec-triage'); await h.option(manager,'spec-triage');
        await expect(h.metadataValue(manager,'Assignees','spec-triage').first()).toBeVisible();
        await h.button(manager,'Close issue').click(); await expect(h.text(manager,'Closed issue').first()).toBeVisible();
        await h.button(manager,'Reopen issue').click(); await h.persisted(manager,()=>expect(h.button(manager,'Close issue')).toBeVisible());
      });
      await test.step('Read sees preserved fields and activity but has no mutation controls',async()=>{
        await h.signIn(view,'spec-read'); await view.goto(address);
        await h.persisted(view,async()=>{
          await expect(view.getByRole('heading',{name:title,exact:true})).toBeVisible();
          await expect(h.text(view,'Persist all fields through the lifecycle.')).toBeVisible();
          await expect(h.text(view,comment)).toBeVisible(); await expect(h.text(view,'spec-triage').first()).toBeVisible();
          await expect(h.text(view,'Closed issue').first()).toBeVisible(); await expect(h.text(view,'Reopened issue').first()).toBeVisible();
          await expect(h.button(view,'Close issue')).toHaveCount(0); await expect(h.button(view,'Reopen issue')).toHaveCount(0);
        });
      });
    } finally { await maintain.close(); await reader.close(); }
    ''', 'guide-issue-lifecycle', requires=['REQ-1-1-2','REQ-5-1-1','REQ-5-1-2','REQ-5-2-1','REQ-5-2-3','REQ-5-3-1','REQ-5-4'])

    g('REQ-6-3-4', 'guide: submitting one review publishes only that reviewers drafts', r'''
    const other=await browser.newContext(), visitor=await browser.newContext();
    try {
      const second=await other.newPage(), publicView=await visitor.newPage();
      const published=h.unique('published-draft'), privateDraft=h.unique('private-draft'); let address='';
      await test.step('Two non-author reviewers independently retain private draft comments',async()=>{
        await h.signIn(page,'bob-reviewer'); await h.pr(page,'guide-review-publication'); await h.link(page,'Files changed').click(); address=page.url();
        await h.button(page,'Add comment').first().click(); await h.field(page,'Comment').fill(published); await h.button(page,'Start a review').click();
        await h.persisted(page,()=>expect(h.text(page,published).first()).toBeVisible());
        await h.signIn(second,'spec-maintain'); await second.goto(address);
        await expect(h.text(second,published)).toHaveCount(0);
        await h.button(second,'Add comment').first().click(); await h.field(second,'Comment').fill(privateDraft); await h.button(second,'Start a review').click();
        await h.persisted(second,()=>expect(h.text(second,privateDraft).first()).toBeVisible());
        await publicView.goto(address); await expect(h.text(publicView,published)).toHaveCount(0); await expect(h.text(publicView,privateDraft)).toHaveCount(0);
      });
      await test.step('Submitting Bob’s review publicly releases his comment and retains the other draft',async()=>{
        await h.button(page,'Review changes').click(); await h.field(page,'Summary').fill('Publish my current-commit draft');
        await page.getByRole('radio',{name:'Comment',exact:true}).check(); await h.button(page,'Submit review').click();
        await publicView.reload(); await expect(h.text(publicView,published).first()).toBeVisible(); await expect(h.text(publicView,privateDraft)).toHaveCount(0);
        await second.reload(); await expect(h.text(second,privateDraft).first()).toBeVisible(); await expect(h.text(second,'Pending review').first()).toBeVisible();
      });
    } finally { await other.close(); await visitor.close(); }
    ''', 'guide-review-publication', requires=['REQ-1-1-2','REQ-6-2-1','REQ-6-3-1','REQ-6-3-2','REQ-6-3-3','REQ-6-3-4'])
