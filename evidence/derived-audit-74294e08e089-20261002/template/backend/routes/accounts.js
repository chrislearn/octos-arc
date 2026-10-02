'use strict';
const crypto = require('crypto');
const {collection} = require('../lib/collection');

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, 64).toString('hex');
  return salt + ':' + hash;
}
function verifyPassword(password, stored) {
  const [salt, hash] = String(stored).split(':');
  if (!salt || !hash) return false;
  const candidate = crypto.scryptSync(password, salt, 64).toString('hex');
  return crypto.timingSafeEqual(Buffer.from(candidate), Buffer.from(hash));
}

const accounts = collection('accounts', {
  idKey: 'id',
  initial: [{
    id: 'acc-alice-dev',
    username: 'alice-dev',
    email: 'alice.dev@example.test',
    passwordHash: hashPassword('Valid-password-123!'),
    verified: true,
    available: true
  }, {
    id: 'acc-spec-new-member',
    username: 'spec-new-member',
    email: 'spec-new-member@example.test',
    passwordHash: hashPassword('Valid-password-123!'),
    verified: true,
    available: true
  }, {
    id: 'acc-spec-unavailable',
    username: 'spec-unavailable',
    email: 'spec-unavailable@example.test',
    passwordHash: hashPassword('Valid-password-123!'),
    verified: true,
    available: false
  }, ...['bob-reviewer', 'spec-owner', 'spec-admin', 'spec-write', 'spec-maintain', 'spec-triage', 'spec-read'].map(username => ({
    id: 'acc-' + username,
    username,
    email: username + '@example.test',
    passwordHash: hashPassword('Valid-password-123!'),
    verified: true,
    available: true
  }))]
});
const sessions = collection('sessions', {idKey: 'id', initial: []});

function validEmail(email) {
  if (!email || email.length > 254) return false;
  const parts = email.split('@');
  if (parts.length !== 2) return false;
  const domain = parts[1];
  if (!domain.includes('.')) return false;
  return domain.split('.').every(label => label.length > 0);
}
function validPassword(password) {
  return typeof password === 'string' && password.length >= 12 && password.length <= 128 &&
    /[A-Z]/.test(password) && /[a-z]/.test(password) && /[0-9]/.test(password) &&
    /[^A-Za-z0-9]/.test(password) && !/\s/.test(password);
}

module.exports = (app) => {
  app.post('/api/accounts', (req, res) => {
    const body = req.body || {};
    const username = typeof body.username === 'string' ? body.username.trim() : '';
    const email = typeof body.email === 'string' ? body.email.trim() : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const confirm = typeof body.confirm === 'string' ? body.confirm : '';
    const errors = {};
    if (!username || username.length > 39 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(username)) {
      errors.username = 'Username format is invalid';
    } else if (accounts.list().some(a => a.username === username)) {
      errors.username = 'Username already exists';
    }
    if (!validEmail(email)) {
      errors.email = 'Email format is invalid';
    } else if (accounts.list().some(a => a.email === email)) {
      errors.email = 'Email already exists';
    }
    if (!validPassword(password)) errors.password = 'Password requirements are not satisfied';
    if (password !== confirm) errors.confirm = 'Passwords do not match';
    if (body.terms !== true) errors.terms = 'Agree to terms is required';
    if (Object.keys(errors).length) return res.status(422).json({errors});
    const account = accounts.create({
      id: 'acc-' + crypto.randomUUID(),
      username, email,
      passwordHash: hashPassword(password),
      verified: true
    });
    res.status(201).json({id: account.id, username: account.username});
  });

  app.post('/api/session', (req, res) => {
    const body = req.body || {};
    const identifier = typeof body.username === 'string' ? body.username.trim() : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const account = accounts.list().find(a => a.username === identifier || a.email === identifier);
    if (!account || account.available === false ||
        !verifyPassword(password, account.passwordHash)) {
      return res.status(401).json({error: 'Invalid credentials'});
    }
    const session = sessions.create({
      id: crypto.randomUUID(),
      account_id: account.id,
      active: true
    });
    res.status(201).json({id: account.id, username: account.username, sessionId: session.id});
  });

  app.get('/api/session', (req, res) => {
    const sessionId = req.get('x-session-id');
    const session = sessionId && sessions.get(sessionId);
    if (!session || !session.active) return res.status(401).json({error: 'Not signed in'});
    const account = accounts.get(session.account_id);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    res.json({id: account.id, username: account.username});
  });

  app.post('/api/recovery/reset', (req, res) => {
    const body = req.body || {};
    const email = typeof body.email === 'string' ? body.email.trim() : '';
    const code = typeof body.code === 'string' ? body.code : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const confirm = typeof body.confirm === 'string' ? body.confirm : '';
    const errors = {};
    const account = email ? accounts.list().find(a => a.email === email) : null;
    if (!account) errors.email = 'Email is not registered';
    if (code !== '123456') errors.code = 'Verification code is invalid';
    if (!validPassword(password)) errors.password = 'Password requirements are not satisfied';
    if (password !== confirm) errors.confirm = 'Passwords do not match';
    if (Object.keys(errors).length) return res.status(422).json({errors});
    accounts.transact(items => {
      const record = items.find(a => a.email === email);
      record.passwordHash = hashPassword(password);
    });
    res.status(200).json({updated: true});
  });

  app.post('/api/password', (req, res) => {
    const sessionId = req.get('x-session-id');
    const session = sessionId && sessions.get(sessionId);
    if (!session || !session.active) return res.status(401).json({error: 'Not signed in'});
    const account = accounts.get(session.account_id);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const body = req.body || {};
    const current = typeof body.current === 'string' ? body.current : '';
    const password = typeof body.password === 'string' ? body.password : '';
    const confirm = typeof body.confirm === 'string' ? body.confirm : '';
    const errors = {};
    if (!current) errors.current = 'Current password is required';
    else if (!verifyPassword(current, account.passwordHash)) errors.current = 'Current password is incorrect';
    if (!validPassword(password)) errors.password = 'Password requirements are not satisfied';
    if (password !== confirm) errors.confirm = 'Password confirmation does not match';
    if (Object.keys(errors).length) return res.status(422).json({errors});
    accounts.transact(items => {
      const record = items.find(a => a.id === account.id);
      record.passwordHash = hashPassword(password);
    });
    res.status(200).json({updated: true});
  });

  app.delete('/api/session', (req, res) => {
    const sessionId = req.get('x-session-id');
    const session = sessionId && sessions.get(sessionId);
    if (session) sessions.patch(sessionId, {active: false});
    res.status(204).end();
  });
};
// Named exports attached after the route function so other modules reuse the
// canonical account/session collections instead of independent fallbacks.
module.exports.accounts = accounts;
module.exports.sessions = sessions;
