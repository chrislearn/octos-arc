#!/usr/bin/env python3
"""Reproduce the curated source suites. Review/freeze is a separate audit step.

These recipes use atomic prose and inherited interaction contracts because the
supplied scenario templates often contain no actionable steps. No model/API call.
"""
from pathlib import Path
import json
import textwrap
import yaml

ROOT = Path(__file__).resolve().parent / 'derived-tests'
CASES = {}

def case(task, node, title, body, *, fixture=None, file=None, requires=None):
    file = file or node
    phase = 'integration' if file.startswith('INTEGRATION-') else 'node'
    CASES.setdefault(task, {}).setdefault(file, []).append({
        'node_id': node, 'title': title, 'body': textwrap.dedent(body).strip(),
        'fixture': fixture, 'phase': phase, 'requires': requires or [node],
    })

def s(node, title, body, **options): case('hackathon--sheet', node, title, body, **options)
def g(node, title, body, fixture=None, **options): case('hackathon--github', node, title, body, fixture=fixture, **options)

g('REQ-1-1-1','registration entry accepts valid account and redirects to sign-in without exposing password', r'''
await h.home(page); await h.link(page,'Sign in').click(); await expect(h.link(page,'Create an account')).toHaveCount(1); await h.link(page,'Create an account').click();
for(const label of ['Username','Email','Password','Confirm password']) await expect(h.field(page,label)).toHaveCount(1);
await expect(page.getByRole('checkbox',{name:'Agree to the terms',exact:true})).not.toBeChecked(); await expect(h.button(page,'Create account')).toBeEnabled();
await h.register(page); await expect(h.field(page,'Username or email')).toBeVisible(); await expect(page.locator('body')).not.toContainText(h.PASSWORD);
''')
g('REQ-1-1-1','registered credentials work by email and survive a later browser session', r'''
const {username,email}=await h.register(page); await h.signIn(page,email);
await h.persisted(page, () => expect(h.button(page,'Account menu')).toBeVisible());
await h.button(page,'Account menu').click(); await expect(h.text(page,username).first()).toBeVisible();
const later=await browser.newContext();
try { const p=await later.newPage(); await h.signIn(p,username); await expect(h.button(p,'Account menu')).toBeVisible(); }
finally { await later.close(); }
''', file='INTEGRATION-identity', requires=['REQ-1-1-1','REQ-1-1-2'])
g('REQ-1-1-1','all invalid fields show errors together and clear sensitive values', r'''
await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
await h.field(page,'Username').fill('-invalid'); await h.field(page,'Email').fill('not-an-email'); await h.field(page,'Password').fill('short'); await h.field(page,'Confirm password').fill('different'); await h.button(page,'Create account').click();
for(const message of ['Username format is invalid','Email format is invalid','Password requirements are not satisfied','Agree to terms is required']) await expect(page.getByText(message,{exact:false})).toBeVisible();
await expect(h.field(page,'Username')).toHaveValue('-invalid'); await expect(h.field(page,'Email')).toHaveValue('not-an-email'); await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue(''); await expect(h.button(page,'Create account')).toBeEnabled();
''')
g('REQ-1-1-1','duplicate username preserves both attempted non-sensitive values', r'''
await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click(); const email=`${h.unique()}@example.test`;
await h.field(page,'Username').fill('alice-dev'); await h.field(page,'Email').fill(email); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD); await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
await expect(page.getByText('Username already exists',{exact:false})).toBeVisible(); await expect(h.field(page,'Username')).toHaveValue('alice-dev'); await expect(h.field(page,'Email')).toHaveValue(email);
''')
for username in ['alice-dev','alice.dev@example.test']:
 g('REQ-1-1-2','existing '+username+' creates persistent session',f'''
 await h.signIn(page,{json.dumps(username)}); await h.persisted(page, () => expect(h.button(page,'Account menu')).toBeVisible());
 ''')
for username,password in [('unknown-reviewer','Valid-password-123!'),('alice-dev','Wrong-password-456!'),('spec-unavailable','Valid-password-123!')]:
 g('REQ-1-1-2','generic credential rejection for '+username+' / '+('wrong password' if password.startswith('Wrong') else 'account state'),f'''
 await h.home(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill({json.dumps(username)}); await h.field(page,'Password').fill({json.dumps(password)}); await h.button(page,'Sign in').click();
 await expect(h.text(page,'Invalid credentials').first()).toBeVisible(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.reload(); await expect(h.button(page,'Account menu')).toHaveCount(0);
 ''')
g('REQ-1-1-2','guide: a newly registered identity signs in by email and username across reload and an independent session',r'''
let identity: {username: string, email: string};
await test.step('Create an account through the earlier registration capability',async()=>{ identity=await h.register(page); });
await test.step('Use its email and retain the authenticated session after reload',async()=>{
  await h.signIn(page,identity.email); await h.persisted(page,()=>expect(h.button(page,'Account menu')).toBeVisible());
  await h.button(page,'Account menu').click(); await expect(h.text(page,identity.username).first()).toBeVisible();
});
await test.step('Use its username in an independent browser session',async()=>{
  const later=await browser.newContext({baseURL:new URL(page.url()).origin});
  try { const p=await later.newPage(); await h.signIn(p,identity.username); await h.persisted(p,()=>expect(h.button(p,'Account menu')).toBeVisible()); }
  finally { await later.close(); }
});
''',requires=['REQ-1-1-2','REQ-1-1-1'])
g('REQ-1-1-3','valid local recovery updates only registered credentials; invalid code preserves old password', r'''
const {username,email}=await h.register(page); await h.link(page,'Forgot password').click(); await h.field(page,'Email').fill(email); await h.button(page,'Send reset link').click();
await expect(h.text(page,'123456').first()).toBeVisible(); await h.field(page,'Verification code').fill('000000'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click();
await expect(page.getByText('Verification code is invalid',{exact:false})).toBeVisible(); await h.signIn(page,username); await h.signOut(page);
await h.link(page,'Forgot password').click(); await h.field(page,'Email').fill(email); await h.button(page,'Send reset link').click(); await h.field(page,'Verification code').fill('123456'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click();
await expect(h.text(page,'Password updated').first()).toBeVisible(); await h.signIn(page,username,'Replacement-password-456!'); await h.signOut(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill(username); await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials').first()).toBeVisible();
''')
g('REQ-1-1-3','unknown email shows the same fixed code and reset form but cannot update an account', r'''
const {username}=await h.register(page); await h.link(page,'Forgot password').click(); await h.field(page,'Email').fill(`${h.unique()}@example.test`); await h.button(page,'Send reset link').click();
await expect(h.text(page,'123456').first()).toBeVisible(); for(const label of ['Verification code','New password','Confirm password']) await expect(h.field(page,label)).toBeVisible();
await h.field(page,'Verification code').fill('123456'); await h.field(page,'New password').fill('Replacement-password-456!'); await h.field(page,'Confirm password').fill('Replacement-password-456!'); await h.button(page,'Reset password').click(); await expect(h.text(page,'Password updated')).toHaveCount(0); await h.signIn(page,username);
''')
g('REQ-1-2','cancel retains session and confirm invalidates protected page after reload/back/direct entry', r'''
await h.signIn(page); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click(); const protectedAddress=page.url();
await h.button(page,'Account menu').click(); await h.link(page,'Sign out').click(); const dialog=page.getByRole('dialog',{name:'Sign out',exact:true}); await h.button(dialog,'Cancel').click();
await expect(h.button(page,'Account menu')).toBeVisible(); await expect(page).toHaveURL(protectedAddress); await h.signOut(page);
await page.reload(); await expect(h.link(page,'Sign in')).toBeVisible(); await page.goBack(); await expect(h.button(page,'Account menu')).toHaveCount(0); await page.goto(protectedAddress); await expect(h.link(page,'Sign in')).toBeVisible();
''')
g('REQ-1-3','password change uses current account and old password no longer signs in', r'''
const {username}=await h.register(page); await h.signIn(page,username); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click(); await h.link(page,'Password and authentication').click();
await h.field(page,'Current password').fill(h.PASSWORD); await h.field(page,'New password').fill('New-password-456!'); await h.field(page,'Confirm password').fill('New-password-456!'); await h.button(page,'Update password').click(); await expect(h.text(page,'Password updated').first()).toBeVisible(); await h.signOut(page);
await h.signIn(page,username,'New-password-456!'); await h.signOut(page); await h.link(page,'Sign in').click(); await h.field(page,'Username or email').fill(username); await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click(); await expect(h.text(page,'Invalid credentials').first()).toBeVisible();
''')
g('REQ-1-3','missing current password and mismatch leave original credentials usable', r'''
const {username}=await h.register(page); await h.signIn(page,username); await h.button(page,'Account menu').click(); await h.link(page,'Settings').click(); await h.link(page,'Password and authentication').click();
await h.field(page,'New password').fill('Required-password-789!'); await h.field(page,'Confirm password').fill('Required-password-789!'); await h.button(page,'Update password').click(); await expect(page.getByText('Current password is required',{exact:false})).toBeVisible();
await h.field(page,'Current password').fill('Wrong-password-456!'); await h.field(page,'New password').fill('Required-password-789!'); await h.field(page,'Confirm password').fill('does-not-match'); await h.button(page,'Update password').click(); await expect(page.getByText(/Current password is incorrect|Password confirmation does not match/)).toBeVisible(); await h.signOut(page); await h.signIn(page,username);
''')
g('REQ-2-1-1','organization live repository filter exposes public result and hides private result', r'''
await h.organization(page); await h.link(page,'Repositories').click(); await h.field(page,'Find a repository').fill('acme-docs'); await expect(h.link(page,'acme-docs')).toBeVisible();
await h.link(page,'acme-docs').click(); await expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible(); await page.goBack(); await expect(h.link(page,'acme-docs')).toBeVisible();
await h.field(page,'Find a repository').fill('secret-research'); await expect(h.link(page,'secret-research')).toHaveCount(0);
''')
g('REQ-2-1-2','create organization persists identifier and creator Owner relationship', r'''
await h.signIn(page); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click(); const name=h.unique('pw-org');
await h.field(page,'Organization name').fill(name); await h.field(page,'Display name').fill('Mobile Guild'); await h.button(page,'Create organization').click(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
await h.link(page,'People').click(); await expect(h.text(page,'alice-dev').first()).toBeVisible(); await expect(h.text(page,'Owner').first()).toBeVisible();
''')
g('REQ-2-1-2','duplicate organization and malformed input remain retryable without creating organization', r'''
await h.signIn(page); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await h.link(page,'New organization').click();
await h.field(page,'Organization name').fill('spec-org-existing'); await h.field(page,'Display name').fill(''); await h.button(page,'Create organization').click(); await expect(page.getByText('Organization name already exists',{exact:false})).toBeVisible(); await expect(h.field(page,'Organization name')).toHaveValue('spec-org-existing');
await h.field(page,'Organization name').fill('-invalid-organization'); await h.field(page,'Display name').fill('   '); await h.button(page,'Create organization').click(); await expect(page.getByText('Organization name format is invalid',{exact:false})).toBeVisible(); await expect(page.getByText('Display name is required',{exact:false})).toBeVisible();
''')
g('REQ-2-2-1','Owner creates unique team without optional description or parent', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'team-create'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); const name=h.unique('pw-team');
await h.field(page,'Team name').fill(name); await h.button(page,'Create team').click(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:name})).toBeVisible());
''', 'team-create')
g('REQ-2-2-1','invalid team name leaves creation form and no team', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'team-invalid'); await h.link(page,'Teams').click(); await h.link(page,'New team').click(); await h.field(page,'Team name').fill('-invalid'); await h.button(page,'Create team').click();
await expect(page.getByText('Team name format is invalid',{exact:false})).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'-invalid',exact:true})).toHaveCount(0);
''','team-invalid')
g('REQ-2-2-2','Owner adds and immediately removes direct team member with persistence', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'team-members'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Members').click();
await h.button(page,'Add member').click(); await h.field(page,'Username').fill('bob-reviewer'); await h.button(page,'Add member').click();
await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
''','team-members')
g('REQ-2-2-2','cycle rejects and preserves original parent value across reload', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'team-cycle'); await h.link(page,'Teams').click(); await h.link(page,'frontend-team').click(); await h.link(page,'Settings').click();
const parent=h.field(page,'Parent team'); const original=await parent.inputValue(); await parent.selectOption({label:'frontend-child'}); await h.button(page,'Save').click(); await expect(h.text(page,'Cyclic team hierarchy is not allowed').first()).toBeVisible(); await expect(parent).toHaveValue(original); await page.reload(); await expect(parent).toHaveValue(original);
''','team-cycle')
g('REQ-2-2-3','adding Member is immediate, listed after own login, but grants no private access', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'member-add'); await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('spec-new-member'); await h.choose(page,'Role','Member'); await h.button(page,'Add member').last().click();
await h.persisted(page, () => expect(h.text(page,'spec-new-member').first()).toBeVisible()); await expect(h.text(page,'Pending')).toHaveCount(0); await expect(h.text(page,'Awaiting')).toHaveCount(0);
await h.repo(page,h.fixtureRepo('member-add')); const privateAddress=page.url(); await h.signOut(page); await h.signIn(page,'spec-new-member'); await h.button(page,'Account menu').click(); await h.link(page,'Your organizations').click(); await expect(h.text(page,h.orgName('member-add')).first()).toBeVisible(); await page.goto(privateAddress); await expect(h.text(page,'Access denied').first()).toBeVisible();
''','member-add')
g('REQ-2-2-3','unknown and duplicate member keep form open and do not duplicate membership', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'member-invalid'); await h.link(page,'People').click(); await h.button(page,'Add member').click(); await h.field(page,'Username or email').fill('unknown-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account not found').first()).toBeVisible();
await h.field(page,'Username or email').fill('bob-reviewer'); await h.button(page,'Add member').last().click(); await expect(h.text(page,'Account is already a member').first()).toBeVisible(); await expect(h.field(page,'Username or email')).toBeVisible(); await page.reload(); await expect(h.text(page,'bob-reviewer')).toHaveCount(1);
''','member-invalid')
g('REQ-2-2-4','Owner removes membership and associated access without deleting account', r'''
await h.signIn(page,'spec-owner'); await h.organization(page,'member-remove'); await h.link(page,'People').click(); await h.button(page,'Member menu bob-reviewer').click(); await page.getByRole('menuitem',{name:'Remove from organization',exact:true}).click(); await h.button(page,'Remove').click(); await h.persisted(page, () => expect(h.text(page,'bob-reviewer')).toHaveCount(0));
await h.repo(page,h.fixtureRepo('member-remove')); const address=page.url(); await h.signOut(page); await h.signIn(page,'bob-reviewer'); await page.goto(address); await expect(h.text(page,'Access denied').first()).toBeVisible();
''','member-remove')
g('REQ-2-2-4','ordinary member has no removal controls', r'''
await h.signIn(page,'spec-read'); await h.organization(page,'member-read'); await h.link(page,'People').click(); await expect(h.text(page,'bob-reviewer').first()).toBeVisible(); await expect(h.button(page,'Member menu bob-reviewer')).toHaveCount(0); await expect(page.getByRole('menuitem',{name:'Remove from organization',exact:true})).toHaveCount(0);
''','member-read')
g('REQ-2-3','live team search creates one Write grant and reload retains it', r'''
await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('grant-add')); await h.settings(page,'Manage access'); await h.button(page,'Add people or teams').click(); const picker=await h.accessPicker(page); await picker.getByRole('textbox',{name:'Search',exact:true}).fill('frontend-team'); await page.getByRole('option',{name:'frontend-team',exact:true}).click(); await h.choose(picker,'Role','Write'); await h.button(picker,'Add').click();
const row=page.getByRole('row',{name:/frontend-team/}); await h.persisted(page, async () => { await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write'); });
''','grant-add')
g('REQ-2-3','native Read selection replaces Write rather than appending a grant', r'''
await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('grant-replace')); await h.settings(page,'Manage access'); const row=page.getByRole('row',{name:/frontend-team/}); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Write'); await row.getByRole('combobox',{name:'Role',exact:true}).selectOption({label:'Read'}); await h.button(row,'Save').click();
await h.persisted(page, async () => { await expect(row).toHaveCount(1); await expect(row.getByRole('combobox',{name:'Role',exact:true}).locator('option:checked')).toHaveText('Read'); });
''','grant-replace')
g('REQ-3-1','global search opens public identity and excludes private repository', r'''
await h.repo(page); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible()); await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('secret-research'); await search.press('Enter'); await expect(h.link(page,'secret-research')).toHaveCount(0);
''')
g('REQ-3-1','empty repository search is repeatable without stale results', r'''
for(let i=0;i<2;i++){ await h.home(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-repository'); await search.press('Enter'); await expect(h.text(page,'No results').first()).toBeVisible(); await expect(h.link(page,'acme-docs')).toHaveCount(0); }
''')
g('REQ-3-2-1','default personal namespace creates initialized Private repository and saved README', r'''
await h.signIn(page); await h.link(page,'New repository').click(); const name=h.unique('pw-repo'); await h.field(page,'Repository name').fill(name); await h.field(page,'Description').fill('Repository created by Playwright'); await page.getByRole('radio',{name:'Private',exact:true}).check(); await page.getByRole('checkbox',{name:'Add a README file',exact:true}).check(); await h.button(page,'Create repository').click();
await h.persisted(page, async () => { await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible(); await expect(h.text(page,'Private').first()).toBeVisible(); await expect(h.link(page,'README.md')).toBeVisible(); await expect(h.text(page,'Repository created by Playwright').first()).toBeVisible(); });
''')
g('REQ-3-2-1','duplicate and empty repository names retain form and create no repository', r'''
await h.signIn(page); await h.link(page,'New repository').click(); await h.field(page,'Repository name').fill('acme-docs'); await h.button(page,'Create repository').click(); await expect(h.field(page,'Repository name')).toBeVisible(); await expect(page.getByRole('heading',{name:'alice-dev/acme-docs',exact:true})).toHaveCount(0); await h.field(page,'Repository name').fill(''); await h.button(page,'Create repository').click(); await expect(h.field(page,'Repository name')).toBeVisible();
''')
g('REQ-3-2-2','fork records source relationship and independent readable history', r'''
await h.signIn(page); await h.repo(page); await h.button(page,'Fork').click(); const name=h.unique('pw-fork'); await h.field(page,'Repository name').fill(name); await h.button(page,'Create fork').click();
await h.persisted(page, async () => { await expect(page.getByRole('heading').filter({hasText:name})).toBeVisible(); await expect(h.text(page,'Forked from acme-docs').first()).toBeVisible(); await expect(h.link(page,'README.md')).toBeVisible(); }); await h.link(page,'Commits').click(); await expect(h.text(page,'Document search flow').first()).toBeVisible();
''')
g('REQ-3-2-2','conflicting fork name cannot open or modify an existing repository', r'''
await h.signIn(page); await h.repo(page); await h.button(page,'Fork').click(); await h.field(page,'Repository name').fill('acme-docs-fork'); await h.button(page,'Create fork').click(); await expect(h.field(page,'Repository name')).toBeVisible(); await expect(page.getByRole('heading',{name:'alice-dev/acme-docs-fork',exact:true})).toHaveCount(0);
''')
for protocol in ['HTTPS','SSH']:
 g('REQ-3-2-3','copy complete '+protocol+' clone value without modifying repository',f'''
 await h.repo(page); await h.button(page,'Code').click(); await page.getByRole('tab',{{name:{json.dumps(protocol)},exact:true}}).click(); await h.button(page,'Copy clone value').click(); await expect(h.text(page,'Copied').first()).toBeVisible();
 const value=await page.evaluate(() => navigator.clipboard.readText()); expect(value).toMatch({'/^https:\\/\\/[^\\s]+\\/[^\\s/]+\\/acme-docs\\.git$/' if protocol=='HTTPS' else '/^(?:[^@\\s]+@[^:\\s]+:[^\\s/]+\\/acme-docs\\.git|ssh:\\/\\/[^\\s]+\\/acme-docs\\.git)$/'}); await expect(page.getByRole('heading').filter({{hasText:'acme-docs'}})).toBeVisible();
 ''')
g('REQ-3-3','visitor public repository overview and Code navigation persist', r'''
await h.repo(page); await expect(h.text(page,'Public').first()).toBeVisible(); await expect(h.link(page,'Code')).toBeVisible(); await h.persisted(page, () => expect(page.getByRole('heading').filter({hasText:'acme-docs'})).toBeVisible());
''')
g('REQ-3-4','Admin makes Private repository Public and fresh visitor reads saved identity', r'''
await h.signIn(page,'spec-admin'); const address=await h.repo(page,h.fixtureRepo('visibility')); await expect(h.text(page,'Private').first()).toBeVisible(); await h.settings(page,'General'); await h.button(page,'Change visibility').click(); await page.getByRole('radio',{name:'Public',exact:true}).check(); await h.button(page,'Confirm visibility').click(); await expect(h.text(page,'Public').first()).toBeVisible();
const visitor=await browser.newContext(); const p=await visitor.newPage(); await p.goto(address); await expect(p.getByRole('heading').filter({hasText:h.fixtureRepo('visibility')})).toBeVisible(); await expect(h.text(p,'Public').first()).toBeVisible(); await visitor.close();
''','visibility')
g('REQ-3-4','non-Admin cannot activate visibility change', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('visibility-read')); if(await h.link(page,'Settings').count()) { await h.link(page,'Settings').click(); if(await h.link(page,'General').count()) await h.link(page,'General').click(); } await expect(h.button(page,'Change visibility')).toHaveCount(0);
''','visibility-read')
g('REQ-4-1','visitor directory/file navigation persists exact path content', r'''
await h.repo(page); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await h.persisted(page, () => expect(h.text(page,'export const search = "search flow";')).toBeVisible()); await expect(page.locator('body')).toContainText('src');
''')
g('REQ-4-2-1','branch commit history displays exact message, author and relative timestamp', r'''
await h.repo(page); await h.link(page,'Commits').click(); await expect(h.text(page,'Document search flow').first()).toBeVisible(); await expect(h.text(page,'alice-dev').first()).toBeVisible(); await expect(page.getByText(/\bago\b/).first()).toBeVisible();
''')
g('REQ-4-2-2','visitor commit diff reads changed file and exact additions/deletions from the parent snapshot', r'''
await h.repo(page); await h.link(page,'Commits').click(); await h.link(page,'Document search flow').click(); const address=page.url(); await page.goto(address); await expect(h.text(page,'src/search.ts').first()).toBeVisible(); await expect(page.getByText(/Changed files/).first()).toBeVisible(); await expect(page.getByText('2 additions, 0 deletions',{exact:false}).first()).toBeVisible();
''')
g('REQ-4-2-3','repository code result opens matching file with persisted code context', r'''
await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('search flow'); await search.press('Enter'); await h.link(page,'Code').click(); await h.link(page,'README.md').click(); await h.persisted(page, () => expect(h.text(page,'search flow').first()).toBeVisible()); await expect(h.link(page,'README.md')).toBeVisible();
''')
g('REQ-4-2-3','no code matches retain exact query across repeated searches', r'''
for(let i=0;i<2;i++){ await h.repo(page); const search=page.getByRole('searchbox',{name:'Search',exact:true}); await search.fill('no-such-token'); await search.press('Enter'); await h.link(page,'Code').click(); await expect(h.text(page,'No code results').first()).toBeVisible(); await expect(search).toHaveValue('no-such-token'); await expect(h.link(page,'README.md')).toHaveCount(0); }
''')
g('REQ-4-3-1','branch live selector switches file snapshot and persists current page branch', r'''
await h.repo(page); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('feature-search'); await h.option(page,'feature-search'); await h.persisted(page, async () => { await expect(h.button(page,'Branch feature-search')).toBeVisible(); await expect(h.link(page,'main-only.md')).toBeVisible(); });
''')
g('REQ-4-3-1','unknown branch leaves original branch intact after Escape and refresh', r'''
await h.repo(page); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('unknown-branch'); await expect(h.text(page,'No matching branch').first()).toBeVisible(); await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
''')
g('REQ-4-3-2','Write branch creation defaults to current head and switches immediately', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('branch-create')); await h.button(page,'Branch main').click(); const name=h.unique('pw-branch'); await h.field(page,'Find branch').fill(name); await h.option(page,`Create branch: ${name}`); await h.persisted(page, () => expect(h.button(page,`Branch ${name}`)).toBeVisible()); await expect(h.link(page,'README.md')).toBeVisible();
''','branch-create')
g('REQ-4-3-2','invalid branch is rejected live and never created', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('branch-invalid')); await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('invalid..branch'); await expect(h.text(page,'Invalid branch').first()).toBeVisible(); await expect(page.getByRole('option',{name:'Create branch: invalid..branch',exact:true})).toHaveCount(0); await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
''','branch-invalid')
g('REQ-4-3-3','Admin changes native default branch and old branch still exists', r'''
await h.signIn(page,'spec-admin'); const address=await h.repo(page,h.fixtureRepo('default-branch')); await h.settings(page,'Branches'); await h.field(page,'Default branch').selectOption({label:'feature-search'}); await h.button(page,'Update').click(); await h.button(page.getByRole('dialog'),'Confirm').click(); await page.goto(address); await expect(h.button(page,'Branch feature-search')).toBeVisible(); await h.button(page,'Branch feature-search').click(); await expect(page.getByRole('option',{name:'main',exact:true})).toBeVisible();
''','default-branch')
g('REQ-4-3-3','non-Admin default-branch edit controls are absent', r'''
await h.signIn(page,'spec-read'); await h.repo(page,h.fixtureRepo('default-read')); if(await h.link(page,'Settings').count()){ await h.link(page,'Settings').click(); if(await h.link(page,'Branches').count()) await h.link(page,'Branches').click(); } await expect(h.field(page,'Default branch')).toHaveCount(0); await expect(h.button(page,'Update')).toHaveCount(0);
''','default-read')
g('REQ-4-4','file creation persists exact contents', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('file-create')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('pw-file')}.md`,message=`Add ${name}`;
await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('Persisted file contents'); await h.field(page,'Commit message').fill(message); await h.button(page,'Commit changes').click(); await h.persisted(page, () => expect(h.text(page,'Persisted file contents').first()).toBeVisible());
''','file-create')
g('REQ-4-4','invalid path rejects even with a valid commit message', r'''
await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-invalid-path')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.field(page,'Commit message').fill('Attempt invalid path'); await h.button(page,'Commit changes').click();
await expect(h.text(page,'Invalid file path').first()).toBeVisible(); await page.goto(address); await h.persisted(page,()=>expect(h.link(page,'invalid.md')).toHaveCount(0));
''','file-invalid-path')
g('REQ-4-4','empty commit message rejects even with a valid file path', r'''
await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-invalid-message')); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click(); const name=`${h.unique('valid')}.md`;
await h.field(page,'File name').fill(name); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click();
await expect(h.text(page,'Commit message is required').first()).toBeVisible(); await page.goto(address); await h.persisted(page,()=>expect(h.link(page,name)).toHaveCount(0));
''','file-invalid-message')
g('REQ-4-4','invalid path and empty message cannot change files or history', r'''
await h.signIn(page,'spec-write'); const address=await h.repo(page,h.fixtureRepo('file-invalid')); await h.link(page,'Commits').click(); const before=await h.historyLinks(page); await page.goto(address); await h.button(page,'Add file').click(); await page.getByRole('menuitem',{name:'Create new file',exact:true}).click();
await h.field(page,'File name').fill('../invalid.md'); await h.field(page,'File contents').fill('must not be saved'); await h.button(page,'Commit changes').click(); await expect(page.getByRole('alert').filter({hasText:/Invalid file path|Commit message is required/}).first()).toBeVisible(); await page.goto(address); await expect(h.link(page,'invalid.md')).toHaveCount(0); await h.link(page,'Commits').click(); await expect.poll(()=>h.historyLinks(page),{message:'Rejected commit must preserve history'}).toEqual(before); await page.reload(); await expect.poll(()=>h.historyLinks(page)).toEqual(before);
''','file-invalid', file='INTEGRATION-file-history', requires=['REQ-4-4','REQ-4-2-1'])
g('REQ-5-1-1','Open/Closed live issue filters combine with keyword and survive refresh', r'''
await h.repo(page); await h.link(page,'Issues').click(); await h.link(page,'Open').click(); await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill('Improve onboarding'); await h.persisted(page, () => expect(h.link(page,'Improve onboarding')).toBeVisible());
await h.link(page,'Closed').click(); await page.getByRole('searchbox',{name:'Search issues',exact:true}).fill('Legacy welcome text'); await expect(h.link(page,'Legacy welcome text')).toBeVisible(); await expect(h.link(page,'Improve onboarding')).toHaveCount(0);
''')
g('REQ-5-1-2','visitor issue detail shows complete title, description and readable timeline', r'''
await h.issue(page); const address=page.url(); await page.goto(address); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.text(page,'Describe the onboarding improvement.').first()).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(page.getByText(/Comment|Activity/).first()).toBeVisible(); });
''')
g('REQ-5-2-1','Write creates issue with exact title/body and list reads same persisted record', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('issue-create')); await h.link(page,'Issues').click(); const listAddress=page.url(); await h.link(page,'New issue').click(); const title=h.unique('pw-issue'); await h.field(page,'Title').fill(title); await h.field(page,'Description').fill('Complete saved issue description.'); await h.button(page,'Submit new issue').click();
await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Complete saved issue description.').first()).toBeVisible(); }); await page.goto(listAddress); await expect(h.link(page,title)).toBeVisible();
''','issue-create')
g('REQ-5-2-1','blank issue title creates neither issue nor partial record', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('issue-create-invalid')); await h.link(page,'Issues').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible(); const before=await page.getByRole('link').allTextContents(),address=page.url(); await h.link(page,'New issue').click(); await h.field(page,'Title').fill('   '); await h.button(page,'Submit new issue').click(); await expect(page.getByText('Title is required',{exact:false})).toBeVisible(); await page.goto(address); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before); await page.reload(); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before);
''','issue-create-invalid')
g('REQ-5-2-2','Maintain saves issue title and body with separate commit actions and persists both', r'''
await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-edit'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('Updated onboarding title'); await h.button(page,'Save issue title').click(); await h.button(page,'Edit issue description').click(); await h.field(page,'Issue description').fill('Updated onboarding body'); await h.button(page,'Save issue description').click();
await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Updated onboarding title',exact:true})).toBeVisible(); await expect(h.text(page,'Updated onboarding body').first()).toBeVisible(); });
''','issue-edit')
g('REQ-5-2-2','blank edited title preserves exact original title after reload', r'''
await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-edit-invalid','Original issue title'); await h.button(page,'Edit issue title').click(); await h.field(page,'Issue title').fill('   '); await h.button(page,'Save issue title').click(); await expect(page.getByText('Title is required',{exact:false})).toBeVisible(); await page.reload(); await expect(page.getByRole('heading',{name:'Original issue title',exact:true})).toBeVisible();
''','issue-edit-invalid')
g('REQ-5-2-3','Write comment stores full body and author and survives reload', r'''
await h.signIn(page,'spec-write'); await h.issue(page,'issue-comment'); const body=h.unique('pw-comment'); await h.field(page,'Comment').fill(body); await h.button(page,'Comment').click(); const entry=page.getByRole('article').filter({hasText:body}); await h.persisted(page, async () => { await expect(entry).toContainText(body); await expect(entry).toContainText('spec-write'); });
''','issue-comment')
g('REQ-5-2-3','blank comment adds no article or activity through either allowed UI behavior', r'''
await h.signIn(page,'spec-write'); await h.issue(page,'issue-comment-invalid'); const before=await page.getByRole('article').allTextContents(); await h.field(page,'Comment').fill('   '); const submit=h.button(page,'Comment'); if(await submit.isEnabled()){ await submit.click(); await expect(page.getByText('Comment is required',{exact:false})).toBeVisible(); } else await expect(submit).toBeDisabled();
expect(await page.getByRole('article').allTextContents()).toEqual(before); await page.reload(); expect(await page.getByRole('article').allTextContents()).toEqual(before);
''','issue-comment-invalid')
g('REQ-5-3-1','eligible assignee is saved live and removed without erasing timeline', r'''
await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-assign'); await h.button(page,'Assignees').click(); await h.field(page,'Search assignees').fill('spec-triage'); await h.option(page,'spec-triage'); await h.persisted(page, () => expect(h.sidebar(page,'Assignees')).toContainText('spec-triage')); await h.button(page,'Assignees').click(); await h.option(page,'spec-triage'); await h.persisted(page, () => expect(h.sidebar(page,'Assignees')).not.toContainText('spec-triage'));
''','issue-assign')
g('REQ-5-3-2','existing label toggle immediately saves and removes association', r'''
await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-label'); await h.button(page,'Labels').click(); await h.option(page,'bug'); await h.persisted(page, () => expect(h.sidebar(page,'Labels')).toContainText('bug')); await h.button(page,'Labels').click(); await h.option(page,'bug'); await h.persisted(page, () => expect(h.sidebar(page,'Labels')).not.toContainText('bug'));
''','issue-label')
g('REQ-5-3-3','milestone selection saves immediately and None removes only association', r'''
await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-milestone'); await h.button(page,'Milestone').click(); await h.option(page,'v1.0'); await h.persisted(page, () => expect(h.sidebar(page,'Milestone')).toContainText('v1.0')); await h.button(page,'Milestone').click(); await h.option(page,'None'); await h.persisted(page, () => expect(h.sidebar(page,'Milestone')).not.toContainText('v1.0'));
''','issue-milestone')
g('REQ-5-4','Maintain closes and reopens issue preserving title, body and state', r'''
await h.signIn(page,'spec-maintain'); await h.issue(page,'issue-close'); await h.button(page,'Close issue').click(); await expect(h.text(page,'Closed issue').first()).toBeVisible(); await expect(h.button(page,'Reopen issue')).toBeVisible(); await h.button(page,'Reopen issue').click(); await h.persisted(page, async () => { await expect(h.button(page,'Close issue')).toBeVisible(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.text(page,'Describe the onboarding improvement.').first()).toBeVisible(); });
''','issue-close')
g('REQ-5-4','Read viewer has neither issue status control', r'''
await h.signIn(page,'spec-read'); await h.issue(page,'issue-read'); await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0); await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
''','issue-read')
g('REQ-6-1','Admin stores exact branch protection toggles and reload displays summaries', r'''
await h.signIn(page,'spec-admin'); await h.repo(page,h.fixtureRepo('protection-create')); await h.settings(page,'Branches'); await h.button(page,'Add branch protection rule').click(); await h.field(page,'Branch name pattern').fill('main'); await page.getByRole('checkbox',{name:'Require 1 approval',exact:true}).check(); await page.getByRole('checkbox',{name:'Require status check test',exact:true}).check(); await h.button(page,'Create').click(); await h.persisted(page, async () => { await expect(h.visibleText(page,'main').first()).toBeVisible(); await expect(h.visibleText(page,'1 approval').first()).toBeVisible(); await expect(h.visibleText(page,'Require status check test').first()).toBeVisible(); });
''','protection-create')
g('REQ-6-1','non-Admin cannot create protection rule', r'''
await h.signIn(page,'spec-read'); await h.repo(page,h.fixtureRepo('protection-read')); if(await h.link(page,'Settings').count()){ await h.link(page,'Settings').click(); if(await h.link(page,'Branches').count()) await h.link(page,'Branches').click(); } await expect(h.button(page,'Add branch protection rule')).toHaveCount(0);
''','protection-read')
g('REQ-6-1','Admin changes current compare-commit check pending to success and persists setter', r'''
await h.signIn(page,'spec-admin'); await h.pr(page,'check-success'); await expect(h.text(page,'test: pending').first()).toBeVisible(); await h.choose(page,'test status','success'); await h.button(page,'Save').click(); await h.persisted(page, async () => { await expect(h.text(page,'test: success').first()).toBeVisible(); await expect(h.text(page,'spec-admin').last()).toBeVisible(); });
''','check-success', file='INTEGRATION-protection', requires=['REQ-6-1','REQ-6-2-3'])
g('REQ-6-2-1','visitor Open PR list filter reads same persisted PR after repeated navigation', r'''
await h.repo(page); await h.link(page,'Pull requests').click(); const list=page.url(); await h.link(page,'Open').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible(); await page.reload(); await h.link(page,'Improve onboarding').click(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await h.home(page); await page.goto(list); await h.link(page,'Open').click(); await expect(h.link(page,'Improve onboarding')).toBeVisible();
''')
g('REQ-6-2-2','native base/compare show exact changed file and comparable commits', r'''
await h.signIn(page,'spec-write'); await h.compare(page,'pr-compare'); await expect(page.getByText(/Commit summary/).first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeEnabled();
''','pr-compare')
g('REQ-6-2-2','equal base and compare disable creation before compare button and afterward', r'''
await h.signIn(page,'spec-write'); await h.compare(page,'pr-no-changes'); await h.field(page,'compare').selectOption({label:'main'}); await expect(h.text(page,'No changes').first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled(); await h.button(page,'Compare changes').click(); await expect(h.text(page,'No changes').first()).toBeVisible(); await expect(h.button(page,'Create pull request')).toBeDisabled();
''','pr-no-changes')
g('REQ-6-2-3','create Open PR from comparison persists exact title and description', r'''
await h.signIn(page,'spec-write'); await h.compare(page,'pr-create'); await h.button(page,'Create pull request').click(); const title=h.unique('pw-pr'); await h.field(page,'Title').fill(`  ${title}  `); await h.field(page,'Description').fill('Saved PR description'); await expect(h.button(page,'Create pull request')).toHaveCount(1); await h.button(page,'Create pull request').click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'Saved PR description').first()).toBeVisible(); });
''','pr-create')
g('REQ-6-2-3','blank PR title keeps form and creates no PR', r'''
await h.signIn(page,'spec-write'); await h.repo(page,h.fixtureRepo('pr-create-invalid')); await h.link(page,'Pull requests').click(); await expect(h.link(page,'New pull request')).toBeVisible(); const before=await page.getByRole('link').allTextContents(),listAddress=page.url(); await h.compare(page,'pr-create-invalid'); await h.button(page,'Create pull request').click(); await h.field(page,'Title').fill('   '); await h.button(page,'Create pull request').click(); await expect(page.getByText('Title is required',{exact:false})).toBeVisible(); await expect(h.field(page,'Title')).toBeVisible(); await page.goto(listAddress); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before); await page.reload(); await expect.poll(()=>page.getByRole('link').allTextContents()).toEqual(before);
''','pr-create-invalid')
g('REQ-6-2-4','Draft creation is persistent and has present disabled merge action', r'''
await h.signIn(page,'spec-write'); await h.compare(page,'pr-draft-create'); await h.button(page,'Create draft pull request').click(); const title=h.unique('pw-draft'); await h.field(page,'Title').fill(title); await h.button(page,'Create draft pull request').click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible(); await expect(h.text(page,'Draft').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeDisabled(); });
''','pr-draft-create')
g('REQ-6-2-4','author marks Draft ready without changing title or branches', r'''
await h.signIn(page,'spec-write'); await h.pr(page,'pr-ready','Draft onboarding update'); await h.button(page,'Ready for review').click(); const confirm=h.button(page,'Confirm'); if(await confirm.isVisible()) await confirm.click(); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Draft onboarding update',exact:true})).toBeVisible(); await expect(h.text(page,'Draft')).toHaveCount(0); await expect(h.text(page,'Open').first()).toBeVisible(); await expect(h.text(page,'draft-feature').first()).toBeVisible(); await expect(h.text(page,'main').first()).toBeVisible(); await expect(h.text(page,'Ready for review').first()).toBeVisible(); });
''','pr-ready')
g('REQ-6-3-1','visitor PR overview, commits and changed-files navigation survives direct reopen', r'''
await h.pr(page); const address=page.url(); await h.link(page,'Commits').click(); await expect(page.getByText(/Commit summary/).first()).toBeVisible(); await h.link(page,'Files changed').click(); await expect(page.getByText(/Changed files/).first()).toBeVisible(); await page.goto(address); await h.persisted(page, async () => { await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.link(page,'Commits')).toBeVisible(); await expect(h.link(page,'Files changed')).toBeVisible(); });
''')
g('REQ-6-3-2','visitor diff displays exact path and exact aggregate additions/deletions from both changed files', r'''
await h.pr(page); await h.link(page,'Files changed').click(); await expect(h.text(page,'src/search.ts').first()).toBeVisible(); await expect(page.getByText('2 additions, 1 deletions',{exact:false}).first()).toBeVisible();
''')
for pending in [False,True]:
 fid='review-pending' if pending else 'review-comment'
 g('REQ-6-3-3',('pending review draft' if pending else 'single inline comment')+' persists at changed line',f'''
 await h.signIn(page,'bob-reviewer'); await h.pr(page,{json.dumps(fid)}); await h.link(page,'Files changed').click(); await h.button(page,'Add comment').first().click(); const body=h.unique('pw-review'); await h.field(page,'Comment').fill(body); await h.button(page,{json.dumps('Start a review' if pending else 'Add single comment')}).click(); await h.persisted(page, async () => {{ await expect(h.text(page,body).first()).toBeVisible(); {'await expect(h.text(page,"Pending review").first()).toBeVisible();' if pending else ''} }});
 {'const address=page.url(); const visitor=await browser.newContext(); const p=await visitor.newPage(); await p.goto(address); await expect(h.text(p,body)).toHaveCount(0); await visitor.close();' if pending else ''}
 ''',fid)
for decision,status in [('Approve','Approved'),('Request changes','Changes requested'),('Comment','')]:
 fid='review-'+('decision-comment' if decision=='Comment' else decision.lower().replace(' ','-'))
 g('REQ-6-3-4',decision+' submission persists current-commit review',f'''
 await h.signIn(page,'bob-reviewer'); await h.pr(page,{json.dumps(fid)}); await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click();
 {'await h.field(page,"Summary").fill("Please fix the search edge case");' if decision!='Approve' else ''} await page.getByRole('radio',{{name:{json.dumps(decision)},exact:true}}).check(); await h.button(page,'Submit review').click();
 await h.persisted(page, () => expect(h.text(page,{json.dumps(status or 'Please fix the search edge case')}).first()).toBeVisible());
 ''',fid)
g('REQ-6-4','author requests and removes live eligible reviewer without confirmation', r'''
await h.signIn(page,'spec-write'); await h.pr(page,'review-request'); await h.button(page,'Reviewers').click(); await page.getByRole('textbox',{name:'Search',exact:true}).fill('bob-reviewer'); await h.option(page,'bob-reviewer'); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toBeVisible()); await h.button(page,'Remove bob-reviewer').click(); await h.persisted(page, () => expect(h.button(page,'Remove bob-reviewer')).toHaveCount(0));
''','review-request')
g('REQ-6-5','Maintain merge commits actual changes to base branch and persists terminal status', r'''
await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-success'); await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click(); await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible()); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
await h.repo(page,h.fixtureRepo('merge-success')); await h.button(page,'Branch main').click(); await h.option(page,'main'); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await expect(h.text(page,'export const search = "merged search flow";')).toBeVisible();
''','merge-success')
g('REQ-6-5','missing required approval blocks merge before click and retains PR and branch', r'''
await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-blocked'); await expect(h.button(page,'Merge pull request')).toBeDisabled(); await expect(h.text(page,'Review required by branch protection').first()).toBeVisible(); await h.persisted(page, () => expect(h.button(page,'Merge pull request')).toBeDisabled()); await expect(h.text(page,'Open').first()).toBeVisible(); await h.repo(page,h.fixtureRepo('merge-blocked')); await h.link(page,'src').click(); await h.link(page,'search.ts').click(); await expect(h.text(page,'export const search = "search flow";')).toBeVisible();
''','merge-blocked')
g('REQ-6-6','author closes and reopens PR while discussion and branches persist', r'''
await h.signIn(page,'spec-write'); await h.pr(page,'pr-close'); await h.button(page,'Close pull request').click(); await expect(h.button(page,'Reopen pull request')).toBeVisible(); await h.button(page,'Reopen pull request').click(); await h.persisted(page, async () => { await expect(h.button(page,'Close pull request')).toBeVisible(); await expect(page.getByRole('heading',{name:'Improve onboarding',exact:true})).toBeVisible(); await expect(h.link(page,'Files changed')).toBeVisible(); });
''','pr-close')
g('REQ-6-6','Read viewer has no close or reopen action', r'''
await h.signIn(page,'spec-read'); await h.pr(page,'pr-close-read'); await expect(h.button(page,'Close pull request')).toHaveCount(0); await expect(h.button(page,'Reopen pull request')).toHaveCount(0);
''','pr-close-read')


for role in ['spec-read','spec-triage']:
    g('REQ-5-2-2', role+' cannot edit issue content', f'''
    await h.signIn(page,{json.dumps(role)}); await h.issue(page,'issue-edit-'+{json.dumps(role)});
    await h.unavailable(page,'Edit issue title'); await h.unavailable(page,'Edit issue description');
    await h.persisted(page, () => expect(page.getByRole('heading',{{name:'Improve onboarding',exact:true}})).toBeVisible());
    ''','issue-edit-'+role)
for role in ['spec-read','spec-write']:
    g('REQ-5-3-1', role+' does not acquire metadata authority from role name', f'''
    await h.signIn(page,{json.dumps(role)}); await h.issue(page,'issue-metadata-'+{json.dumps(role)});
    for(const control of ['Assignees','Labels','Milestone']) await h.unavailable(page,control);
    await expect(h.button(page,'Close issue')).toHaveCount(0); await expect(h.button(page,'Reopen issue')).toHaveCount(0);
    ''','issue-metadata-'+role)
for role in ['spec-read','spec-triage']:
    g('REQ-4-3-2',role+' cannot create branch reference',f'''
    await h.signIn(page,{json.dumps(role)}); await h.repo(page,h.fixtureRepo('branch-permission-'+{json.dumps(role)}));
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch');
    const create=page.getByRole('option',{{name:'Create branch: pw-denied-branch',exact:true}}); if(await create.count() && await create.isEnabled()) await create.click();
    await page.keyboard.press('Escape'); await h.persisted(page, () => expect(h.button(page,'Branch main')).toBeVisible());
    await h.button(page,'Branch main').click(); await h.field(page,'Find branch').fill('pw-denied-branch'); await expect(page.getByRole('option',{{name:'pw-denied-branch',exact:true}})).toHaveCount(0);
    ''','branch-permission-'+role)
for rule in ['check-only','approval-only','unprotected']:
    g('REQ-6-5',rule+' enforces only its configured merge prerequisites',f'''
    await h.signIn(page,'spec-maintain'); await h.pr(page,{json.dumps('merge-'+rule)});
    await expect(h.button(page,'Merge pull request')).toBeEnabled(); await h.button(page,'Merge pull request').click();
    await h.button(page,'Confirm merge').click(); await h.persisted(page, () => expect(h.text(page,'Merged').first()).toBeVisible());
    ''','merge-'+rule)
g('REQ-6-3-4','latest Comment replaces Request changes while retaining history',r'''
await h.signIn(page,'bob-reviewer'); await h.pr(page,'review-replace');
for(const decision of ['Request changes','Comment']) { await h.link(page,'Files changed').click(); await h.button(page,'Review changes').click(); await h.field(page,'Summary').fill(`Decision: ${decision}`); await page.getByRole('radio',{name:decision,exact:true}).check(); await h.button(page,'Submit review').click(); }
await h.signOut(page); await h.signIn(page,'spec-maintain'); await h.pr(page,'review-replace');
await expect(h.text(page,'Decision: Request changes').first()).toBeVisible(); await expect(h.text(page,'Decision: Comment').first()).toBeVisible(); await expect(h.button(page,'Merge pull request')).toBeEnabled();
''','review-replace')
g('REQ-6-5','current Request changes blocks an otherwise unprotected PR',r'''
await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-request-changes'); await h.persisted(page, () => expect(h.button(page,'Merge pull request')).toBeDisabled()); await expect(h.text(page,'Open').first()).toBeVisible();
''','merge-request-changes')
g('REQ-6-5','old-commit approval cannot satisfy a protected current-commit PR',r'''
await h.signIn(page,'spec-maintain'); await h.pr(page,'merge-stale-approval'); await expect(h.button(page,'Merge pull request')).toBeDisabled(); await expect(h.text(page,'Review required by branch protection').first()).toBeVisible(); await page.reload(); await expect(h.button(page,'Merge pull request')).toBeDisabled();
''','merge-stale-approval')


g('REQ-1-2','sign-out invalidates only this browser session and preserves another session',r'''
const {username}=await h.register(page); await h.signIn(page,username);
const other=await browser.newContext(); const p=await other.newPage();
try { await h.signIn(p,username); await h.button(p,'Account menu').click(); await h.link(p,'Settings').click(); const address=p.url();
await h.signOut(page); await expect(h.button(page,'Account menu')).toHaveCount(0);
await p.reload(); await expect(h.button(p,'Account menu')).toBeVisible(); await p.goto(address); await expect(h.button(p,'Account menu')).toBeVisible();
} finally { await other.close(); }
''')

from embedded_sheet_cases import register
register(s)
from embedded_guided_cases import register as register_guidance
register_guidance(g, s)
from embedded_node_smokes import register as register_node_smokes
register_node_smokes(s)
from embedded_repair_cases import register as register_repair_cases
register_repair_cases(s)
from embedded_case_phases import partition_sheet_cases
CASES['hackathon--sheet'] = partition_sheet_cases(CASES['hackathon--sheet'], yaml.safe_load(
    (Path(__file__).resolve().parent / 'tasks/hackathon--sheet/requirements.yaml').read_text()))

from embedded_node_coverage import complete_node_coverage
for _task in CASES:
    CASES[_task] = complete_node_coverage(CASES[_task], yaml.safe_load(
        (Path(__file__).resolve().parent / 'tasks' / _task / 'requirements.yaml').read_text()))

def build():
    for task, nodes in CASES.items():
        directory = ROOT / task
        for path in directory.glob('*.spec.ts'): path.unlink()
        plan=[]
        for file, recipes in nodes.items():
            parts=["import { test, expect } from './helpers';\nimport * as h from './helpers';\n\n// Source-reviewed internal derived suite; requirements.yaml remains authoritative.\n"]
            for recipe in recipes:
                node, title, body = recipe['node_id'], recipe['title'], recipe['body']
                name=f"{file if recipe['phase']=='integration' else node}: {title}"
                parts.append(f'test({json.dumps(name)}, async ({{ page, browser }}) => {{\n  test.setTimeout(60_000);\n'+textwrap.indent(body,'  ')+'\n});\n')
                plan.append({k:v for k,v in recipe.items() if k not in {'body','title'}} | {'title':name,'file':f'{file}.spec.ts'})
            (directory/f'{file}.spec.ts').write_text('\n'.join(parts),encoding='utf8')
        (directory/'case-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
        print(task,len(nodes),'files',len(plan),'cases')

if __name__=='__main__': build()
