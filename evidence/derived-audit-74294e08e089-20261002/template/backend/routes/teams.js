'use strict';
const crypto = require('crypto');
const {accounts, sessions} = require('./accounts');
const {organizations} = require('./repositories');
const {HttpError} = require('../lib/errors');

function currentAccount(req) {
  const sessionId = req.get('x-session-id');
  const session = sessionId && sessions.get(sessionId);
  if (!session || !session.active) return null;
  return accounts.get(session.account_id);
}

function findOrg(identifier) {
  return organizations.list(o => o.identifier === identifier)[0] || null;
}

function validTeamName(name) {
  return typeof name === 'string' && name.length >= 1 && name.length <= 50 &&
    /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name);
}

function findTeam(org, key) {
  return (org.teams || []).find(t => t.name === key || t.id === key) || null;
}

function teamMembers(team) {
  return (team.direct_members || []).map(id => {
    const account = accounts.get(id);
    return account ? {username: account.username} : null;
  }).filter(Boolean);
}

module.exports = (app) => {
  app.get('/api/organizations/:identifier/teams', (req, res) => {
    const org = findOrg(req.params.identifier);
    if (!org) return res.status(404).json({error: 'not found'});
    res.json((org.teams || []).map(t => ({
      id: t.id, name: t.name, parent_id: t.parent_id || null})));
  });

  app.post('/api/organizations/:identifier/teams', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const org = findOrg(req.params.identifier);
    if (!org) return res.status(404).json({error: 'not found'});
    if (!org.owners.includes(account.id)) {
      return res.status(403).json({error: 'Only organization owners can create teams'});
    }
    const body = req.body || {};
    const name = typeof body.name === 'string' ? body.name.trim() : '';
    const description = typeof body.description === 'string' ? body.description.trim() : '';
    const parentId = body.parent_id || null;
    const errors = {};
    if (!validTeamName(name)) errors.name = 'Team name format is invalid';
    else if ((org.teams || []).some(t => t.name === name)) errors.name = 'Team name already exists';
    if (parentId && !(org.teams || []).some(t => t.id === parentId)) {
      errors.parent_id = 'Parent team must belong to this organization';
    }
    if (Object.keys(errors).length) return res.status(422).json({errors});
    const team = {
      id: 'team-' + crypto.randomUUID(),
      name,
      description: description || null,
      parent_id: parentId,
      creator: account.id,
      created_at: new Date().toISOString(),
      direct_members: []
    };
    organizations.transact(items => {
      const record = items.find(o => o.id === org.id);
      record.teams = record.teams || [];
      record.teams.push(team);
    });
    res.status(201).json({id: team.id, name: team.name, parent_id: team.parent_id});
  });

  app.get('/api/organizations/:identifier/teams/:team', (req, res) => {
    const org = findOrg(req.params.identifier);
    if (!org) return res.status(404).json({error: 'not found'});
    const team = findTeam(org, req.params.team);
    if (!team) return res.status(404).json({error: 'not found'});
    res.json({id: team.id, name: team.name, description: team.description || null,
      parent_id: team.parent_id || null, members: teamMembers(team)});
  });

  app.patch('/api/organizations/:identifier/teams/:team', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const org = findOrg(req.params.identifier);
    if (!org) return res.status(404).json({error: 'not found'});
    if (!org.owners.includes(account.id)) {
      return res.status(403).json({error: 'Only organization owners can change team settings'});
    }
    const body = req.body || {};
    const parentId = body.parent_id || null;
    let updated = null;
    organizations.transact(items => {
      const record = items.find(o => o.id === org.id);
      const team = findTeam(record, req.params.team);
      if (!team) throw new HttpError(404, 'not found');
      if (parentId) {
        if (parentId === team.id) {
          throw new HttpError(422, 'Parent team must belong to this organization');
        }
        const parent = record.teams.find(t => t.id === parentId);
        if (!parent) {
          throw new HttpError(422, 'Parent team must belong to this organization');
        }
        const seen = new Set([team.id]);
        let cursor = parent;
        while (cursor) {
          if (seen.has(cursor.id)) {
            throw new HttpError(422, 'Cyclic team hierarchy is not allowed');
          }
          seen.add(cursor.id);
          cursor = record.teams.find(t => t.id === cursor.parent_id) || null;
        }
      }
      team.parent_id = parentId;
      updated = {id: team.id, name: team.name, parent_id: team.parent_id};
    });
    res.json(updated);
  });

  app.post('/api/organizations/:identifier/teams/:team/members', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const org = findOrg(req.params.identifier);
    if (!org) return res.status(404).json({error: 'not found'});
    if (!org.owners.includes(account.id)) {
      return res.status(403).json({error: 'Only organization owners can maintain team members'});
    }
    const body = req.body || {};
    const identifier = typeof body.username === 'string' ? body.username.trim() : '';
    const lowered = identifier.toLowerCase();
    const target = identifier
      ? accounts.list(a => a.username === identifier ||
          (typeof a.email === 'string' && a.email.toLowerCase() === lowered))[0]
      : null;
    if (!target || !org.members.includes(target.id)) {
      return res.status(422).json({errors: {username: 'Account is not a member of this organization'}});
    }
    let result = null;
    organizations.transact(items => {
      const record = items.find(o => o.id === org.id);
      const team = findTeam(record, req.params.team);
      if (!team) throw new HttpError(404, 'not found');
      team.direct_members = team.direct_members || [];
      if (team.direct_members.includes(target.id)) {
        throw new HttpError(409, 'Account is already a member of this team');
      }
      team.direct_members.push(target.id);
      result = {username: target.username};
    });
    res.status(201).json(result);
  });

  app.delete('/api/organizations/:identifier/teams/:team/members/:username', (req, res) => {
    const account = currentAccount(req);
    if (!account) return res.status(401).json({error: 'Not signed in'});
    const org = findOrg(req.params.identifier);
    if (!org) return res.status(404).json({error: 'not found'});
    if (!org.owners.includes(account.id)) {
      return res.status(403).json({error: 'Only organization owners can maintain team members'});
    }
    const target = accounts.list(a => a.username === req.params.username)[0];
    if (!target) return res.status(404).json({error: 'not found'});
    let removed = false;
    organizations.transact(items => {
      const record = items.find(o => o.id === org.id);
      const team = findTeam(record, req.params.team);
      if (!team) throw new HttpError(404, 'not found');
      const before = (team.direct_members || []).length;
      team.direct_members = (team.direct_members || []).filter(id => id !== target.id);
      removed = team.direct_members.length !== before;
    });
    if (!removed) return res.status(404).json({error: 'not found'});
    res.status(204).end();
  });
};
