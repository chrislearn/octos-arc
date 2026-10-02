"""UI navigation regressions prompted by visible self-test 6fcdca72 failures.

The immediate visibility checks are explicit navigation-readiness compatibility
checks. They supplement the business requirements; they do not reconstruct the
unavailable official navigation helper or impose private API knowledge.
"""


def register(g):
    g('REQ-1-1-3', 'navigation readiness exposes recovery fields when the entry click completes', r'''
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Forgot password').click();
    expect(await h.field(page,'Email').isVisible(),'the recovery destination must be committed after clicking its entry').toBe(true);
    for (const label of ['Verification code','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
    await expect(h.text(page,'123456')).toBeVisible();
    await h.field(page,'Email').fill('recovery-visibility@example.test');
    await expect(h.field(page,'Email')).toHaveValue('recovery-visibility@example.test');
    ''')
    g('REQ-1-3', 'navigation readiness keeps password settings available across same-session navigation', r'''
    await h.signIn(page,'password-change-invalid'); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click();
    expect(await h.link(page,'Password and authentication').isVisible(),'same-session refresh must not hide the settings navigation').toBe(true);
    await h.link(page,'Password and authentication').click();
    await expect(h.field(page,'Current password')).toBeVisible();
    await expect(h.button(page,'Account menu')).toBeVisible();
    ''')
    g('REQ-2-1-2', 'navigation readiness keeps New organization available after the account menu entry', r'''
    await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    expect(await h.link(page,'New organization').isVisible(),'organization creation must remain available during the list refresh').toBe(true);
    await h.link(page,'New organization').click();
    for (const label of ['Organization name','Display name']) await expect(h.field(page,label)).toBeVisible();
    ''')
    g('REQ-2-1-1', 'navigation readiness retains organization navigation while repository data loads', r'''
    await h.home(page); await h.link(page,'Acme Demo').click();
    expect(await h.link(page,'Repositories').isVisible(),'organization navigation must not wait for repository data').toBe(true);
    for (const label of ['People','Teams']) await expect(h.link(page,label)).toBeVisible();
    await h.link(page,'Repositories').click(); await h.link(page,'acme-docs').click();
    await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    ''')
    g('REQ-1-1-2', 'account menu occupies the upper-right area and exposes readable links', r'''
    await page.setViewportSize({width:1280,height:720}); await h.signIn(page,'alice-dev');
    const menu=h.button(page,'Account menu'); const bounds=await menu.boundingBox();
    expect(bounds).not.toBeNull(); expect(bounds.x+bounds.width/2).toBeGreaterThan(640);
    expect(bounds.y+bounds.height/2).toBeLessThan(360);
    await menu.click(); await expect(h.link(page,'Your organizations')).toBeVisible();
    await expect(h.link(page,'Settings')).toBeVisible(); await expect(h.link(page,'Sign out')).toBeVisible();
    ''')
    g('REQ-2-2-3', 'member roles are associated with each account when multiple members share Member role', r'''
    await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await h.link(page,'New organization').click(); const organization=h.unique('member-roles');
    await h.field(page,'Organization name').fill(organization); await h.field(page,'Display name').fill(organization);
    await h.button(page,'Create organization').click(); await h.link(page,'People').click();
    for (const name of ['bob-reviewer','org-member']) {
      await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill(name);
      await h.choose(page,'Role','Member'); await h.button(page,'Add member').click();
      await expect(h.text(page,name)).toBeVisible();
    }
    await h.persisted(page,async()=>{
      for (const name of ['bob-reviewer','org-member']) {
        const member=page.getByRole('listitem').filter({has:h.text(page,name)});
        await expect(member).toHaveCount(1); await expect(h.text(member,'Member')).toBeVisible();
      }
      await expect(h.text(page,'Pending invitation')).toHaveCount(0);
    });
    ''', requires=['REQ-2-2-3','REQ-2-1-2'])
