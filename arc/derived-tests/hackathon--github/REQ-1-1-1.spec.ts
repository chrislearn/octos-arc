import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-1-1: requirement scenario 1", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click(); await h.field(page,'Username').fill('nora-demo'); await h.field(page,'Email').fill('nora.demo@example.test'); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD); await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible(); await h.field(page,'Username or email').fill('nora.demo@example.test'); await h.field(page,'Password').fill(h.PASSWORD); await h.button(page,'Sign in').click(); await h.persisted(page,()=>expect(h.containsValue(page,'nora-demo').first()).toBeVisible());
});

test("REQ-1-1-1: requirement scenario 2", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click(); await h.field(page,'Username').fill('-invalid-demo'); await h.field(page,'Email').fill('invalid.username@example.test'); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD); await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.text(page,'Username format is invalid')).toBeVisible(); await expect(h.field(page,'Username')).toHaveValue('-invalid-demo'); for(const label of ['Email','Password','Confirm password']) await expect(h.field(page,label)).toBeVisible(); await expect(h.field(page,'Username or email')).toHaveCount(0);
});

test("REQ-1-1-1: requirement scenario 3", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click(); await h.field(page,'Username').fill('invalid-email-demo'); await h.field(page,'Email').fill('not-an-email'); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD); await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.text(page,'Email format is invalid')).toBeVisible(); await expect(h.field(page,'Email')).toHaveValue('not-an-email'); await expect(h.field(page,'Username')).toHaveValue('invalid-email-demo'); await expect(h.field(page,'Username or email')).toHaveCount(0);
});

test("REQ-1-1-1: registration entry accepts valid account and redirects to sign-in without exposing password", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await expect(h.link(page,'Create an account')).toHaveCount(1); await h.link(page,'Create an account').click();
    for(const label of ['Username','Email','Password','Confirm password']) await expect(h.field(page,label)).toHaveCount(1);
    await h.maskedPasswords(page,['Password','Confirm password']);
    await expect(page.getByRole('checkbox',{name:'Agree to the terms',exact:true})).not.toBeChecked(); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.register(page); await expect(h.field(page,'Username or email')).toBeVisible(); await expect(page.locator('body')).not.toContainText(h.PASSWORD);
});

test("REQ-1-1-1: all invalid fields show errors together and preserve attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill('-invalid'); await h.field(page,'Email').fill('not-an-email'); await h.field(page,'Password').fill('short'); await h.field(page,'Confirm password').fill('different'); await h.button(page,'Create account').click();
    for(const message of ['Username format is invalid','Email format is invalid','Password requirements are not satisfied','Agree to terms is required']) await expect(page.getByText(message,{exact:false})).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue('-invalid'); await expect(h.field(page,'Email')).toHaveValue('not-an-email'); await h.maskedPasswords(page,['Password','Confirm password']); await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue(''); await expect(h.button(page,'Create account')).toBeEnabled();
});

test("REQ-1-1-1: duplicate username preserves both attempted non-sensitive values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click(); const email=`${h.unique()}@example.test`;
    await h.field(page,'Username').fill('alice-dev'); await h.field(page,'Email').fill(email); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD); await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(page.getByText('Username already exists',{exact:false})).toBeVisible(); await expect(h.field(page,'Username')).toHaveValue('alice-dev'); await expect(h.field(page,'Email')).toHaveValue(email);
});

test("REQ-1-1-1: isolated registration rejection 1: Username; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Username").fill("-invalid");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Username format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue("-invalid");
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 2: Username; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Username").fill("invalid-");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Username format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue("invalid-");
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 3: Username; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Username").fill("has--hyphens");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Username format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue("has--hyphens");
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 4: Username; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Username").fill("Uppercase");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Username format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue("Uppercase");
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 5: Username; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Username").fill("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Username format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 6: Username; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Username").fill("bad_name");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Username format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue("bad_name");
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 7: Email; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Email").fill("two@@example.test");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Email format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue("two@@example.test");
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 8: Email; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Email").fill("missing@dot");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Email format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue("missing@dot");
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 9: Email; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Email").fill("empty@.test");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Email format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue("empty@.test");
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 10: Email; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Email").fill("empty@example..test");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Email format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue("empty@example..test");
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 11: Email; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Email").fill("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@example.test");

    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Email format is invalid").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@example.test");
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 12: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("Aa1!xxxxxxx");
    await h.field(page,"Confirm password").fill("Aa1!xxxxxxx");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 13: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("Aa1!xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx");
    await h.field(page,"Confirm password").fill("Aa1!xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 14: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("lowercase-123!");
    await h.field(page,"Confirm password").fill("lowercase-123!");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 15: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("UPPERCASE-123!");
    await h.field(page,"Confirm password").fill("UPPERCASE-123!");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 16: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("Password-only!");
    await h.field(page,"Confirm password").fill("Password-only!");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 17: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("Password12345");
    await h.field(page,"Confirm password").fill("Password12345");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 18: Password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Password").fill("Valid pass-123!");
    await h.field(page,"Confirm password").fill("Valid pass-123!");
    await h.button(page,'Create account').click();await expect(h.containsValue(page,"Password requirements are not satisfied").first()).toBeVisible();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: isolated registration rejection 19: Confirm password; correction creates exactly the attempted identity", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    const username=h.unique('boundary'), email=`${username}@example.test`;
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check();
    await h.field(page,"Confirm password").fill("Other-password-456!");

    await h.button(page,'Create account').click();
    await expect(h.field(page,'Username')).toHaveValue(username);
    await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await expect(h.field(page,'Username or email')).toHaveCount(0); await expect(h.button(page,'Create account')).toBeEnabled();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: duplicate email retains identity; correcting email does not encounter a partially created username", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const username=h.unique('duplicate-email'), email='alice.dev@example.test';
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username')).toHaveValue(username); await expect(h.field(page,'Email')).toHaveValue(email);
    await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue('');
    await h.field(page,'Email').fill(`${username}@example.test`); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click(); await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: username legal length 1 is accepted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const username='z';
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(`${h.unique()}@example.test`);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: username legal length 39 is accepted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const username=h.unique('u').padEnd(39,'x');
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(`${h.unique()}@example.test`);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username or email')).toBeVisible();
});

test("REQ-1-1-1: email legal length 254 is accepted", async ({ page, browser }) => {
  test.setTimeout(60_000);
  const username=h.unique('email-boundary'), email=username.padEnd(241,'x')+'@example.test'; expect(email.length).toBe(254);
    await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
    await h.field(page,'Username').fill(username); await h.field(page,'Email').fill(email);
    await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD);
    await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
    await expect(h.field(page,'Username or email')).toBeVisible();
});
