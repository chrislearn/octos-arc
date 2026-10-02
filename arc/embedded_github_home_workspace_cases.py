"""Visible home-entry compatibility and branch-rule context from fc6db770.

These checks deliberately omit repo()/scenarioIssue()/scenarioPr() before
the first target: those helpers otherwise supply the missing navigation.
"""


def register(g):
    g('REQ-5-1-1', 'home workspace: a fresh visitor opens Issues directly and filters persisted rows', r'''
    await h.home(page); await h.link(page,'Issues').click(); await h.link(page,'Open').click();
    await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill('Improve onboarding');
    await expect(h.link(page,'Improve onboarding')).toBeVisible(); await page.reload();
    await expect(h.link(page,'Improve onboarding')).toBeVisible();
    ''')
    g('REQ-6-2-1', 'home workspace: a fresh visitor opens Pull requests directly', r'''
    await h.home(page); await h.link(page,'Pull requests').click();
    await expect(h.link(page,'Overview onboarding PR')).toBeVisible(); await h.link(page,'Open').click();
    await page.reload(); await expect(h.link(page,'Overview onboarding PR')).toBeVisible();
    ''')
    g('REQ-6-2-2', 'home workspace: a fresh sign-in can open Compare without an inserted repository step', r'''
    await h.signIn(page,'pr-contributor'); await h.link(page,'Compare').click();
    await h.chosen(page,'Base','main'); await h.choose(page,'Compare','feature-search');
    await h.button(page,'Compare changes').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
    ''')
    g('REQ-5-1-2', 'home workspace: every seeded issue entry is discoverable directly by its title', r'''
    for (const title of ['Improve onboarding','Legacy welcome text','Editable onboarding issue','Original issue title',
      'Commentable onboarding issue','Comment validation issue','Assignable onboarding issue','Labelable onboarding issue',
      'Milestone onboarding issue','Closable onboarding issue','Protected onboarding issue']) {
      await h.home(page); await expect(h.link(page,title)).toHaveCount(1); await h.link(page,title).click();
      await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    }
    ''')
    g('REQ-6-6', 'home workspace: named PR entries across repositories open their saved details', r'''
    for (const title of ['Draft onboarding update','Overview onboarding PR','Public onboarding PR','Reviewable onboarding PR',
      'Change request onboarding PR','Reviewer request onboarding PR','Closable onboarding PR','Protected onboarding PR',
      'Protection status onboarding PR','Mergeable onboarding PR','Blocked onboarding PR']) {
      await h.home(page); await expect(h.link(page,title)).toHaveCount(1); await h.link(page,title).click();
      await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    }
    ''')
    g('REQ-6-2-1', 'home workspace: changing the repository changes the collaboration destination', r'''
    await h.home(page); await h.choose(page,'Workspace repository','Acme Demo/branch-protection-demo');
    await h.link(page,'Pull requests').click(); await expect(h.link(page,'Protection status onboarding PR')).toBeVisible();
    await expect(h.link(page,'Overview onboarding PR')).toHaveCount(0);
    ''')
    g('REQ-5-1-2', 'home workspace: colliding titles remain operable with repository-specific accessible names', r'''
    await h.home(page); await expect(h.link(page,'Improve onboarding')).toHaveCount(1);
    await expect(page.getByText('Improve onboarding',{exact:true})).toHaveCount(1);
    const alternatives=page.getByRole('link',{name:/^Improve onboarding — /});
    await expect(alternatives.first()).toBeVisible(); const label=await alternatives.first().getAttribute('aria-label');
    expect(label).toMatch(/Improve onboarding — .+\/.+/);
    await alternatives.first().click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    ''')
    g('REQ-5-2-2', 'home workspace: a newly created private issue can be renamed, rediscovered, and remains private after sign-out', r'''
    const account=await h.register(page); await h.signIn(page,account.username); await h.link(page,'New repository').click();
    const repository=h.unique('workspace-private'), title=h.unique('Workspace issue'), renamed=title+' renamed';
    await h.field(page,'Repository name').fill(repository); await page.getByRole('radio',{name:'Private',exact:true}).check();
    await h.button(page,'Create repository').click(); await h.link(page,'Issues').click(); await h.link(page,'New issue').click();
    await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Created through the visible interface.');
    await h.button(page,'Submit new issue').click(); await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await h.home(page); await h.link(page,title).click(); await h.button(page,'Edit issue title').click();
    await h.field(page,'Issue title').fill(renamed); await h.button(page,'Save issue title').click();
    await h.home(page); await expect(h.link(page,renamed)).toBeVisible(); await expect(h.link(page,title)).toHaveCount(0);
    await h.signOut(page); await expect(h.link(page,renamed)).toHaveCount(0); await page.reload();
    await expect(h.link(page,renamed)).toHaveCount(0); await expect(h.link(page,repository)).toHaveCount(0);
    ''', requires=['REQ-1-1-1','REQ-1-1-2','REQ-1-2','REQ-3-2-1','REQ-5-1-1','REQ-5-1-2','REQ-5-2-1','REQ-5-2-2'])
    g('REQ-6-1', 'home workspace: a created protection rule has an unambiguous branch summary after reload', r'''
    await h.signIn(page,'repo-owner'); await h.link(page,'New repository').click();
    await h.field(page,'Repository name').fill(h.unique('protection-context'));
    await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check(); await h.button(page,'Create repository').click();
    await h.settings(page,'Branches'); await h.chosen(page,'Default branch','main');
    await h.button(page,'Add branch protection rule').click(); await h.field(page,'Branch name pattern').fill('main');
    await page.getByRole('checkbox',{name:'Require 1 approval',exact:true}).check();
    await page.getByRole('checkbox',{name:'Require status check test',exact:true}).check(); await h.action(page,['Create','Save changes']).click();
    await expect(page.getByText('main',{exact:true})).toBeVisible(); await page.reload();
    await expect(page.getByText('main',{exact:true})).toBeVisible(); await expect(h.text(page,'1 approval')).toBeVisible();
    await h.link(page,'Branches').click(); await h.chosen(page,'Default branch','main');
    ''', requires=['REQ-1-1-2','REQ-3-2-1','REQ-4-3-3','REQ-6-1'])
    g('REQ-5-1-2', 'home workspace: repository search still presents exact repository results without work-item duplicates', r'''
    await h.home(page); await expect(h.link(page,'Improve onboarding')).toBeVisible();
    const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('acme-docs'); await search.press('Enter');
    await expect(h.link(page,'acme-docs')).toHaveCount(1); await expect(h.link(page,'Improve onboarding')).toHaveCount(0);
    await h.openRepositoryResult(page,'acme-docs','Acme Demo'); await expect(h.link(page,'Code')).toBeVisible();
    ''')
