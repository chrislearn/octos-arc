"""Source-grounded regressions for the three-stage requirements audit.

Keep exact accessible names and repository identity throughout the public flow.
The contradictory Stage1 organization scenario is tested against its atomic
prose, without accepting a display name as an identifier.
"""

def register(g):
    g('REQ-3-1', 'personal repository results expose exact names separately from owner metadata', r'''
    for (const [name, owner] of [['acme-docs-personal','alice-dev'], ['acme-docs-fork','alice-dev'], ['acme-docs-fork','fork-user']]) {
      await h.home(page);
      const search=page.getByRole('searchbox',{name:'Search',exact:true});
      await search.fill(name); await search.press('Enter');
      await expect(h.link(page,`${owner}/${name}`)).toHaveCount(0);
      await h.openRepositoryResult(page,name,owner);
      await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:owner}).filter({hasText:name})).toBeVisible());
    }
    ''')

    g('REQ-2-1-2', 'display names cannot replace identifiers and independent validation errors persist', r'''
    await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click();
    await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click();
    await h.field(page,'Organization name').fill('Acme Demo'); await h.button(page,'Create organization').click();
    await expect(h.text(page,'Organization name format is invalid')).toBeVisible();
    await expect(h.text(page,'Display name is required')).toBeVisible();
    await expect(h.text(page,'Organization name already exists')).toHaveCount(0);
    await expect(h.field(page,'Organization name')).toHaveValue('Acme Demo');
    await h.field(page,'Organization name').fill('acme-demo'); await h.button(page,'Create organization').click();
    await expect(h.text(page,'Organization name already exists')).toBeVisible();
    await expect(h.text(page,'Display name is required')).toBeVisible();
    await page.reload(); await h.field(page,'Organization name').fill(h.unique('pw-org'));
    await h.field(page,'Display name').fill('   '); await h.button(page,'Create organization').click();
    await expect(h.text(page,'Display name is required')).toBeVisible();
    await expect(h.button(page,'Create organization')).toBeVisible();
    ''')

    g('REQ-4-3-2', 'legal slash branch survives creation reload switching and nested file browsing', r'''
    await h.signIn(page,'branch-contributor'); await h.repo(page,'branch-switch-demo');
    const branch=`audit/${h.unique('slash')}`;
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill(branch);
    await page.getByRole('option',{name:`Create branch: ${branch}`,exact:true}).click();
    await h.persisted(page,()=>expect(h.button(page,`Branch ${branch}`)).toBeVisible());
    await h.button(page,`Branch ${branch}`).click(); await h.option(page,'main');
    await expect(h.button(page,'Branch main')).toBeVisible();
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill(branch); await h.option(page,branch);
    await h.persisted(page,()=>expect(h.button(page,`Branch ${branch}`)).toBeVisible());
    await h.link(page,'src').click(); await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
    await h.link(page,'search.ts').click();
    await h.persisted(page,async()=>{
      await expect(h.text(page,'export const search = "search flow";')).toBeVisible();
      await expect(h.renderedSubstring(page,`Branch ${branch}`).first()).toBeVisible();
    });
    ''', requires=['REQ-4-3-2','REQ-4-3-1','REQ-4-1'])

    g('REQ-4-4', 'slash branch web writes edits and history remain isolated from main', r'''
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
    ''', requires=['REQ-4-4','REQ-4-3-2','REQ-4-3-1','REQ-4-1','REQ-4-2-1'])

    g('REQ-6-2-2', 'comparison controls have the exact Base and Compare accessible names', r'''
    await h.signIn(page,'pr-contributor'); await h.canonicalRepo(page);
    await h.link(page,'Pull requests').click(); await h.link(page,'New pull request').click();
    for (const name of ['Base','Compare']) {
      await expect(page.getByRole('combobox',{name,exact:true})).toHaveCount(1);
      await expect(page.getByRole('combobox',{name:name.toLowerCase(),exact:true})).toHaveCount(0);
    }
    await h.choose(page,'Base','main'); await h.choose(page,'Compare','feature-search');
    await h.button(page,'Compare changes').click(); await expect(h.text(page,'src/search.ts')).toBeVisible();
    ''')

    g('REQ-6-3-4', 'Request changes accepts an omitted optional summary and persists the decision', r'''
    await h.signIn(page,'bob-reviewer'); await h.pr(page,'review-optional-summary');
    await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
    await expect(await h.reviewSummary(page)).toHaveValue('');
    await page.getByRole('radio',{name:'Request changes',exact:true}).check(); await h.button(page,'Submit review').click();
    await h.persisted(page,async()=>{
      await expect(h.text(page,'Changes requested').first()).toBeVisible();
      await expect(h.text(page,'Summary is required for Request changes')).toHaveCount(0);
      await expect(h.button(page,'Merge pull request')).toBeDisabled();
    });
    ''', 'review-optional-summary')

    g('REQ-6-3-1', 'global search file issue and PR navigation share the prescribed organization repository', r'''
    const address=await h.repo(page);
    await expect(page.getByRole('heading').filter({hasText:'Acme Demo'}).filter({hasText:'acme-docs'})).toBeVisible();
    await h.link(page,'src').click(); await h.link(page,'README.md').click();
    await h.persisted(page,()=>expect(h.text(page,'Document search flow')).toBeVisible());
    await page.goto(address); await h.link(page,'Issues').click(); await h.link(page,'Improve onboarding').click();
    await h.persisted(page,()=>expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible());
    await page.goto(address); await h.link(page,'Pull requests').click(); await h.link(page,'Overview onboarding PR').click();
    await h.link(page,'Commits').click(); await expect(h.renderedSubstring(page,'Implement search flow').first()).toBeVisible();
    await h.link(page,'Files changed').click();
    await h.persisted(page,async()=>{
      await expect(page.getByRole('heading',{name:'Overview onboarding PR',exact:true})).toBeVisible();
      await expect(h.text(page,'src/search.ts')).toBeVisible();
    });
    ''', requires=['REQ-6-3-1','REQ-3-1','REQ-3-3','REQ-4-1','REQ-5-1-2'])
