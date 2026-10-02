"""Stage 1 regressions from the 43400d1f58ee requirements audit.

Inherited account privacy and public organization boundaries are checked through
public UI. Backend authorization has a separate implementation harness.
"""


def register(g):
    g('REQ-1-1-1', 'homepage Sign up enters registration directly and survives reload', r'''
    await h.home(page);
    for (const name of ['Sign up','Sign in','Forgot password']) await expect(h.link(page,name)).toBeVisible();
    await h.link(page,'Sign up').click();
    await h.persisted(page,async()=>{
      for (const name of ['Username','Email','Password','Confirm password']) await expect(h.field(page,name)).toBeVisible();
      await expect(h.button(page,'Create account')).toBeVisible();
    });
    ''')
    g('REQ-1-1-1', 'rejected registration retains nonsensitive inputs and clears both passwords', r'''
    await h.home(page); await h.link(page,'Sign up').click();
    const email=h.unique('stage1')+'@example.test';
    await h.field(page,'Username').fill('-invalid-user'); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.button(page,'Create account').click(); await expect(h.text(page,'Username format is invalid')).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue('-invalid-user'); await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.button(page,'Account menu')).toHaveCount(0);
    ''')
    g('REQ-1-1-2', 'rejected login clears password retains identifier and allows a valid retry', r'''
    await h.home(page); await h.link(page,'Sign in').click();
    for (const identifier of ['unknown@example.test','alice.dev@example.test']) {
      await h.field(page,'Username or email').fill(identifier); await h.field(page,'Password').fill(h.PASSWORD+'-wrong');
      await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials')).toBeVisible();
      await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Username or email')).toHaveValue(identifier);
      await expect(h.button(page,'Account menu')).toHaveCount(0);
    }
    await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click();
    await h.persisted(page,()=>expect(h.button(page,'Account menu')).toBeVisible());
    await h.button(page,'Account menu').click(); await expect(h.containsValue(page,'alice-dev').first()).toBeVisible();
    ''')
    for code, confirmation, reason in [('000000','Replacement-password-456!','Verification code is invalid'),
                                      ('123456','Different-password-789!','Passwords do not match')]:
        g('REQ-1-1-3', f'rejected recovery clears both passwords and retains verification code: {reason}', f'''
    await h.home(page); await h.link(page,'Forgot password').click();
    await h.field(page,'Email').fill('recovery-invalid-code@example.test'); await h.button(page,'Send reset link').click();
    await h.field(page,'Verification code').fill('{code}');
    await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('{confirmation}');
    await h.button(page,'Reset password').click(); await expect(h.text(page,'{reason}')).toBeVisible();
    await expect(h.field(page,'Verification code')).toHaveValue('{code}');
    await expect(h.field(page,'New password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await h.signIn(page,'recovery-invalid-code@example.test');
    ''')
    g('REQ-2-1-1', 'public organization shows both identities and only repository navigation', r'''
    await h.canonicalOrganization(page);
    await h.persisted(page,async()=>{
      await expect(page.getByRole('heading',{name:'Acme Demo',exact:true})).toBeVisible();
      await expect(page.getByRole('heading',{name:'acme-demo',exact:true})).toBeVisible();
      await expect(h.link(page,'acme-docs')).toBeVisible(); await expect(h.link(page,'secret-research')).toHaveCount(0);
      for (const name of ['People','Teams']) await expect(h.link(page,name)).toHaveCount(0);
      await expect(h.text(page,'bob-reviewer')).toHaveCount(0);
    });
    await h.link(page,'acme-docs').click(); await h.link(page,'Acme Demo').click();
    await expect(page.getByRole('heading',{name:'Acme Demo',exact:true})).toBeVisible();
    ''')
    g('REQ-2-1-2', 'account menu organization entry preserves display name identifier and member navigation', r'''
    await h.signIn(page,'org-owner'); await h.memberOrganization(page);
    await h.persisted(page,async()=>{
      await expect(page.getByRole('heading',{name:'Acme Demo',exact:true})).toBeVisible();
      await expect(page.getByRole('heading',{name:'acme-demo',exact:true})).toBeVisible();
      for (const name of ['Repositories','People','Teams']) await expect(h.link(page,name)).toBeVisible();
    });
    ''')
    g('REQ-2-2-3', 'People denies visitors and nonmembers while an ordinary member can view members', r'''
    await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'People').click();
    await expect(h.text(page,'protected-member')).toBeVisible(); const address=page.url();
    await h.signOut(page); await page.goto(address);
    await h.persisted(page,async()=>{
      await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
      await expect(h.text(page,'protected-member')).toHaveCount(0); await expect(h.text(page,'bob-reviewer')).toHaveCount(0);
    });
    await h.signIn(page,'alice-dev'); await page.goto(address);
    await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
    await expect(h.text(page,'protected-member')).toHaveCount(0);
    await h.signOut(page); await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'People').click();
    await h.persisted(page,()=>expect(h.text(page,'protected-member')).toBeVisible());
    ''', requires=['REQ-2-2-3','REQ-1-2'])
    g('REQ-2-2-1', 'Teams list and detail deny visitors and nonmembers but retain member access', r'''
    await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'Teams').click();
    await expect(h.link(page,'frontend-team')).toBeVisible(); const listAddress=page.url();
    await h.link(page,'frontend-team').click(); await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible();
    const detailAddress=page.url(); await h.signOut(page);
    for (const address of [listAddress,detailAddress]) {
      await page.goto(address); await h.persisted(page,async()=>{
        await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
        await expect(h.link(page,'frontend-team')).toHaveCount(0);
        await expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toHaveCount(0);
      });
    }
    await h.signIn(page,'alice-dev');
    for (const address of [listAddress,detailAddress]) {
      await page.goto(address); await expect(page.getByRole('heading',{name:'Access denied',exact:true})).toBeVisible();
    }
    await h.signOut(page); await h.signIn(page,'org-member'); await h.memberOrganization(page); await h.link(page,'Teams').click();
    await h.link(page,'frontend-team').click();
    await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:'frontend-team'})).toBeVisible());
    ''', requires=['REQ-2-2-1','REQ-1-2'])
