"""Parent requirements and reference-navigation regressions.

Home-directory cases are explicit compatibility coverage for visible-entry
discovery, not a claim that the unavailable evaluator uses this implementation.
No helper inserts search or an organization hop into these entry checks.
"""


def register(g):
    g('REQ-3-3', 'reference navigation: cold homepage has public repository entries without a search prerequisite', r'''
    await h.home(page);
    await expect(page.getByRole('searchbox',{name:'Search',exact:true})).toHaveValue('');
    for (const name of ['acme-docs','branch-switch-demo','default-branch-demo','file-management-demo'])
      await expect(h.link(page,name)).toBeVisible();
    await expect(h.link(page,'secret-research')).toHaveCount(0);
    await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    await page.reload(); await expect(h.link(page,'Issues')).toBeVisible();
    ''')
    g('REQ-3-4', 'reference navigation: authorized home entries follow identity and sign-out permissions', r'''
    await h.signIn(page,'org-owner'); await expect(h.link(page,'secret-research')).toBeVisible();
    await h.link(page,'secret-research').click(); const address=page.url();
    await expect(page.getByRole('heading').filter({hasText:'secret-research'})).toBeVisible();
    await h.signOut(page); await expect(h.link(page,'secret-research')).toHaveCount(0);
    await page.reload(); await expect(h.link(page,'secret-research')).toHaveCount(0);
    await page.goto(address); await expect(h.link(page,'secret-research')).toHaveCount(0);
    await h.signIn(page,'org-owner'); await expect(h.link(page,'secret-research')).toBeVisible();
    await h.link(page,'secret-research').click(); await expect(page.getByRole('heading').filter({hasText:'secret-research'})).toBeVisible();
    ''', requires=['REQ-1-1-2','REQ-1-2','REQ-3-3','REQ-3-4'])
    g('REQ-3-1', 'reference navigation: search replaces the directory without duplicate repository links', r'''
    await h.home(page); await expect(h.link(page,'acme-docs')).toBeVisible();
    const search=page.getByRole('searchbox',{name:'Search',exact:true});
    await search.fill('acme-docs'); await search.press('Enter');
    await expect(h.link(page,'acme-docs')).toHaveCount(1); await h.openRepositoryResult(page,'acme-docs','Acme Demo');
    await h.home(page); await search.fill('no-match-'+h.unique('repo')); await search.press('Enter');
    await expect(h.text(page,'No results')).toBeVisible(); await expect(h.link(page,'acme-docs')).toHaveCount(0);
    await search.fill(''); await expect(h.link(page,'acme-docs')).toBeVisible();
    ''')
    g('REQ-3-2-1', 'reference navigation: a newly created personal repository is discoverable after returning home', r'''
    const account=await h.register(page); await h.signIn(page,account.username);
    await h.link(page,'New repository').click(); const name=h.unique('home-repository');
    await h.field(page,'Repository name').fill(name);
    await page.getByRole('radio',{name:'Private',exact:true}).check(); await h.button(page,'Create repository').click();
    await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible();
    await h.home(page); await expect(h.link(page,name)).toBeVisible(); await h.link(page,name).click();
    await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible();
    await h.signOut(page); await expect(h.link(page,name)).toHaveCount(0);
    ''', requires=['REQ-1-1-1','REQ-1-1-2','REQ-1-2','REQ-3-2-1'])
    g('REQ-6-2-1', 'reference navigation: repository lists can switch Issues to Pull requests and back to Code', r'''
    await h.canonicalRepo(page); await h.link(page,'Issues').click();
    await expect(h.link(page,'Improve onboarding')).toBeVisible(); await expect(h.link(page,'acme-docs')).toBeVisible();
    await h.link(page,'Pull requests').click(); await expect(h.link(page,'Overview onboarding PR')).toBeVisible();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await h.link(page,'Issues').click();
    await expect(h.link(page,'Improve onboarding')).toBeVisible(); await h.link(page,'Code').click();
    await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    ''', requires=['REQ-3-3','REQ-5-1-1','REQ-6-2-1'])
    g('REQ-5-1-2', 'reference navigation: an issue direct link and reload retain its repository and sibling navigation', r'''
    await h.canonicalRepo(page); await h.link(page,'Issues').click();
    await h.link(page,'Improve onboarding').click(); const address=page.url(); await h.home(page); await page.goto(address);
    for (let attempt=0;attempt<2;attempt++) {
      await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
      await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'Pull requests')).toBeVisible();
      if (!attempt) await page.reload();
    }
    await h.link(page,'acme-docs').click(); await expect(h.link(page,'Code')).toBeVisible();
    ''')
    g('REQ-6-3-1', 'reference navigation: PR context does not duplicate its Commits tab', r'''
    await h.canonicalRepo(page); await h.link(page,'Pull requests').click();
    await h.link(page,'Overview onboarding PR').click(); await page.reload();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'Commits')).toHaveCount(1);
    await h.link(page,'Commits').click(); await expect(h.link(page,'Conversation')).toBeVisible();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await h.link(page,'Issues').click();
    await expect(h.link(page,'Improve onboarding')).toBeVisible();
    ''')
    g('REQ-4-2-2', 'reference navigation: commit detail retains repository context and returns to code after reload', r'''
    await h.canonicalRepo(page); await h.link(page,'Commits').click();
    await h.link(page,'Document search flow').click(); await page.reload();
    await expect(page.getByRole('heading',{name:'Document search flow',exact:true})).toBeVisible();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(page.getByText(/(?:Commit|Revision)\s+\S+/).first()).toBeVisible();
    await h.link(page,'Code').click(); await expect(h.link(page,'README.md')).toBeVisible();
    ''')
    g('REQ-4-4', 'reference navigation: file editor displays repository and selected branch across reload', r'''
    await h.signIn(page,'file-contributor'); await h.repo(page,'file-management-demo');
    const branch='context/'+h.unique('branch'); await h.button(page,'Branch main').click();
    await h.field(page,'Find branch').fill(branch); await page.getByRole('option',{name:'Create branch: '+branch,exact:true}).click();
    await expect(h.button(page,'Branch '+branch)).toBeVisible();
    await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
    await expect(h.field(page,'File name')).toBeVisible(); await expect(h.link(page,'file-management-demo')).toBeVisible();
    await expect(h.renderedSubstring(page,'Branch '+branch).first()).toBeVisible(); await page.reload();
    await expect(h.field(page,'File name')).toBeVisible(); await expect(h.renderedSubstring(page,'Branch '+branch).first()).toBeVisible();
    await h.link(page,'Code').click(); await expect(h.button(page,'Branch '+branch)).toBeVisible();
    ''', requires=['REQ-1-1-2','REQ-3-3','REQ-4-3-2','REQ-4-4'])
    g('REQ-4-1', 'reference navigation: file pages retain repository tabs and one file-specific Commits entry', r'''
    await h.canonicalRepo(page); await h.link(page,'README.md').click();
    await expect(h.link(page,'Issues')).toBeVisible(); await expect(h.link(page,'Commits')).toHaveCount(1);
    await h.link(page,'Commits').click(); await expect(h.link(page,'Document search flow')).toBeVisible();
    await h.link(page,'Code').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    ''')
    g('REQ-6-2-2', 'reference navigation: comparison keeps repository identity and permits returning to the PR list', r'''
    await h.signIn(page,'pr-author'); await h.canonicalRepo(page);
    await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click();
    await h.chosen(page,'Base','main'); await expect(h.link(page,'acme-docs')).toBeVisible();
    await h.choose(page,'Compare','feature-search'); await h.button(page,'Compare changes').click();
    await expect(h.text(page,'src/search.ts')).toBeVisible(); await page.reload();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await h.link(page,'Pull requests').click();
    await expect(h.link(page,'Overview onboarding PR')).toBeVisible();
    ''')
    g('REQ-4-3-3', 'reference navigation: branch settings retain the repository navigation after direct reload', r'''
    await h.signIn(page,'default-branch-admin'); await h.repo(page,'default-branch-demo');
    await h.link(page,'Settings').click(); await h.link(page,'Branches').click(); await page.reload();
    await expect(page.getByRole('combobox',{name:'Default branch',exact:true})).toBeVisible();
    await expect(h.link(page,'default-branch-demo')).toBeVisible(); await h.link(page,'Code').click();
    await expect(page.getByRole('heading').filter({hasText:'default-branch-demo'})).toBeVisible();
    ''')
