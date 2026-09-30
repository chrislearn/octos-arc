#!/usr/bin/env python3
"""Validate curated suites and bind the completed source review to file hashes.

--freeze records source review only. Product execution is a separate measurement.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import yaml
from frozen_suites import requirements_digest

ROOT=Path(__file__).resolve().parent
SUITES=ROOT/'frozen-tests'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def leaves(node):
    if node.get('type')=='ATOMIC': yield node
    for child in node.get('children',[]): yield from leaves(child)

def fixtures(task,plan):
    if task=='hackathon--sheet':
        return {'schema_version':1,'task':task,'isolation':'Every mutation creates its own workbook through visible UI. One seed workbook is reserved solely for REQ-1-1-1.',
                'workbooks':[{'name':'Q3 Sales','worksheets':[{'name':'Sheet1','cells':{'A1':'Region'}}]}],
                'private_api_required':False,'routes':'Implementation-defined; tests discover and reuse browser-visible URLs.'}
    repositories=[]
    accounts=[{'username':u,'email':('alice.dev@example.test' if u=='alice-dev' else u+'@example.test'),
               'password':'Valid-password-123!','verified':True,'available':u!='spec-unavailable'}
              for u in ['alice-dev','bob-reviewer','spec-owner','spec-admin','spec-write','spec-maintain','spec-triage','spec-read','spec-new-member','spec-unavailable']]
    roles={'spec-admin':'Admin','spec-write':'Write','spec-maintain':'Maintain','spec-triage':'Triage','spec-read':'Read','bob-reviewer':'Write'}
    orgs=[]
    case_ids=sorted({r['fixture'] for r in plan if r.get('fixture')})
    for fid in case_ids:
        organization='spec-org-'+fid
        org={'identifier':organization,'display_name':organization,'owners':['spec-owner'],
             'members':['spec-owner','spec-admin','spec-write','spec-maintain','spec-triage','spec-read','bob-reviewer'],
             'teams':[{'name':'frontend-team','direct_members':[],'parent':'platform-team'},
                      {'name':'frontend-child','direct_members':[],'parent':'frontend-team'},
                      {'name':'platform-team','direct_members':[],'parent':None}]}
        orgs.append(org)
        repo={'name':'spec-'+fid,'owner':organization,'visibility':'Private' if fid in {'member-add','member-remove','visibility'} else 'Public',
              'direct_grants':dict(roles),'team_grants':{},'default_branch':'main',
              'branches':{'main':{'files':{'README.md':'search flow','src/search.ts':'export const search = "search flow";'},'commit_message':'Document search flow','author':'alice-dev','committed_at':'2026-09-01T12:00:00Z','parent_revision':{'files':{},'commit_message':'Initialize empty repository','author':'alice-dev','committed_at':'2026-08-31T12:00:00Z'}},
                          'feature-search':{'base':'main','files':{'README.md':'search flow','src/search.ts':'export const search = "merged search flow";','main-only.md':'feature-only content'},'commit_message':'Implement search flow','author':'spec-write'},
                          'draft-feature':{'base':'main','files':{'README.md':'draft changes','src/search.ts':'export const search = "search flow";'},'commit_message':'Draft update','author':'spec-write'}},
              'labels':['bug'],'milestones':['v1.0'],'issues':[], 'pull_requests':[], 'branch_protection':{}}
        if fid=='member-add': repo['direct_grants'].pop('spec-new-member',None)
        if fid=='grant-add': repo['team_grants']={}
        if fid=='grant-replace': repo['team_grants']={'frontend-team':'Write'}
        if fid.startswith('issue-'):
            repo['issues']=[{'number':1,'title':'Original issue title' if fid=='issue-edit-invalid' else 'Improve onboarding',
                             'description':'Describe the onboarding improvement.','status':'Open','author':'spec-write','assignees':[],'labels':[],'milestone':None,'comments':[], 'activity':['Created issue']}]
        pr_ids={'check-success','pr-ready','review-comment','review-pending','review-approve','review-request-changes','review-request','merge-success','merge-blocked','pr-close','pr-close-read'}
        if fid in pr_ids or fid.startswith('merge-') or fid=='review-replace' or fid=='review-decision-comment':
            draft=fid=='pr-ready'
            pr={'number':1,'title':'Draft onboarding update' if draft else 'Improve onboarding',
                'description':'Describe the onboarding improvement.','status':'Draft' if draft else 'Open',
                'author':'spec-write','base':'main','compare':'draft-feature' if draft else 'feature-search',
                'reviews':[],'reviewers':[],'inline_comments':[], 'check_test':'pending',
                'discussion':[{'author':'spec-write','body':'Please review this update.'}]}
            if fid in {'merge-success','merge-blocked','check-success'}:
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':True}}
            if fid=='merge-success': pr.update(reviews=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'current_compare'}],check_test='success')
            if fid=='merge-blocked': pr['check_test']='success'
            if fid=='merge-check-only':
                repo['branch_protection']={'main':{'require_1_approval':False,'require_status_check_test':True}}
                pr['check_test']='success'
            if fid=='merge-approval-only':
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':False}}
                pr['reviews']=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'current_compare'}]
            if fid=='merge-request-changes':
                pr['reviews']=[{'reviewer':'bob-reviewer','decision':'Request changes','commit':'current_compare'}]
            if fid=='merge-stale-approval':
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':True}}
                pr['check_test']='success'
                pr['reviews']=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'previous_compare'}]
                repo['branches']['feature-search']['previous_commit']={'message':'Previous search change','author':'spec-write'}
            repo['pull_requests']=[pr]
        repositories.append(repo)
    # Immutable public discovery records. Same repository name in two owners is
    # legitimate; the helper scopes ambiguous results by owner/name metadata.
    template={'name':'acme-docs','owner':'alice-dev','visibility':'Public','default_branch':'main','direct_grants':roles,
              'branches':{'main':{'files':{'README.md':'search flow','src/search.ts':'export const search = "search flow";'},'commit_message':'Document search flow','author':'alice-dev','committed_at':'2026-09-01T12:00:00Z','parent_revision':{'files':{},'commit_message':'Initialize empty repository','author':'alice-dev','committed_at':'2026-08-31T12:00:00Z'}},
                          'feature-search':{'base':'main','files':{'README.md':'search flow','src/search.ts':'export const search = "merged search flow";','main-only.md':'feature-only content'},'commit_message':'Implement search flow','author':'alice-dev'}},
              'issues':[{'number':1,'title':'Improve onboarding','description':'Describe the onboarding improvement.','status':'Open','author':'alice-dev','activity':['Created issue']},
                        {'number':2,'title':'Legacy welcome text','description':'Previous welcome wording','status':'Closed','author':'alice-dev'}],
              'pull_requests':[{'number':1,'title':'Improve onboarding','description':'Describe the onboarding improvement.','status':'Open','author':'alice-dev','base':'main','compare':'feature-search','discussion':[{'author':'bob-reviewer','body':'Review discussion'}]},
                               {'number':2,'title':'Fix search','status':'Closed','author':'alice-dev','base':'main','compare':'feature-search'}]}
    repositories.extend([template,{**template,'owner':'Acme Demo','issues':[],'pull_requests':[]},
                         {**template,'name':'acme-docs-org','owner':'Acme Demo','issues':[],'pull_requests':[]},
                         {**template,'name':'secret-research','visibility':'Private','direct_grants':{}},
                         {**template,'name':'secret-research','owner':'Acme Demo','visibility':'Private','direct_grants':{},'issues':[],'pull_requests':[]},
                         {**template,'name':'acme-docs-fork','source_repository':'alice-dev/acme-docs'}])
    orgs.extend([{'identifier':'acme-demo','display_name':'Acme Demo','owners':['spec-owner'],'members':['spec-owner','bob-reviewer'],'teams':[]},
                 {'identifier':'spec-org-existing','display_name':'Existing Organization','owners':['alice-dev'],'members':['alice-dev'],'teams':[]}])
    return {'schema_version':1,'task':task,'private_api_required':False,'accounts':accounts,'organizations':orgs,'repositories':repositories,
            'isolation':'Each caseId owns a separate mutable repository/organization. Fresh server data is required for a new suite invocation; restore these seeds before repeated runs. Each test owns its browser session.',
            'role_matrix':{'create_edit_comment_issue':['Write','Maintain','Admin'],'assign_label_milestone_close_issue':['Triage','Maintain','Admin'],
                           'create_branch_edit_file_review':['Write','Maintain','Admin'],'merge':['Maintain','Admin'],'admin_settings':['Admin'],
                           'organization_owner':'Admin on own organization repositories','team_hierarchy':'No membership or grant propagation'},
            'routes':'No prescribed URL paths or private seed/reset API. Provision these records as initial server data; tests navigate named public controls.'}

README='''# Source-reviewed frozen internal tests\n\nThese tests are derived from the supplied atomic requirements and inherited interaction contracts. Generic or corrupted scenario templates are interpreted using the more precise atomic prose. They are internal acceptance checks, not official ARC evaluation tests or an official score.\n\nAll executable cases have completed source review. Frozen hashes in suite-origin.json and review.json bind that review to the exact helper, fixture and spec bytes. Runtime product behavior has not been certified by this source review.\n\nRead app-design.json, domain-contracts.json, requirement-contracts.json and test-obligations.json as the frozen source-reviewed business context before generating code. app-design describes shared identities, source contracts and atomic commands; its implementation schemas are proposals, while original requirements remain authoritative. The obligation ledger is a verbatim clause inventory, not a claim of exhaustive executable test coverage.

Read fixtures.json before generating code. Provision the public records and role relationships as server seeds. Do not create a private test-only API. Every suite invocation starts with fresh server data; within a suite, mutable GitHub records are separate per case and spreadsheet mutations create separate workbooks through UI. Tests remain enabled if a seed is missing.\n\nPlaywright uses E2E_BASE_URL (the harness supplies its isolated smoke server). Both helpers use role/name locators; entry addresses are discovered from the browser and reused across reloads. Source requirements remain authoritative if a conflict is found.\n'''

def audit(freeze=False):
    catalogue={'schema_version':1,'suites':{}}
    for directory in sorted(p for p in SUITES.iterdir() if p.is_dir()):
        task=directory.name; source=ROOT/'tasks'/task/'requirements.yaml'; tree=yaml.safe_load(source.read_text()); nodes={n['id']:n for n in leaves(tree)}
        plan=json.loads((directory/'case-plan.json').read_text()); specs={p.stem.removesuffix('.spec') for p in directory.glob('*.spec.ts')}
        mutable=[r['fixture'] for r in plan if r.get('fixture')]
        assert len(mutable)==len(set(mutable)),(task,'mutable fixture reused across cases')
        assert specs==set(nodes),(task,'leaf coverage',sorted(set(nodes)-specs))
        names=set()
        for row in plan:
            source_text=(directory/row['file']).read_text(); title=row['title']; assert title not in names; names.add(title)
            assert f'test({json.dumps(title)}' in source_text,(task,title)
            assert not re.search(r'test\.(skip|fixme|only)\s*\(',source_text)
            assert 'await ' in source_text and ('expect(' in source_text or 'h.values(' in source_text or 'h.persisted(' in source_text or 'h.formula(' in source_text)
        for spec in directory.glob('*.spec.ts'):
            assert len(re.findall(r'^test\(',spec.read_text(),re.M))==sum(r['file']==spec.name for r in plan)
        if freeze:
            from build_frozen_models import build as build_model
            build_model(task)
            (directory/'requirements.yaml').write_bytes(source.read_bytes()); (directory/'README.md').write_text(README)
            write(directory/'fixtures.json',fixtures(task,plan))
            reviews=[]
            for row in plan:
                node=nodes[row['node_id']]
                reviews.append({**row,'status':'reviewed','frozen':True,'reviewer':'Codex source review','review_date':'2026-09-30',
                                'basis':'Atomic description + inherited role, scope, state and entry contracts; source review only',
                                'requirement_quote':node['description'],'file_sha256':sha(directory/row['file']),
                                'runtime_status':'not_run_against_product'})
            write(directory/'review.json',{'schema_version':1,'review_status':'reviewed','frozen':True,'cases':reviews})
            paths=sorted(p for p in directory.rglob('*') if p.is_file() and p.name!='suite-origin.json')
            manifest={'schema_version':1,'name':task,'root_name':tree['name'],'official':False,'review_status':'reviewed','frozen':True,
                      'review_date':'2026-09-30','review_kind':'source_review','runtime_status':'not_run_against_product',
                      'requirements_sha256':requirements_digest(tree),'spec_count':len(specs),'case_count':len(plan),'node_ids':sorted(nodes),
                      'files':{p.relative_to(directory).as_posix():sha(p) for p in paths}}
            write(directory/'suite-origin.json',manifest)
        else:
            from frozen_suites import verify_directory
            manifest=verify_directory(directory,tree,task)
        catalogue['suites'][task]={'root_name':tree['name'],'requirements_sha256':requirements_digest(tree),
                                 'spec_count':len(specs),'case_count':len(plan),'review_status':'reviewed','frozen':True,'official':False}
        print(task,len(specs),'atomic requirements',len(plan),'reviewed cases')
    if freeze: write(SUITES/'manifest.json',catalogue)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--freeze',action='store_true'); audit(parser.parse_args().freeze)
