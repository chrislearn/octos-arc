'use strict';
const {collection} = require('../lib/collection');
const {accounts, sessions} = require('./accounts');

const fixtureOrgs = ['spec-org-file-create', 'spec-org-file-history', 'spec-org-issue-create',
  'spec-org-pr-ready', 'spec-org-review-request', 'spec-org-team-members', 'spec-org-team-cycle',
  'spec-org-existing', 'spec-org-team-create', 'spec-org-team-invalid',
  'spec-org-member-add', 'spec-org-member-invalid'];
const fixtureRepos = ['spec-file-create', 'spec-file-history', 'spec-issue-create',
  'spec-pr-ready', 'spec-review-request', 'spec-team-members', 'spec-team-cycle',
  'spec-team-create', 'spec-team-invalid', 'spec-member-add', 'spec-member-invalid'];
const fixtureMembers = ['acc-spec-owner', 'acc-spec-admin', 'acc-spec-write',
  'acc-spec-maintain', 'acc-spec-triage', 'acc-spec-read', 'acc-bob-reviewer'];

const organizations = collection('organizations', {
  idKey: 'id',
  initial: [
    {
      id: 'org-acme-demo',
      identifier: 'acme-demo',
      display_name: 'Acme Demo',
      members: ['acc-spec-owner', 'acc-bob-reviewer'],
      owners: ['acc-spec-owner']
    },
    ...fixtureOrgs.map(identifier => ({
      id: 'org-' + identifier,
      identifier,
      display_name: identifier === 'spec-org-existing' ? 'Existing Organization' : identifier,
      members: fixtureMembers,
      owners: ['acc-spec-owner'],
      teams: [
        {id: 'team-' + identifier + '-platform', name: 'platform-team', parent_id: null, direct_members: []},
        {id: 'team-' + identifier + '-frontend', name: 'frontend-team', parent_id: 'team-' + identifier + '-platform', direct_members: []},
        {id: 'team-' + identifier + '-child', name: 'frontend-child', parent_id: 'team-' + identifier + '-frontend', direct_members: []}
      ]
    }))
  ]
});

const mainFiles = {'README.md': 'search flow', 'src/search.ts': 'export const search = "search flow";'};
const featureFiles = {'README.md': 'search flow', 'src/search.ts': 'export const search = "merged search flow";', 'main-only.md': 'feature-only content'};
const mainBranch = {
  name: 'main',
  base: null,
  files: mainFiles,
  commit_message: 'Document search flow',
  author: 'acc-alice-dev',
  committed_at: '2026-09-01T12:00:00Z',
  parent: {files: {}, commit_message: 'Initialize empty repository', author: 'acc-alice-dev', committed_at: '2026-08-31T12:00:00Z'}
};
const featureBranch = {
  name: 'feature-search',
  base: 'main',
  files: featureFiles,
  commit_message: 'Implement search flow',
  author: 'acc-alice-dev',
  committed_at: '2026-09-02T12:00:00Z',
  parent: null
};

function repo(id, ownerType, ownerId, name, visibility, issues, pulls) {
  return {
    id,
    owner_type: ownerType,
    owner_id: ownerId,
    name,
    visibility,
    updated_at: '2026-09-02T12:00:00Z',
    description: 'Search flow documentation repository',
    default_branch: 'main',
    branches: [mainBranch, featureBranch],
    issues,
    pull_requests: pulls
  };
}

const repositories = collection('repositories', {
  idKey: 'id',
  initial: [
    repo('repo-alice-acme-docs', 'account', 'acc-alice-dev', 'acme-docs', 'Public',
      [{number: 1, title: 'Improve onboarding', description: 'Describe the onboarding improvement.', status: 'Open', author: 'acc-alice-dev'},
       {number: 2, title: 'Legacy welcome text', description: 'Previous welcome wording', status: 'Closed', author: 'acc-alice-dev'}],
      [{number: 1, title: 'Improve onboarding', description: 'Describe the onboarding improvement.', status: 'Open', author: 'acc-alice-dev', base: 'main', compare: 'feature-search'},
       {number: 2, title: 'Fix search', status: 'Closed', author: 'acc-alice-dev', base: 'main', compare: 'feature-search'}]),
    repo('repo-org-acme-docs', 'organization', 'org-acme-demo', 'acme-docs', 'Public', [], []),
    repo('repo-org-acme-docs-org', 'organization', 'org-acme-demo', 'acme-docs-org', 'Public', [], []),
    repo('repo-alice-secret-research', 'account', 'acc-alice-dev', 'secret-research', 'Private',
      [{number: 1, title: 'Improve onboarding', description: 'Describe the onboarding improvement.', status: 'Open', author: 'acc-alice-dev'},
       {number: 2, title: 'Legacy welcome text', description: 'Previous welcome wording', status: 'Closed', author: 'acc-alice-dev'}],
      [{number: 1, title: 'Improve onboarding', description: 'Describe the onboarding improvement.', status: 'Open', author: 'acc-alice-dev', base: 'main', compare: 'feature-search'},
       {number: 2, title: 'Fix search', status: 'Closed', author: 'acc-alice-dev', base: 'main', compare: 'feature-search'}]),
    repo('repo-org-secret-research', 'organization', 'org-acme-demo', 'secret-research', 'Private', [], []),
    ...fixtureRepos.map(name => repo('repo-' + name, 'organization', 'org-spec-org-' + name.slice('spec-'.length), name,
      name === 'spec-member-add' ? 'Private' : 'Public', [], []))
  ]
});

const grants = collection('repository_grants', {
  idKey: 'id',
  initial: [
    {id: 'grant-1', repository_id: 'repo-alice-acme-docs', subject_type: 'account', subject_id: 'acc-spec-admin', role: 'Admin'},
    {id: 'grant-2', repository_id: 'repo-alice-acme-docs', subject_type: 'account', subject_id: 'acc-spec-write', role: 'Write'},
    {id: 'grant-3', repository_id: 'repo-alice-acme-docs', subject_type: 'account', subject_id: 'acc-spec-maintain', role: 'Maintain'},
    {id: 'grant-4', repository_id: 'repo-alice-acme-docs', subject_type: 'account', subject_id: 'acc-spec-triage', role: 'Triage'},
    {id: 'grant-5', repository_id: 'repo-alice-acme-docs', subject_type: 'account', subject_id: 'acc-spec-read', role: 'Read'},
    {id: 'grant-6', repository_id: 'repo-alice-acme-docs', subject_type: 'account', subject_id: 'acc-bob-reviewer', role: 'Write'},
    {id: 'grant-7', repository_id: 'repo-org-acme-docs', subject_type: 'account', subject_id: 'acc-spec-admin', role: 'Admin'},
    {id: 'grant-8', repository_id: 'repo-org-acme-docs', subject_type: 'account', subject_id: 'acc-spec-write', role: 'Write'},
    {id: 'grant-9', repository_id: 'repo-org-acme-docs', subject_type: 'account', subject_id: 'acc-spec-maintain', role: 'Maintain'},
    {id: 'grant-10', repository_id: 'repo-org-acme-docs', subject_type: 'account', subject_id: 'acc-spec-triage', role: 'Triage'},
    {id: 'grant-11', repository_id: 'repo-org-acme-docs', subject_type: 'account', subject_id: 'acc-spec-read', role: 'Read'},
    {id: 'grant-12', repository_id: 'repo-org-acme-docs', subject_type: 'account', subject_id: 'acc-bob-reviewer', role: 'Write'},
    ...['repo-org-acme-docs-org'].flatMap(rid => [
      {id: 'grant-' + rid + '-admin', repository_id: rid, subject_type: 'account', subject_id: 'acc-spec-admin', role: 'Admin'},
      {id: 'grant-' + rid + '-write', repository_id: rid, subject_type: 'account', subject_id: 'acc-spec-write', role: 'Write'},
      {id: 'grant-' + rid + '-maintain', repository_id: rid, subject_type: 'account', subject_id: 'acc-spec-maintain', role: 'Maintain'},
      {id: 'grant-' + rid + '-triage', repository_id: rid, subject_type: 'account', subject_id: 'acc-spec-triage', role: 'Triage'},
      {id: 'grant-' + rid + '-read', repository_id: rid, subject_type: 'account', subject_id: 'acc-spec-read', role: 'Read'},
      {id: 'grant-' + rid + '-bob', repository_id: rid, subject_type: 'account', subject_id: 'acc-bob-reviewer', role: 'Write'}
    ]),
    ...fixtureRepos.flatMap(name => [
      {id: 'grant-' + name + '-admin', repository_id: 'repo-' + name, subject_type: 'account', subject_id: 'acc-spec-admin', role: 'Admin'},
      {id: 'grant-' + name + '-write', repository_id: 'repo-' + name, subject_type: 'account', subject_id: 'acc-spec-write', role: 'Write'},
      {id: 'grant-' + name + '-maintain', repository_id: 'repo-' + name, subject_type: 'account', subject_id: 'acc-spec-maintain', role: 'Maintain'},
      {id: 'grant-' + name + '-triage', repository_id: 'repo-' + name, subject_type: 'account', subject_id: 'acc-spec-triage', role: 'Triage'},
      {id: 'grant-' + name + '-read', repository_id: 'repo-' + name, subject_type: 'account', subject_id: 'acc-spec-read', role: 'Read'},
      {id: 'grant-' + name + '-bob', repository_id: 'repo-' + name, subject_type: 'account', subject_id: 'acc-bob-reviewer', role: 'Write'}
    ])
  ]
});

function currentAccount(req) {
  const sessionId = req.get('x-session-id');
  const session = sessionId && sessions.get(sessionId);
  if (!session || !session.active) return null;
  return accounts.get(session.account_id);
}

function ownerLabel(record) {
  if (record.owner_type === 'organization') {
    const org = organizations.get(record.owner_id);
    return org ? org.identifier : null;
  }
  const account = accounts.get(record.owner_id);
  return account ? account.username : null;
}

function canRead(record, account) {
  if (record.visibility === 'Public') return true;
  if (!account) return false;
  if (record.owner_type === 'account') return record.owner_id === account.id;
  const org = organizations.get(record.owner_id);
  if (org && org.owners.includes(account.id)) return true;
  return grants.list(g => g.repository_id === record.id && g.subject_type === 'account' && g.subject_id === account.id).length > 0;
}

function findRepository(owner, name) {
  const account = accounts.list(a => a.username === owner)[0];
  const org = organizations.list(o => o.identifier === owner)[0];
  if (!account && !org) return null;
  const ownerId = account ? account.id : org.id;
  const ownerType = account ? 'account' : 'organization';
  return repositories.list(r => r.owner_id === ownerId && r.owner_type === ownerType && r.name === name)[0] || null;
}

module.exports = (app) => {
  app.get('/api/organizations', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const results = organizations.list(o =>
      o.members.includes(account.id) || o.owners.includes(account.id))
      .map(o => ({identifier: o.identifier, display_name: o.display_name}));
    res.json(results);
  });

  app.post('/api/organizations', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const body = req.body || {};
    const name = typeof body.name === 'string' ? body.name.trim() : '';
    const displayName = typeof body.display_name === 'string' ? body.display_name.trim() : '';
    const errors = {};
    if (!name || name.length > 39 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name)) {
      errors.name = 'Organization name format is invalid';
    } else if (organizations.list(o => o.identifier === name).length) {
      errors.name = 'Organization name already exists';
    }
    if (!displayName || displayName.length > 100) errors.display_name = 'Display name is required';
    if (Object.keys(errors).length) return res.status(422).json({errors});
    const organization = organizations.create({
      id: 'org-' + name + '-' + Date.now().toString(36),
      identifier: name,
      display_name: displayName,
      members: [account.id],
      owners: [account.id],
      created_at: new Date().toISOString()
    });
    res.status(201).json({identifier: organization.identifier, display_name: organization.display_name});
  });

  app.post('/api/organizations/:identifier/members', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const org = organizations.list(o => o.identifier === req.params.identifier)[0];
    if (!org) return res.status(404).json({error: 'not found'});
    if (!org.owners.includes(account.id)) {
      return res.status(403).json({error: 'Only organization owners can add members'});
    }
    const body = req.body || {};
    const identifier = typeof body.username === 'string' ? body.username.trim() : '';
    const role = body.role === 'Owner' ? 'Owner' : body.role === 'Member' ? 'Member' : null;
    const errors = {};
    const lowered = identifier.toLowerCase();
    const target = identifier
      ? accounts.list(a => a.username === identifier ||
          (typeof a.email === 'string' && a.email.toLowerCase() === lowered))[0]
      : null;
    if (!target) errors.username = 'Account not found';
    else if (org.members.includes(target.id)) errors.username = 'Account is already a member';
    if (!role) errors.role = 'Role is invalid';
    if (Object.keys(errors).length) return res.status(422).json({errors});
    organizations.transact(items => {
      const record = items.find(o => o.id === org.id);
      record.members = record.members || [];
      record.members.push(target.id);
      if (role === 'Owner') {
        record.owners = record.owners || [];
        record.owners.push(target.id);
      }
    });
    res.status(201).json({username: target.username, role});
  });

  app.get('/api/organizations/:identifier/members', (req, res) => {
    const org = organizations.list(o => o.identifier === req.params.identifier)[0];
    if (!org) return res.status(404).json({error: 'not found'});
    const members = org.members.map(id => {
      const account = accounts.get(id);
      return account ? {username: account.username,
        role: org.owners.includes(id) ? 'Owner' : 'Member'} : null;
    }).filter(Boolean);
    res.json(members);
  });

  app.get('/api/organizations/:identifier', (req, res) => {
    const org = organizations.list(o => o.identifier === req.params.identifier)[0];
    if (!org) return res.status(404).json({error: 'not found'});
    const account = currentAccount(req);
    res.json({identifier: org.identifier, display_name: org.display_name,
      is_owner: !!(account && org.owners.includes(account.id))});
  });

  app.get('/api/organizations/:identifier/repositories', (req, res) => {
    const org = organizations.list(o => o.identifier === req.params.identifier)[0];
    if (!org) return res.status(404).json({error: 'not found'});
    const account = currentAccount(req);
    const results = repositories.list(r => r.owner_type === 'organization' && r.owner_id === org.id)
      .filter(r => canRead(r, account))
      .map(r => ({name: r.name, description: r.description, visibility: r.visibility,
        updated_at: r.updated_at || null}));
    res.json(results);
  });

  app.get('/api/repositories', (req, res) => {
    const account = currentAccount(req);
    const q = typeof req.query.q === 'string' ? req.query.q.trim().toLowerCase() : '';
    const results = repositories.list(r => canRead(r, account))
      .filter(r => !q || r.name.toLowerCase().includes(q) || (ownerLabel(r) || '').toLowerCase().includes(q))
      .map(r => ({owner: ownerLabel(r), name: r.name, visibility: r.visibility, description: r.description}));
    res.json(results);
  });

  app.get('/api/repositories/:owner/:name', (req, res) => {
    const account = currentAccount(req);
    const record = findRepository(req.params.owner, req.params.name);
    if (!record) return res.status(404).json({error: 'not found'});
    if (!canRead(record, account)) {
      return res.status(account ? 403 : 404).json({error: account ? 'Access denied' : 'not found'});
    }
    const branch = record.branches.find(b => b.name === record.default_branch) || record.branches[0];
    const ownerName = record.owner_type === 'organization'
      ? ((organizations.get(record.owner_id) || {}).display_name || ownerLabel(record))
      : ownerLabel(record);
    res.json({
      owner: ownerName,
      owner_type: record.owner_type,
      owner_identifier: record.owner_type === 'organization'
        ? ownerLabel(record) : (accounts.get(record.owner_id) || {}).username || null,
      name: record.name,
      visibility: record.visibility,
      description: record.description,
      default_branch: record.default_branch,
      files: branch ? Object.keys(branch.files).sort() : [],
      branches: record.branches.map(b => b.name)
    });
  });

  app.get('/api/repositories/:owner/:name/branches/:branch/files/*path', (req, res) => {
    const account = currentAccount(req);
    const record = findRepository(req.params.owner, req.params.name);
    if (!record || !canRead(record, account)) return res.status(404).json({error: 'not found'});
    const branch = record.branches.find(b => b.name === req.params.branch);
    const filePath = (req.params.path || []).join('/');
    if (!branch || !(filePath in branch.files)) return res.status(404).json({error: 'not found'});
    res.json({path: filePath, content: branch.files[filePath]});
  });
};
// Named export attached after the route function so other modules reuse the
// canonical organizations collection instead of independent fallbacks.
module.exports.organizations = organizations;
