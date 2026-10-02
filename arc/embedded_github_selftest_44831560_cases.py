"""Remaining self-test gaps, reconstructed from public requirements and screenshots.

Immediate visibility is a navigation compatibility check, not a claim about the
unavailable evaluator helper. No private application endpoint is used here.
"""


def register(g):
    g('REQ-1-1-3', '44831560 regression: email-only submission exposes the same recovery step for known and unknown addresses', r'''
    for (const email of ['recovery-visibility@example.test','unknown@example.test']) {
      await h.home(page); await h.link(page,'Sign in').click(); await h.recovery(page,email);
      await expect(h.field(page,'Email')).toHaveValue(email);
      await expect(h.text(page,'123456')).toBeVisible();
      for (const label of ['Verification code','New password','Confirm password']) await expect(h.field(page,label)).toHaveValue('');
      await expect(page.getByRole('alert')).toHaveCount(0);
      // A new recovery step must accept a wrong code and report that error only
      // after an actual reset attempt, while preserving the original account.
      await h.field(page,'Verification code').fill('000000');
      await h.field(page,'New password').fill('Replacement-password-456!');
      await h.field(page,'Confirm password').fill('Replacement-password-456!');
      await h.button(page,'Reset password').click();
      await expect(h.text(page,'Verification code is invalid')).toBeVisible();
    }
    await h.signIn(page,'recovery-visibility@example.test');
    ''')
    g('REQ-1-1-3', '44831560 regression: email submission and invalid code preserve original credentials', r'''
    const {username,email}=await h.register(page);
    await h.recovery(page,email);
    await h.signIn(page,username); await h.signOut(page);
    await h.link(page,'Sign in').click(); await h.recovery(page,email);
    await h.field(page,'Verification code').fill('000000');
    await h.field(page,'New password').fill('Replacement-password-456!');
    await h.field(page,'Confirm password').fill('Replacement-password-456!');
    await h.button(page,'Reset password').click();
    await expect(h.text(page,'Verification code is invalid')).toBeVisible();
    await h.signIn(page,username);
    ''')
    g('REQ-1-1-3', '44831560 regression: successful reset after email submission replaces the original credentials', r'''
    const {username,email}=await h.register(page);
    await h.recovery(page,email);
    await h.field(page,'Verification code').fill('123456');
    await h.field(page,'New password').fill('Replacement-password-456!');
    await h.field(page,'Confirm password').fill('Replacement-password-456!');
    await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toBeVisible();
    await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill(username);
    await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click();
    await expect(h.text(page,'Invalid credentials')).toBeVisible();
    await h.signIn(page,email,'Replacement-password-456!',username);
    await page.reload(); await expect(h.button(page,'Account menu')).toBeVisible();
    ''')
    g('REQ-2-2-2', '44831560 regression: account menu organization entry exposes the named team without a data gap', r'''
    await h.signIn(page,'team-maintainer'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click();
    expect(await h.link(page,'frontend-team').isVisible(),'named team must be ready after directory navigation').toBe(true);
    await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
    await h.chosen(page,'Parent team','platform-team');
    ''')
    g('REQ-2-3', '44831560 regression: account menu organization entry exposes the repository before access management', r'''
    await h.signIn(page,'repo-admin'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await h.link(page,'Acme Demo').click();
    expect(await h.link(page,'acme-docs').isVisible(),'named repository must be ready after directory navigation').toBe(true);
    await h.link(page,'acme-docs').click(); await h.link(page,'Settings').click(); await h.link(page,'Manage access').click();
    await expect(h.button(page,'Add people or teams')).toBeVisible();
    ''')
    g('REQ-2-1-1', '44831560 regression: public directory entry exposes the public repository without a data gap', r'''
    await h.home(page); await h.link(page,'Acme Demo').click();
    expect(await h.link(page,'acme-docs').isVisible(),'public repository must be ready after directory navigation').toBe(true);
    await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible();
    ''')
    g('REQ-2-2-2', '44831560 regression: browser history cannot restore member-only team links after sign-out', r'''
    await h.signIn(page,'team-maintainer'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click();
    await h.link(page,'Acme Demo').click(); await h.link(page,'Teams').click(); await expect(h.link(page,'frontend-team')).toBeVisible();
    await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
    await page.goBack(); await expect(h.text(page,'Access denied')).toBeVisible();
    await expect(h.link(page,'frontend-team')).toHaveCount(0); await expect(h.link(page,'New team')).toHaveCount(0);
    await page.reload(); await expect(h.text(page,'Access denied')).toBeVisible();
    ''', requires=['REQ-2-2-2','REQ-1-2'])
