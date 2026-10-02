"""Additional source-grounded cases from the full-requirements audit.

Never invent a private endpoint, reaction type, author-filter field name, or
storage layout where the source provides no portable interaction contract.
"""


def register(g):
    g('REQ-4-2-1', 'branch history keeps newest-first order and file history excludes unrelated commits', r'''
    const address=await h.repo(page); await h.link(page,'Commits').click();
    const history=await h.historyLinks(page);
    expect(history.indexOf('Document search flow')).toBeLessThan(history.indexOf('Initialize empty repository'));
    await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
    await page.goto(address); await h.link(page,'README.md').click(); await h.link(page,'Commits').click();
    await h.persisted(page,async()=>{
      await expect(h.link(page,'Document search flow')).toBeVisible();
      await expect(h.link(page,'Initialize empty repository')).toHaveCount(0);
    });
    ''')

    for account in ['spec-read', 'spec-triage']:
        g('REQ-4-4', account + ' cannot commit files on a readable repository', f'''
        await h.signIn(page,'{account}'); const address=await h.repo(page,h.fixtureRepo('file-denied-{account}'));
        await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address); await expect(h.link(page,'README.md')).toBeVisible();
        const name=h.unique('denied')+'.md',add=h.button(page,'Add file');
        if(await add.count() && await add.isVisible() && await add.isEnabled()) {{
          await add.click(); const create=page.getByRole('menuitem',{{name:'Create new file',exact:true}});
          if(await create.count() && await create.isVisible() && await create.isEnabled()) {{
            await create.click();
            for(const [label,value] of [['File name',name],['File contents','Must not be saved'],['Commit message','Attempt unauthorized write']]) {{
              const field=h.field(page,label); if(await field.count() && await field.isEditable()) await field.fill(value);
            }}
            const commit=h.button(page,'Commit changes'); if(await commit.count() && await commit.isEnabled()) await h.attemptSubmission(page,commit);
          }}
        }}
        await page.goto(address); await expect(h.link(page,name)).toHaveCount(0); await h.link(page,'Commits').click();
        await expect.poll(()=>h.historyLinks(page)).toEqual(history); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
        ''', 'file-denied-' + account, requires=['REQ-4-4', 'REQ-4-2-1'])

    for suffix, path in [('absolute', '/invalid.md'), ('existing-file', 'README.md'), ('directory', 'src')]:
        g('REQ-4-4', suffix + ' file path is rejected without advancing history', f'''
        await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-path-{suffix}'));
        await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address);
        await h.button(page,'Add file').click(); await page.getByRole('menuitem',{{name:'Create new file',exact:true}}).click();
        await h.field(page,'File name').fill('{path}'); await h.field(page,'File contents').fill('Rejected replacement');
        await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
        await expect(h.containsValue(page,'Invalid file path').first()).toBeVisible();
        await page.goto(address); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
        await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
        ''', 'file-path-' + suffix, requires=['REQ-4-4', 'REQ-4-2-1'])

    g('REQ-4-4', 'overlong trimmed commit message leaves files and history unchanged', r'''
    await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-message-too-long'));
    await h.link(page,'Commits').click(); const history=await h.historyLinks(page); await page.goto(address);
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    const name=h.unique('rejected')+'.md'; await h.field(page,'File name').fill(name);
    await h.field(page,'File contents').fill('Must not be committed'); await h.field(page,'Commit message').fill('x'.repeat(73));
    await h.button(page,'Commit changes').click(); await expect(h.field(page,'File name')).toBeVisible();
    await page.goto(address); await expect(h.link(page,name)).toHaveCount(0); await h.link(page,'Commits').click();
    await expect.poll(()=>h.historyLinks(page)).toEqual(history); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(history);
    ''', 'file-message-too-long', requires=['REQ-4-4', 'REQ-4-2-1'])

    for account in ['spec-read', 'spec-triage']:
        g('REQ-5-2-3', account + ' can read discussion but cannot publish a comment', f'''
        await h.signIn(page,'{account}'); await h.issue(page,'issue-comment-denied-{account}');
        await h.unavailable(page,'Comment'); await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
        ''', 'issue-comment-denied-' + account)

    # PR navigation is a later capability than issue metadata. Retain the source
    # integration and let complete_node_coverage attach it to the last node.
    g('REQ-5-3-3', 'PR milestone toggles without cross-repository choices or deleting history', r'''
    await h.signIn(page,'spec-maintain'); await h.repo(page,'foreign-milestone-repo'); await h.pr(page,'pr-milestone');
    await h.button(page,'Milestone').click(); await expect(page.getByRole('option',{name:'foreign-milestone',exact:true})).toHaveCount(0);
    await h.option(page,'v1.0'); await h.persisted(page,()=>expect(h.metadataValue(page,'Milestone','v1.0').first()).toBeVisible());
    await h.button(page,'Milestone').click(); await h.option(page,'None');
    await h.persisted(page,()=>expect(h.metadataValue(page,'Milestone','v1.0')).toHaveCount(0));
    await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();
    const discussion=page.getByRole('article').filter({hasText:'Please review this update.'});
    await expect(discussion).toHaveCount(1); await expect(discussion).toContainText('Please review this update.');
    await expect(discussion).toContainText('spec-write');
    ''', 'pr-milestone', file='INTEGRATION-pr-planning', requires=['REQ-5-3-3', 'REQ-6-3-1'])

    for account in ['spec-read', 'spec-write']:
        g('REQ-5-3-3', account + ' cannot change a PR milestone', f'''
        await h.signIn(page,'{account}'); await h.pr(page,'pr-milestone-denied-{account}');
        await h.unavailable(page,'Milestone'); await h.persisted(page,()=>expect(page.getByRole('heading',{{name:'Improve onboarding',exact:true}})).toBeVisible());
        ''', 'pr-milestone-denied-' + account, file='INTEGRATION-pr-planning', requires=['REQ-5-3-3', 'REQ-6-3-1'])

    for suffix, account, status in [('author', 'spec-write', 'Open'), ('draft', 'bob-reviewer', 'Draft'), ('read', 'spec-read', 'Open'), ('triage', 'spec-triage', 'Open')]:
        g('REQ-6-3-4', suffix + ' cannot persist a review decision', f'''
        await h.signIn(page,'{account}'); await h.pr(page,'review-denied-{suffix}');
        await h.link(page,'Files changed').click(); await expect(h.text(page,'{'README.md' if suffix == 'draft' else 'src/search.ts'}')).toBeVisible();
        const address=page.url(),summary=h.unique('forbidden-review');
        const open=h.button(page,'Review changes');
        if(await open.count() && await open.isVisible() && await open.isEnabled()) {{
          await open.click(); const decision=page.getByRole('radio',{{name:'Approve',exact:true}});
          await decision.waitFor({{state:'visible',timeout:2000}}).catch(error=>{{ if(error.name!=='TimeoutError') throw error; }});
          if(await decision.count() && await decision.isVisible() && await decision.isEnabled()) {{
            await decision.check(); if(await h.field(page,'Summary').count()) await h.field(page,'Summary').fill(summary);
            const submit=h.button(page,'Submit review'); if(await submit.count() && await submit.isEnabled()) await h.attemptSubmission(page,submit);
          }}
        }}
        await page.goto(address); await h.persisted(page,async()=>{{
          await expect(page.getByRole('heading',{{name:'Improve onboarding',exact:true}})).toBeVisible();
          await expect(h.text(page,'{status}').first()).toBeVisible();
          await expect(h.containsValue(page,summary)).toHaveCount(0); await expect(h.text(page,'Approved')).toHaveCount(0);
        }});
        ''', 'review-denied-' + suffix)

    for suffix, account in [('write', 'spec-write'), ('read', 'spec-read'), ('triage', 'spec-triage')]:
        g('REQ-6-5', suffix + ' cannot merge or change the base branch', f'''
        await h.signIn(page,'{account}'); await h.pr(page,'merge-denied-{suffix}'); const address=page.url();
        await expect(h.text(page,'Open').first()).toBeVisible();
        const merge=h.button(page,'Merge pull request');
        if(await merge.count() && await merge.isVisible() && await merge.isEnabled()) {{
          await merge.click(); const confirm=h.button(page,'Confirm merge');
          await confirm.waitFor({{state:'visible',timeout:2000}}).catch(error=>{{ if(error.name!=='TimeoutError') throw error; }});
          if(await confirm.count() && await confirm.isVisible() && await confirm.isEnabled()) await h.attemptSubmission(page,confirm);
        }}
        await page.goto(address); await h.persisted(page,async()=>{{ await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Merged')).toHaveCount(0); }});
        await h.repo(page,h.fixtureRepo('merge-denied-{suffix}')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
        await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
        ''', 'merge-denied-' + suffix, requires=['REQ-6-5', 'REQ-4-1'])

    g('REQ-6-5', 'a failed required check blocks an otherwise approved PR', r'''
    await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-check-failure');
    await h.persisted(page,async()=>{ await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeDisabled(); });
    await h.repo(page,h.fixtureRepo('merge-check-failure')); await h.link(page,'src').click(); await h.link(page,'search.ts').click();
    await h.persisted(page,()=>expect(h.text(page,'export const search = "search flow";')).toBeVisible());
    ''', 'merge-check-failure', requires=['REQ-6-5', 'REQ-4-1'])

    g('REQ-6-2-1', 'Open Draft Closed and actual Merged status filters isolate records and retain other PRs', r'''
    await h.signIn(page,'spec-maintain'); const address=await h.repo(page,h.fixtureRepo('pr-filter-lifecycle'));
    await h.link(page,'Pull requests').click(); const list=page.url();
    for(const [status,title] of [['Open','Improve onboarding'],['Draft','Draft onboarding update'],['Closed','Fix search']]) {
      await h.filterStatus(page,status); await h.persisted(page,async()=>{
        await expect(h.link(page,title)).toBeVisible();
        for(const other of ['Improve onboarding','Draft onboarding update','Fix search'].filter(name=>name!==title)) await expect(h.link(page,other)).toHaveCount(0);
      });
    }
    await h.filterStatus(page,'Open'); await h.link(page,'Improve onboarding').click();
    await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click(); await expect(h.text(page,'Merged').first()).toBeVisible();
    await page.goto(list); await h.filterStatus(page,'Merged');
    await h.persisted(page,async()=>{ await expect(h.link(page,'Improve onboarding')).toBeVisible(); await expect(h.link(page,'Fix search')).toHaveCount(0); await expect(h.link(page,'Draft onboarding update')).toHaveCount(0); });
    await h.filterStatus(page,'Draft'); await expect(h.link(page,'Draft onboarding update')).toBeVisible();
    await h.filterStatus(page,'Closed'); await expect(h.link(page,'Fix search')).toBeVisible();
    ''', 'pr-filter-lifecycle', file='INTEGRATION-pr-filters', requires=['REQ-6-2-1','REQ-6-2-4','REQ-6-3-1','REQ-6-5'])
