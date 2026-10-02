"""Revision 8 witnesses grounded in the downloaded full GitHub requirements."""
import json


def register(g):
    # Isolate each invalid field: a broken validator cannot hide behind another
    # simultaneously invalid field. Correcting the same identity proves that
    # the rejected request did not partially reserve an account.
    invalid = [
        ('Username', '-invalid', 'Username format is invalid'),
        ('Username', 'invalid-', 'Username format is invalid'),
        ('Username', 'has--hyphens', 'Username format is invalid'),
        ('Username', 'Uppercase', 'Username format is invalid'),
        ('Username', 'a' * 40, 'Username format is invalid'),
        ('Username', 'bad_name', 'Username format is invalid'),
        ('Email', 'two@@example.test', 'Email format is invalid'),
        ('Email', 'missing@dot', 'Email format is invalid'),
        ('Email', 'empty@.test', 'Email format is invalid'),
        ('Email', 'empty@example..test', 'Email format is invalid'),
        ('Email', 'a' * 242 + '@example.test', 'Email format is invalid'),
        ('Password', 'Aa1!' + 'x' * 7, 'Password requirements are not satisfied'),
        ('Password', 'Aa1!' + 'x' * 125, 'Password requirements are not satisfied'),
        ('Password', 'lowercase-123!', 'Password requirements are not satisfied'),
        ('Password', 'UPPERCASE-123!', 'Password requirements are not satisfied'),
        ('Password', 'Password-only!', 'Password requirements are not satisfied'),
        ('Password', 'Password12345', 'Password requirements are not satisfied'),
        ('Password', 'Valid pass-123!', 'Password requirements are not satisfied'),
        ('Confirm password', 'Other-password-456!', None),
    ]
    for index, (label, value, message) in enumerate(invalid):
        feedback = f"await expect(h.containsValue(page,{json.dumps(message)}).first()).toBeVisible();" if message else ''
        g('REQ-1-1-1', f'isolated registration rejection {index + 1}: {label}; correction creates exactly the attempted identity', f'''
        await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
        const username=h.unique('boundary'), email=`${{username}}@example.test`;
        await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
        await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
        await page.getByRole('checkbox',{{name:'Agree to the terms',exact:true}}).check();
        await h.field(page,{json.dumps(label)}).fill({json.dumps(value)});
        {'await h.field(page,"Confirm password").fill('+json.dumps(value)+');' if label == 'Password' else ''}
        await h.button(page,'Create account').click();{feedback}
        await expect(h.field(page,'Username')).toHaveValue({json.dumps(value) if label == 'Username' else 'username'});
        await expect(h.field(page,'Email')).toHaveValue({json.dumps(value) if label == 'Email' else 'email'});
        await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
        await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
        await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
        await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
        await page.getByRole('checkbox',{{name:'Agree to the terms',exact:true}}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
        ''')

    for size in [12, 128]:
        g('REQ-1-1-2', f'registration accepts password boundary {size} and trimmed email; email sign-in persists', f'''
        const username=h.unique('accepted'), email=`${{username}}@example.test`, password='Aa1!'+'x'.repeat({size}-4);
        await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
        await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(`  ${{email}}  `);
        await h.field(page,'Password').fill(password); await h.field(page,'Confirm password').fill(password);
        await page.getByRole('checkbox',{{name:'Agree to the terms',exact:true}}).check(); await h.button(page,'Create account').click();
        await expect(h.field(page,'Username or email')).toBeVisible(); await h.signIn(page,email,password,username);
        ''', requires=['REQ-1-1-1','REQ-1-1-2'])

    g('REQ-1-1-1', 'duplicate email retains identity; correcting email does not encounter a partially created username', r'''
    const username=h.unique('duplicate-email'), email='alice.dev@example.test';
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username')).toHaveValue(username); await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await h.field(page,'Email').fill(`${username}@example.test`); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
    ''')

    g('REQ-2-2-2', 'valid parent change persists independently of the earlier parent relationship', r'''
    await h.signIn(page,'spec-owner'); await h.organization(page,'team-parent-valid'); await h.link(page,'Teams').click();
    await h.link(page,'frontend-child').click(); await h.link(page,'Settings').click();
    await h.choose(page,'Parent team','platform-team'); await h.button(page,'Save').click();
    await h.persisted(page,()=>h.chosen(page,'Parent team','platform-team'));
    await h.choose(page,'Parent team','frontend-team'); await h.button(page,'Save').click();
    await h.persisted(page,()=>h.chosen(page,'Parent team','frontend-team'));
    await h.organization(page,'team-parent-valid'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
    await h.persisted(page,()=>h.chosen(page,'Parent team','platform-team'));
    ''', 'team-parent-valid')

    g('REQ-2-2-4', 'last Owner removal is rejected and retains organization and direct team membership', r'''
    await h.signIn(page,'spec-owner'); await h.organization(page,'last-owner'); await h.link(page,'People').click();
    await expect(h.containsValue(page,'spec-owner').first()).toBeVisible();
    await expect(h.button(page,'Member menu spec-owner')).toBeVisible();
    await h.button(page,'Member menu spec-owner').click(); await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click();
    const remove=h.button(page,'Remove'); if(await remove.isEnabled()) await h.attemptSubmission(page,remove);
    await h.organization(page,'last-owner'); await h.link(page,'People').click();
    await h.persisted(page,()=>expect(h.containsValue(page,'spec-owner').first()).toBeVisible());
    await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click();
    await h.persisted(page,()=>expect(h.button(page,'Remove spec-owner')).toBeVisible());
    ''', 'last-owner', requires=['REQ-2-2-4','REQ-2-2-2'])

    g('REQ-5-4', 'Triage closes and reopens an issue without receiving Write content authority', r'''
    await h.signIn(page,'spec-triage'); await h.issue(page,'issue-triage-status');
    await h.button(page,'Close issue').click(); await expect(h.button(page,'Reopen issue')).toBeVisible();
    await h.persisted(page,()=>expect(h.button(page,'Reopen issue')).toBeVisible());
    await h.button(page,'Reopen issue').click(); await h.persisted(page,()=>expect(h.button(page,'Close issue')).toBeVisible());
    await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
    await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();
    ''', 'issue-triage-status', requires=['REQ-5-4','REQ-5-2-2'])

    for length in [1, 39]:
        g('REQ-1-1-1', f'username legal length {length} is accepted', f'''
        const username={"'z'" if length == 1 else "h.unique('u').padEnd(39,'x')"};
        await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
        await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(`${{h.unique()}}@example.test`);
        await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
        await page.getByRole('checkbox',{{name:'Agree to the terms',exact:true}}).check(); await h.button(page,'Create account').click();
        await expect(h.field(page,'Username or email')).toBeVisible();
        ''')

    g('REQ-1-1-1', 'email legal length 254 is accepted', r'''
    const username=h.unique('email-boundary'), email=username.padEnd(241,'x')+'@example.test'; expect(email.length).toBe(254);
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username or email')).toBeVisible();
    ''')

    g('REQ-2-2-1', 'team legal length 50 is accepted and overlong 51 is refused without creating a team', r'''
    await h.signIn(page,'spec-owner'); await h.organization(page,'team-boundaries'); await h.link(page,'Teams').click();
    const list=page.url(), name=h.unique('team').padEnd(50,'x');
    await h.link(page,'New team').click(); await h.field(page,'Team name').fill(name+'x'); await h.button(page,'Create team').click();
    await expect(h.text(page,'Team name is invalid').first()).toBeVisible(); await page.goto(list);
    await expect(h.link(page,name+'x')).toHaveCount(0); await h.link(page,'New team').click(); await h.field(page,'Team name').fill(name);
    await h.button(page,'Create team').click(); await h.persisted(page,()=>expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
    ''', 'team-boundaries')

    g('REQ-2-2-1', 'duplicate team in the same organization does not create a second relationship', r'''
    await h.signIn(page,'spec-owner'); await h.organization(page,'team-duplicate'); await h.link(page,'Teams').click(); const list=page.url();
    await expect(h.link(page,'frontend-team')).toHaveCount(1); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('frontend-team');
    await h.attemptSubmission(page,h.button(page,'Create team'));
    await page.goto(list); await h.persisted(page,()=>expect(h.link(page,'frontend-team')).toHaveCount(1));
    ''', 'team-duplicate')

    g('REQ-5-2-2', 'Write saves title and description independently without Triage metadata authority', r'''
    await h.signIn(page,'spec-write'); await h.issue(page,'issue-write-edit'); const title=h.unique('write-title'), body=h.unique('write-body');
    await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill(title); await h.button(page,'Save issue title').click();
    await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();await expect(h.text(page,'Describe the onboarding improvement.')).toBeVisible();});
    await h.button(page,'Edit issue description').click(); await h.field(page,'Issue description').fill(body); await h.button(page,'Save issue description').click();
    await h.persisted(page,async()=>{await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();await expect(h.text(page,body)).toBeVisible();});
    for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
    ''', 'issue-write-edit')

    g('REQ-5-3-2', 'Triage toggles a label without receiving Write content authority', r'''
    await h.signIn(page,'spec-triage'); await h.issue(page,'issue-triage-label'); await h.button(page,'Labels').click();
    await h.option(page,'bug'); await h.persisted(page,()=>expect(h.metadataValue(page,'Labels','bug').first()).toBeVisible());
    await h.button(page,'Labels').click(); await h.option(page,'bug');
    await h.persisted(page,()=>expect(h.metadataValue(page,'Labels','bug')).toHaveCount(0));
    await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
    ''', 'issue-triage-label', requires=['REQ-5-3-2','REQ-5-2-2'])
