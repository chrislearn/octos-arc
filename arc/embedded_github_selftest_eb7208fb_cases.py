"""Cross-stage navigation regressions observed in the October 2 self-tests.

Immediate checks are compatibility witnesses for discovery/readiness, not a
reconstruction of the unavailable evaluator helper or a ban on async data.
"""


def register(g):
    g('REQ-2-1-1', 'eb7208fb compatibility: cold public home exposes the organization and its public repository', r'''
    await h.home(page);
    expect(await h.link(page,'Acme Demo').isVisible(),'public discovery must not depend on a session round trip').toBe(true);
    await h.link(page,'Acme Demo').click(); await h.link(page,'Repositories').click();
    expect(await h.link(page,'acme-docs').isVisible()).toBe(true);
    await expect(h.link(page,'secret-research')).toHaveCount(0);
    await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    ''')
    g('REQ-2-1-2', 'eb7208fb compatibility: signed-in home and account directory expose the same organization immediately', r'''
    await h.signIn(page,'org-owner');
    expect(await h.link(page,'Acme Demo').isVisible()).toBe(true);
    await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    expect(await h.link(page,'Acme Demo').isVisible(),'account menu and its organization directory must be ready together').toBe(true);
    await h.link(page,'Acme Demo').click(); await expect(h.link(page,'Repositories')).toBeVisible();
    ''')
    g('REQ-2-2-2', 'eb7208fb compatibility: named team navigation keeps the settings entry usable', r'''
    await h.signIn(page,'team-maintainer'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click();
    expect(await h.link(page,'Settings').isVisible(),'team detail must retain its settings navigation while data loads').toBe(true);
    await h.link(page,'Settings').click(); await h.chosen(page,'Parent team','platform-team');
    ''')
    g('REQ-2-3', 'eb7208fb compatibility: repository access is discoverable through the complete organization chain', r'''
    await h.signIn(page,'repo-admin');
    for (const name of ['Acme Demo','acme-docs','Settings','Manage access']) {
      expect(await h.link(page,name).isVisible(),`next navigation target ${name}`).toBe(true);
      await h.link(page,name).click();
    }
    await expect(h.button(page,'Add people or teams')).toBeVisible();
    ''')
    g('REQ-2-1-1', 'eb7208fb compatibility: sign-out retains public discovery without restoring private repository entries', r'''
    await h.signIn(page,'org-owner'); await h.link(page,'Acme Demo').click();
    await expect(h.link(page,'secret-research')).toBeVisible();
    await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
    expect(await h.link(page,'Acme Demo').isVisible()).toBe(true);
    await h.link(page,'Acme Demo').click(); await h.link(page,'Repositories').click();
    await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
    await page.reload(); await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
    ''', requires=['REQ-2-1-1','REQ-1-2'])
    g('REQ-2-3', 'eb7208fb compatibility: reloading repository settings retains the access navigation entry', r'''
    await h.signIn(page,'repo-admin'); await h.canonicalRepo(page); await h.link(page,'Settings').click();
    await expect(h.link(page,'Manage access')).toBeVisible(); await page.reload();
    expect(await h.link(page,'Manage access').isVisible()).toBe(true);
    await h.link(page,'Manage access').click(); await expect(h.button(page,'Add people or teams')).toBeVisible();
    ''')
    g('REQ-3-1', '7aa2e514 compatibility: homepage search remains in the initial viewport beside a populated organization directory', r'''
    await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true});
    await expect(search).toBeInViewport(); await search.fill('acme-docs'); await search.press('Enter');
    await h.openRepositoryResult(page,'acme-docs','Acme Demo');
    await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    ''')
    g('REQ-3-3', '7aa2e514 compatibility: public organization directory discovers each named stage 2 repository', r'''
    for (const name of ['acme-docs','branch-switch-demo','default-branch-demo','file-management-demo']) {
      await h.home(page); expect(await h.link(page,'Acme Demo').isVisible()).toBe(true);
      await h.link(page,'Acme Demo').click(); expect(await h.link(page,name).isVisible()).toBe(true);
      await h.link(page,name).click(); await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible();
    }
    ''')
    g('REQ-4-2-2', '7aa2e514 compatibility: the public repository chain exposes its named commit before opening the diff', r'''
    await h.home(page); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
    expect(await h.link(page,'Commits').isVisible()).toBe(true); await h.link(page,'Commits').click();
    expect(await h.link(page,'Document search flow').isVisible()).toBe(true);
    await h.link(page,'Document search flow').click(); await expect(h.renderedSubstring(page,'Document search flow').first()).toBeVisible();
    await expect(h.text(page,'src/search.ts').first()).toBeVisible();
    ''')
    g('REQ-5-1-2', '81c7432a compatibility: issue navigation and named discussion entries are ready along the public chain', r'''
    await h.home(page); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
    expect(await h.link(page,'Issues').isVisible()).toBe(true); await h.link(page,'Issues').click();
    for (const name of ['Improve onboarding','Editable onboarding issue','Original issue title','Commentable onboarding issue',
      'Comment validation issue','Assignable onboarding issue','Labelable onboarding issue','Milestone onboarding issue',
      'Closable onboarding issue','Protected onboarding issue']) expect(await h.link(page,name).isVisible(),name).toBe(true);
    await h.link(page,'Improve onboarding').click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible();
    ''')
    g('REQ-6-2-2', '81c7432a compatibility: pull request and comparison navigation remain discoverable before detail data', r'''
    await h.signIn(page,'pr-author'); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
    expect(await h.link(page,'Pull requests').isVisible()).toBe(true);
    expect(await h.link(page,'Compare').isVisible()).toBe(true);
    await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click();
    await expect(page.getByRole('combobox',{name:'Base',exact:true})).toBeVisible();
    await expect(page.getByRole('combobox',{name:'Compare',exact:true})).toBeVisible();
    ''')
    g('REQ-6-3-1', '81c7432a compatibility: named pull requests are ready when entering their list', r'''
    await h.home(page); await h.link(page,'Acme Demo').click(); await h.link(page,'acme-docs').click();
    await h.link(page,'Pull requests').click();
    for (const name of ['Draft onboarding update','Overview onboarding PR','Public onboarding PR','Reviewable onboarding PR',
      'Change request onboarding PR','Reviewer request onboarding PR','Closable onboarding PR','Protected onboarding PR'])
      expect(await h.link(page,name).isVisible(),name).toBe(true);
    await h.link(page,'Overview onboarding PR').click(); await expect(page.getByRole('heading',{name:'Overview onboarding PR',exact:true})).toBeVisible();
    ''')
    g('REQ-6-5', '81c7432a compatibility: protection and merge repositories expose their named pull requests', r'''
    for (const [repository,titles] of [
      ['branch-protection-demo',['Protection status onboarding PR']],
      ['merge-onboarding-demo',['Mergeable onboarding PR','Blocked onboarding PR']]
    ] as const) {
      await h.home(page); await h.link(page,'Acme Demo').click();
      expect(await h.link(page,repository).isVisible()).toBe(true); await h.link(page,repository).click();
      expect(await h.link(page,'Pull requests').isVisible()).toBe(true); await h.link(page,'Pull requests').click();
      for (const title of titles) expect(await h.link(page,title).isVisible(),title).toBe(true);
      await h.link(page,titles[0]).click(); await expect(page.getByRole('heading',{name:titles[0],exact:true})).toBeVisible();
    }
    ''')

    g('REQ-3-4', '7aa2e514 compatibility: authorized accounts discover the visibility repository through the organization entry', r'''
    for (const account of ['visibility-admin','collaborator']) {
      await h.signIn(page,account); await h.link(page,'Acme Demo').click();
      expect(await h.link(page,'visibility-demo').isVisible()).toBe(true);
      await h.link(page,'visibility-demo').click(); await expect(page.getByRole('heading').filter({hasText:'visibility-demo'})).toBeVisible();
      await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
    }
    ''')
