import { test, expect } from './helpers';
import * as h from './helpers';

// Source-reviewed internal derived suite; requirements.yaml remains authoritative.

test("REQ-1-1-1: registration entry accepts valid account and redirects to sign-in without exposing password", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await expect(h.link(page,'Create an account')).toHaveCount(1); await h.link(page,'Create an account').click();
  for(const label of ['Username','Email','Password','Confirm password']) await expect(h.field(page,label)).toHaveCount(1);
  await expect(page.getByRole('checkbox',{name:'Agree to the terms',exact:true})).not.toBeChecked(); await expect(h.button(page,'Create account')).toBeEnabled();
  await h.register(page); await expect(h.field(page,'Username or email')).toBeVisible(); await expect(page.locator('body')).not.toContainText(h.PASSWORD);
});

test("REQ-1-1-1: all invalid fields show errors together and clear sensitive values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click();
  await h.field(page,'Username').fill('-invalid'); await h.field(page,'Email').fill('not-an-email'); await h.field(page,'Password').fill('short'); await h.field(page,'Confirm password').fill('different'); await h.button(page,'Create account').click();
  for(const message of ['Username format is invalid','Email format is invalid','Password requirements are not satisfied','Agree to terms is required']) await expect(page.getByText(message,{exact:false})).toBeVisible();
  await expect(h.field(page,'Username')).toHaveValue('-invalid'); await expect(h.field(page,'Email')).toHaveValue('not-an-email'); await expect(h.field(page,'Password')).toHaveValue(''); await expect(h.field(page,'Confirm password')).toHaveValue(''); await expect(h.button(page,'Create account')).toBeEnabled();
});

test("REQ-1-1-1: duplicate username preserves both attempted non-sensitive values", async ({ page, browser }) => {
  test.setTimeout(60_000);
  await h.home(page); await h.link(page,'Sign in').click(); await h.link(page,'Create an account').click(); const email=`${h.unique()}@example.test`;
  await h.field(page,'Username').fill('alice-dev'); await h.field(page,'Email').fill(email); await h.field(page,'Password').fill(h.PASSWORD); await h.field(page,'Confirm password').fill(h.PASSWORD); await page.getByRole('checkbox',{name:'Agree to the terms',exact:true}).check(); await h.button(page,'Create account').click();
  await expect(page.getByText('Username already exists',{exact:false})).toBeVisible(); await expect(h.field(page,'Username')).toHaveValue('alice-dev'); await expect(h.field(page,'Email')).toHaveValue(email);
});
