"""UI regressions for the visible 56bf6006 Stage 1 self-test failures.

These are reconstructed requirement checks, not copies of unavailable official
tests. Mutable extra cases create their own organizations through the public UI.
"""


def register(g):
    g('REQ-1-1-3', 'selftest recovery opens one labeled form with a code before email submission', r'''
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Forgot password').click();
    await expect(h.text(page,'123456')).toBeVisible();
    for (const label of ['Email','Verification code','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
    for (const email of ['recovery-visibility@example.test','unknown@example.test']) {
      await h.field(page,'Email').fill(email);
      await expect(h.text(page,'123456')).toBeVisible(); await expect(h.field(page,'Email')).toHaveValue(email);
      await h.maskedPasswords(page,['New password','Confirm password']);
    }
    ''')
    g('REQ-1-1-3', 'selftest recovery has one success message and new credentials sign in without a reset helper', r'''
    const {username,email}=await h.register(page);
    await h.link(page,'Forgot password').click(); await h.field(page,'Email').fill(email);
    await h.field(page,'Verification code').fill('123456');
    await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!');
    await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toBeVisible();
    await expect(h.link(page,'Sign in')).toHaveCount(1); await h.link(page,'Sign in').click();
    await h.field(page,'Username or email').fill(email); await h.field(page,'Password').fill('Replacement-password-456!');
    await h.button(page,'Sign in').click(); await expect(h.text(page,username)).toBeVisible();
    await page.reload(); await expect(h.text(page,username)).toBeVisible();
    ''', requires=['REQ-1-1-3','REQ-1-1-1','REQ-1-1-2'])
    g('REQ-2-2-3', 'selftest Sign in remains a link on the sign-in page and after protected organization reentry', r'''
    await h.home(page); await h.link(page,'Sign in').click();
    await expect(h.link(page,'Sign in')).toHaveCount(1); await expect(h.link(page,'Sign in')).toBeVisible();
    await expect(h.button(page,'Sign in')).toBeVisible();
    await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await expect(h.link(page,'Acme Demo')).toBeVisible(); const listAddress=page.url();
    await h.link(page,'Acme Demo').click(); await h.link(page,'People').click();
    await expect(h.text(page,'protected-member')).toBeVisible(); const peopleAddress=page.url();
    await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click();
    await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible(); const teamAddress=page.url();
    await h.signOut(page);
    for (const address of [listAddress,peopleAddress,teamAddress]) {
      await page.goto(address); await expect(h.link(page,'Sign in')).toBeVisible();
      await expect(h.button(page,'Account menu')).toHaveCount(0);
      await expect(h.text(page,'protected-member')).toHaveCount(0);
    }
    ''', requires=['REQ-1-2','REQ-2-1-2','REQ-2-2-1','REQ-2-2-3'])
    g('REQ-1-3', 'selftest account menu keyboard navigation reaches password settings without reloading', r'''
    await h.signIn(page,'password-change-invalid');
    await h.button(page,'Account menu').press('ArrowDown');
    const settings=h.link(page,'Settings');
    for (let step=0;step<10 && !await settings.evaluate(element=>element===document.activeElement);step++) await page.keyboard.press('ArrowDown');
    await expect(settings).toBeFocused();
    await page.keyboard.press('Enter'); await h.link(page,'Password and authentication').click();
    for (const label of ['Current password','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
    await expect(h.button(page,'Account menu')).toHaveCount(1);
    ''')
    g('REQ-2-2-2', 'selftest keyboard organization entry reaches teams without a reload or search helper', r'''
    await h.signIn(page,'org-owner'); await h.button(page,'Account menu').press('ArrowDown');
    const organizations=h.link(page,'Your organizations');
    for (let step=0;step<10 && !await organizations.evaluate(element=>element===document.activeElement);step++) await page.keyboard.press('ArrowDown');
    await expect(organizations).toBeFocused(); await page.keyboard.press('Enter');
    await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click();
    await expect(h.link(page,'New team')).toBeVisible(); await h.link(page,'frontend-team').click();
    await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible();
    await h.link(page,'Settings').click(); await expect(h.field(page,'Parent team')).toBeVisible();
    ''', requires=['REQ-2-2-1','REQ-2-1-2','REQ-2-2-2'])
    g('REQ-2-3', 'selftest organization repository route reaches access settings immediately after login', r'''
    await h.signIn(page,'repo-admin'); await h.link(page,'Acme Demo').click();
    await h.link(page,'Repositories').click(); await h.link(page,'acme-docs').click();
    await h.link(page,'Settings').click(); await h.link(page,'Manage access').click();
    await expect(h.button(page,'Add people or teams')).toBeVisible();
    await expect(page.getByRole('row',{name:/access-role-team/})).toHaveCount(1);
    ''', requires=['REQ-2-3','REQ-2-1-1'])

    # Each test owns this created organization. A removal in another spec cannot
    # change the duplicate-member precondition or cause an accidental re-add.
    own_org = r'''
    await h.signIn(page,'org-owner'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await h.link(page,'New organization').click(); const organization=h.unique('member-ui');
    await h.field(page,'Organization name').fill(organization); await h.field(page,'Display name').fill(organization);
    await h.button(page,'Create organization').click(); await h.link(page,'People').click();
    await expect(h.button(page,'Add member')).toBeVisible();
    '''
    g('REQ-2-2-3', 'selftest member role pointer selection submits and duplicate errors keep the form open', own_org + r'''
    await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer');
    await h.field(page,'Role').click(); await page.getByRole('option',{name:'Member',exact:true}).click({timeout:5000});
    await h.button(page,'Add member').click(); await expect(h.text(page,'bob-reviewer')).toBeVisible();
    await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
    await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer');
    await h.button(page,'Add member').click(); await expect(h.text(page,'Account is already a member')).toBeVisible();
    await expect(h.field(page,'Username or email')).toHaveValue('bob-reviewer');
    await h.field(page,'Username or email').fill('unknown-reviewer'); await h.button(page,'Add member').click();
    await expect(h.text(page,'Account not found')).toBeVisible(); await expect(h.field(page,'Username or email')).toHaveValue('unknown-reviewer');
    await h.button(page,'Cancel').click(); await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
    ''', requires=['REQ-2-2-3','REQ-2-1-2'])
    g('REQ-2-2-3', 'selftest member role keyboard selection persists the selected Member role', own_org + r'''
    await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer');
    await h.field(page,'Role').press('ArrowDown'); await page.keyboard.press('m'); await page.keyboard.press('Enter');
    await h.chosen(page,'Role','Member'); await h.button(page,'Add member').click();
    const member=page.getByRole('listitem').filter({has:h.text(page,'bob-reviewer')});
    await h.persisted(page,async()=>{await expect(member).toHaveCount(1);await expect(h.text(member,'Member')).toBeVisible();});
    ''', requires=['REQ-2-2-3','REQ-2-1-2'])
    g('REQ-2-2-4', 'selftest removed members stay removed until explicit readdition and then reject duplicates', own_org + r'''
    await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').click();
    await expect(h.text(page,'bob-reviewer')).toBeVisible(); await h.button(page,'Member menu bob-reviewer').click();
    await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click(); await h.button(page,'Remove').click();
    await h.persisted(page,()=>expect(h.text(page,'bob-reviewer')).toHaveCount(0));
    await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').click();
    await expect(h.text(page,'bob-reviewer')).toHaveCount(1); await h.button(page,'Add member').click();
    await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').click();
    await expect(h.text(page,'Account is already a member')).toBeVisible(); await h.button(page,'Cancel').click();
    await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
    ''', requires=['REQ-2-2-4','REQ-2-2-3','REQ-2-1-2'])
