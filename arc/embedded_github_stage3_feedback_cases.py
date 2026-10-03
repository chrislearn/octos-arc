"""37fc81eb feedback: exercise the public default path and exact visible results.

Do not require global uniqueness for arbitrary words such as commit or review:
navigation, data, and historical activity can legitimately contain the same word.
"""


def register(g):
    g('REQ-6-2-2', 'stage3 feedback: identical branches explain the disabled creation action', r'''
    await h.signIn(page,'pr-contributor'); await h.repo(page); await h.link(page,'Compare').click();
    await h.choose(page,'Base','main'); await h.choose(page,'Compare','main');
    await h.button(page,'Compare changes').click();
    await h.persisted(page,async()=>{
      // Compatibility witness for the external report's /identical/i assertion.
      await expect(page.getByText(/identical/i)).toBeVisible();
      await expect(h.button(page,'Create pull request')).toBeDisabled();
    });
    ''')
    g('REQ-6-2-4', 'stage3 feedback: a fresh session can create a draft through the default comparison after an ordinary PR', r'''
    const account=await h.register(page); await h.signIn(page,account.username);
    await h.link(page,'New repository').click(); const repository=h.unique('comparison-defaults');
    await h.field(page,'Repository name').fill(repository);
    await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check();
    await h.button(page,'Create repository').click(); await expect(h.button(page,'Branch main')).toBeVisible();
    const repositoryAddress=page.url(); const branches=[h.unique('ordinary'),h.unique('draft')];
    for(const branch of branches) {
      await page.goto(repositoryAddress); await h.button(page,'Branch main').click();
      await h.field(page,'Find branch').fill(branch); await h.option(page,`Create branch: ${branch}`);
      await expect(h.button(page,`Branch ${branch}`)).toBeVisible();
      await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
      await h.field(page,'File name').fill('change.md'); await h.field(page,'File contents').fill(branch);
      await h.field(page,'Commit message').fill('Change '+branch); await h.button(page,'Commit changes').click();
      await expect(page.locator('pre')).toHaveText(branch);
    }
    await page.goto(repositoryAddress); await h.link(page,'Compare').click();
    await h.chosen(page,'Compare',branches[0]); const explicitComparison=page.url();
    await h.button(page,'Create pull request').click(); const ordinary=h.unique('Ordinary PR');
    await h.field(page,'Title').fill(ordinary); await h.button(page,'Create pull request').click();
    await expect(page.getByRole('heading',{name:ordinary,exact:true})).toBeVisible(); const ordinaryAddress=page.url();
    const fresh=await browser.newContext();
    try {
      const draftPage=await fresh.newPage(); await h.signIn(draftPage,account.username);
      await draftPage.goto(repositoryAddress); await h.link(draftPage,'Compare').click();
      // Do not manually choose the draft seed branch: that hid the original bug.
      await h.chosen(draftPage,'Compare',branches[1]);
      await h.button(draftPage,'Create draft pull request').click(); const draft=h.unique('Draft PR');
      await h.field(draftPage,'Title').fill(draft); await h.button(draftPage,'Create draft pull request').click();
      await h.persisted(draftPage,async()=>{
        await expect(draftPage.getByRole('heading',{name:draft,exact:true})).toBeVisible();
        await expect(h.text(draftPage,'Draft')).toBeVisible(); await expect(h.button(draftPage,'Merge pull request')).toBeDisabled();
      });
    } finally { await fresh.close(); }
    // Explicit user selections must stay unchanged, and duplicate creation remains rejected.
    await page.goto(explicitComparison); await h.chosen(page,'Compare',branches[0]);
    await h.button(page,'Create pull request').click(); const duplicate=h.unique('Duplicate PR');
    await h.field(page,'Title').fill(duplicate); await h.button(page,'Create pull request').click();
    await expect(page.getByText('A pull request already exists for these branches',{exact:true})).toBeVisible();
    await page.goto(ordinaryAddress); await expect(page.getByRole('heading',{name:ordinary,exact:true})).toBeVisible();
    await h.link(page,'Pull requests').click(); await expect(h.link(page,duplicate)).toHaveCount(0);
    ''', requires=['REQ-1-1-1','REQ-1-1-2','REQ-3-2-1','REQ-4-3-2','REQ-4-4','REQ-6-2-3','REQ-6-2-4'])
