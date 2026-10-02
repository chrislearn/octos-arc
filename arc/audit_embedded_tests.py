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
from embedded_suites import requirements_digest

ROOT=Path(__file__).resolve().parent
SUITES=ROOT/'derived-tests'
REVIEWED_RELEASES = {
    'hackathon--github': ('2026-10-02', 16),
    'hackathon--sheet': ('2026-10-02', 11),
}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def leaves(node):
    if node.get('type')=='ATOMIC': yield node
    for child in node.get('children',[]): yield from leaves(child)

def fixtures(task,plan):
    if task=='hackathon--github':
        return json.loads((ROOT/'github_requirement_fixtures.json').read_text())
    if task=='hackathon--sheet':
        return {'schema_version':1,'task':task,'isolation':'Mutations create their own workbook through visible UI, except the exclusive row-node and column-node seeds. Q3 Sales is read-only. Fresh server data is required for each suite invocation.',
                'workbooks':[{'name':'Q3 Sales','worksheets':[{'name':'Sheet1','cells':{'A1':'Region'}}]},
                             {'name':'Row operations seed','case_id':'row-node','worksheets':[{'name':'Sheet1','cells':{'A1':'Label','B1':'Value','A2':'first','B2':'10','A3':'second','B3':'20'}}]},
                             {'name':'Column operations seed','case_id':'column-node','worksheets':[{'name':'Sheet1','cells':{'A1':'first','A2':'alpha','B1':'second','B2':'beta','C1':'third','C2':'gamma'}}]}],
                'private_api_required':False,'routes':'Implementation-defined; tests discover and reuse browser-visible URLs.'}
    repositories=[]
    accounts=[{'username':u,'email':('alice.dev@example.test' if u=='alice-dev' else u+'@example.test'),
               'password':'Valid-password-123!','verified':True,'available':u!='spec-unavailable'}
              for u in ['alice-dev','bob-reviewer','spec-owner','spec-admin','spec-write','spec-maintain','spec-triage','spec-read','spec-new-member','spec-unavailable']]
    roles={'spec-admin':'Admin','spec-write':'Write','spec-maintain':'Maintain','spec-triage':'Triage','spec-read':'Read','bob-reviewer':'Write'}
    orgs=[]
    case_ids=sorted({r['fixture'] for r in plan if r.get('fixture')})
    for fid in case_ids:
        profile = next((row.get('source_fixture', fid) for row in plan if row.get('fixture') == fid), fid)
        organization='spec-org-'+fid
        org={'identifier':organization,'display_name':organization,'owners':['spec-owner'],
             'members':['spec-owner','spec-admin','spec-write','spec-maintain','spec-triage','spec-read','bob-reviewer'],
             'teams':[{'name':'frontend-team','direct_members':[],'parent':'platform-team'},
                      {'name':'frontend-child','direct_members':[],'parent':'frontend-team'},
                      {'name':'platform-team','direct_members':[],'parent':None}]}
        orgs.append(org)
        repo={'name':'spec-'+fid,'owner':organization,'visibility':'Private' if profile in {'member-add','member-remove','visibility','guide-team-access','grant-add','grant-replace'} else 'Public',
              'direct_grants':dict(roles),'team_grants':{},'default_branch':'main',
              'branches':{'main':{'files':{'README.md':'Document search flow','src/search.ts':'export const search = "search flow";'},'commit_message':'Document search flow','author':'alice-dev','committed_at':'2026-09-01T12:00:00Z','parent_revision':{'files':{},'commit_message':'Initialize empty repository','author':'alice-dev','committed_at':'2026-08-31T12:00:00Z'}},
                          'feature-search':{'base':'main','files':{'README.md':'Document search flow','src/search.ts':'export const search = "merged search flow";','main-only.md':'feature-only content'},'commit_message':'Implement search flow','author':'spec-write'},
                          'draft-feature':{'base':'main','files':{'README.md':'draft changes','src/search.ts':'export const search = "search flow";'},'commit_message':'Draft update','author':'spec-write'}},
              'labels':['bug'],'milestones':['v1.0'],'issues':[], 'pull_requests':[], 'branch_protection':{}}
        if profile=='last-owner': org['teams'][0]['direct_members']=['spec-owner']
        if profile=='member-add': repo['direct_grants'].pop('spec-new-member',None)
        if profile in {'grant-add','grant-replace'}:
            repo['direct_grants'].pop('bob-reviewer')
            org['teams'][0]['direct_members']=['bob-reviewer']
            repo['team_grants']={} if profile=='grant-add' else {'frontend-team':'Write'}
        if profile=='guide-team-access':
            repo['direct_grants'].pop('bob-reviewer')
            repo['team_grants']={'frontend-team':'Write'}
            org['teams'][0]['direct_members']=['bob-reviewer']
            org['teams'][1]['direct_members']=['spec-read']
        if profile.startswith('issue-'):
            repo['issues']=[{'number':1,'title':'Original issue title' if profile=='issue-edit-invalid' else 'Improve onboarding',
                             'description':'Describe the onboarding improvement.','status':'Open','author':'spec-write','assignees':[],'labels':[],'milestone':None,'comments':[], 'activity':['Created issue']}]
        if profile=='guide-default-release':
            repo['branches']['release']={'base':'main','files':dict(repo['branches']['main']['files']),
                                         'commit_message':'Prepare release branch','author':'spec-admin'}
        pr_ids={'check-success','pr-ready','review-comment','review-pending','review-approve','review-request-changes','review-request','merge-success','merge-blocked','pr-close','pr-close-read','guide-review-cycle','guide-review-publication'}
        if profile in pr_ids or profile.startswith(('merge-','review-denied-','pr-milestone')) or profile=='pr-filter-lifecycle' or fid=='review-replace' or fid=='review-decision-comment':
            draft=profile in {'pr-ready','review-denied-draft'}
            pr={'number':1,'title':'Draft onboarding update' if draft else 'Improve onboarding',
                'description':'Describe the onboarding improvement.','status':'Draft' if draft else 'Open',
                'author':'spec-write','base':'main','compare':'draft-feature' if draft else 'feature-search',
                'reviews':[],'reviewers':[],'inline_comments':[], 'check_test':'pending',
                'discussion':[{'author':'spec-write','body':'Please review this update.'}]}
            if profile in {'merge-success','merge-blocked','check-success','guide-review-cycle'}:
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':True}}
            if profile=='merge-success': pr.update(reviews=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'current_compare'}],check_test='success')
            if profile.startswith('merge-denied-') or profile=='merge-check-failure':
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':True}}
                pr.update(reviews=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'current_compare'}],check_test='failure' if profile=='merge-check-failure' else 'success')
            if profile=='review-denied-draft': pr['title']='Improve onboarding'
            if profile=='merge-blocked': pr['check_test']='success'
            if profile=='merge-check-only':
                repo['branch_protection']={'main':{'require_1_approval':False,'require_status_check_test':True}}
                pr['check_test']='success'
            if profile=='merge-approval-only':
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':False}}
                pr['reviews']=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'current_compare'}]
            if profile=='merge-request-changes':
                pr['reviews']=[{'reviewer':'bob-reviewer','decision':'Request changes','commit':'current_compare'}]
            if profile=='merge-stale-approval':
                repo['branch_protection']={'main':{'require_1_approval':True,'require_status_check_test':True}}
                pr['check_test']='success'
                pr['reviews']=[{'reviewer':'bob-reviewer','decision':'Approve','commit':'previous_compare'}]
                repo['branches']['feature-search']['previous_commit']={'message':'Previous search change','author':'spec-write'}
            repo['pull_requests']=[pr]
            if profile=='pr-filter-lifecycle':
                repo['pull_requests'].extend([
                    {**pr,'number':2,'title':'Fix search','status':'Closed'},
                    {**pr,'number':3,'title':'Draft onboarding update','status':'Draft','compare':'draft-feature'}])
        repositories.append(repo)
    # Immutable public discovery records. Same repository name in two owners is
    # legitimate; the helper scopes ambiguous results by owner/name metadata.
    template={'name':'acme-docs','owner':'alice-dev','visibility':'Public','default_branch':'main','direct_grants':roles,
              'branches':{'main':{'files':{'README.md':'Document search flow','src/search.ts':'export const search = "search flow";'},'commit_message':'Document search flow','author':'alice-dev','committed_at':'2026-09-01T12:00:00Z','parent_revision':{'files':{},'commit_message':'Initialize empty repository','author':'alice-dev','committed_at':'2026-08-31T12:00:00Z'}},
                          'feature-search':{'base':'main','files':{'README.md':'Document search flow','src/search.ts':'export const search = "merged search flow";','main-only.md':'feature-only content'},'commit_message':'Implement search flow','author':'alice-dev'}},
              'issues':[{'number':1,'title':'Improve onboarding','description':'Describe the onboarding improvement.','status':'Open','author':'alice-dev','activity':['Created issue']},
                        {'number':2,'title':'Legacy welcome text','description':'Previous welcome wording','status':'Closed','author':'alice-dev'}],
              'pull_requests':[{'number':1,'title':'Improve onboarding','description':'Describe the onboarding improvement.','status':'Open','author':'alice-dev','base':'main','compare':'feature-search','discussion':[{'author':'bob-reviewer','body':'Review discussion'}]},
                               {'number':2,'title':'Fix search','status':'Closed','author':'alice-dev','base':'main','compare':'feature-search'}]}
    repositories.extend([template,{**template,'owner':'Acme Demo','issues':[],'pull_requests':[]},
                         {**template,'name':'acme-docs-org','owner':'Acme Demo','issues':[],'pull_requests':[]},
                         {**template,'name':'secret-research','visibility':'Private','direct_grants':{}},
                         {**template,'name':'secret-research','owner':'Acme Demo','visibility':'Private','direct_grants':{},'issues':[],'pull_requests':[]},
                         {**template,'name':'acme-docs-fork','source_repository':'alice-dev/acme-docs'},
                         {**template,'name':'foreign-milestone-repo','milestones':['foreign-milestone'],'issues':[],'pull_requests':[]}])
    orgs.extend([{'identifier':'acme-demo','display_name':'Acme Demo','owners':['spec-owner'],'members':['spec-owner','bob-reviewer'],'teams':[]},
                 {'identifier':'spec-org-existing','display_name':'Existing Organization','owners':['alice-dev'],'members':['alice-dev'],'teams':[]}])
    return {'schema_version':1,'task':task,'private_api_required':False,'accounts':accounts,'organizations':orgs,'repositories':repositories,
            'isolation':'Each caseId owns a separate mutable repository/organization. Fresh server data is required for a new suite invocation; restore these seeds before repeated runs. Each test owns its browser session.',
            'role_matrix':{'create_edit_comment_issue':['Write','Maintain','Admin'],'assign_label_milestone_close_issue':['Triage','Maintain','Admin'],
                           'create_branch_edit_file_review':['Write','Maintain','Admin'],'merge':['Maintain','Admin'],'admin_settings':['Admin'],
                           'organization_owner':'Admin on own organization repositories','team_hierarchy':'No membership or grant propagation'},
            'routes':'No prescribed URL paths or private seed/reset API. Provision these records as initial server data; tests navigate named public controls.'}

README='''# Source-reviewed internal derived tests\n\nThese tests are derived from the supplied atomic requirements and inherited interaction contracts. Generic or corrupted scenario templates are interpreted using the more precise atomic prose. They are internal acceptance checks, not official ARC evaluation tests or an official score.\n\nAll executable cases have completed source review. Frozen hashes in suite-origin.json and review.json bind that review to the exact helper, fixture and spec bytes. Runtime product behavior has not been certified by this source review.\n\nRead app-design.json, domain-contracts.json, requirement-contracts.json and test-obligations.json as the frozen source-reviewed business context before generating code. app-design describes shared identities, source contracts and atomic commands; its implementation schemas are proposals, while original requirements remain authoritative. The obligation ledger is a verbatim clause inventory, not a claim of exhaustive executable test coverage.

Read fixtures.json before generating code. Provision the public records and role relationships as server seeds. Do not create a private test-only API. Every suite invocation starts with fresh server data; within a suite, mutable GitHub records are separate per case and spreadsheet mutations use separate UI-created workbooks or their exclusive seeded workbook. Tests remain enabled if a seed is missing. Run the complete suite with one worker against each server/data instance. Global list snapshots assert absence of partial records and require serial execution; parallel workers need independent servers and storage.\n\nPlaywright uses E2E_BASE_URL (the harness supplies its isolated smoke server). Both helpers use role/name locators; entry addresses are discovered from the browser and reused across reloads. Source requirements remain authoritative if a conflict is found.\n'''

README += """
For GitHub, coverage-review.json separates node gates from reviewed behavior witnesses and records remaining gaps without counting them as passed. Features without portable interaction contracts need a target-specific adapter; backend authorization, storage failures and concurrency need implementation harnesses. Do not invent private APIs or mandatory control names to conceal a gap.

The suite namespace is derived-tests for both embedded recipes and generated project files. REQ-*.spec.ts files are the per-node gates. INTEGRATION-*.spec.ts files describe final acceptance across multiple nodes; never alias them to the first requirement. Integration files are retained in the source suite and binary, but are temporarily omitted when exporting a suite into a project. They are currently unused in project acceptance. The exported suite-origin.json records export_policy, ignored_specs and source manifest identity; its case-plan, review, counts and file hashes describe only the exported REQ cases.

case-plan.json records phase, primary node_id and requires (the contracts explicitly exercised by a case). A node gate cannot require a capability later in the original graph's document-stable topological order. INTEGRATION-deferred-* retains original Sheet cases using later capabilities. Every retained integration case also has an independently runnable REQ context regression at the last required capability; origin_file, origin_title and origin_node_id bind its provenance. Mutable GitHub witnesses own distinct fixture records. Exported node tests therefore keep these behavioral assertions even when integrations are omitted. The primary ID is for traceability, not early scheduling. Guided cases use test.step to explain state transitions and assert the preserved state as well as the change. These retained source cases are temporarily excluded at export, rather than marked skip or deleted.

Sheet's row-node and column-node cases each own a dedicated seeded workbook so those early gates can test record movement before editing/paste exists. Q3 Sales stays read-only; all other mutations create their own workbooks through UI. Provision the seed fixtures rather than adding a private test API.

Source review and a green browser suite do not certify complete backend authorization or real disk-failure/process-restart handling. Those require a harness controlling the implementation's process/storage and legitimate request construction. Do not prescribe private reset endpoints, a JSON action route or disk paths in these portable suites. Preserve all test assertions when investigating a failure; compare the source requirement before classifying it as a product or spec defect.
"""

def validate_plan(plan,nodes,specs):
    """Keep every atomic gate and bind cross-node cases to the final phase."""
    atomic={name for name in specs if name in nodes}
    integration=specs-atomic
    assert atomic==set(nodes),('leaf coverage',sorted(set(nodes)-atomic))
    assert all(re.fullmatch(r'INTEGRATION-[a-z][a-z0-9-]*',name) for name in integration),('unknown spec files',integration)
    assert {r['file'] for r in plan}=={name+'.spec.ts' for name in specs},'case-plan file coverage'
    from requirement_order import topo_order
    order={n['id']:i for i,n in enumerate(topo_order({'id':'ROOT','type':'FOLDER','children':list(nodes.values())}))}
    for row in plan:
        assert row['node_id'] in nodes,('unknown primary requirement',row)
        requires=row['requires']
        assert requires and len(requires)==len(set(requires)) and set(requires)<=set(nodes),('invalid requirement references',row)
        assert row['node_id'] in requires,('primary requirement not exercised',row)
        setup=row.get('setup_requires',[])
        assert isinstance(setup,list) and len(setup)==len(set(setup)) and set(setup)<=set(nodes),('invalid setup references',row)
        assert row['node_id'] not in setup,('self setup reference',row)
        phase='integration' if row['file'].startswith('INTEGRATION-') else 'node'
        assert row['phase']==phase,('phase/filename mismatch',row)
        if phase=='node':
            assert row['file']==row['node_id']+'.spec.ts',('node gate ownership',row)
            assert all(order[rid]<=order[row['node_id']] for rid in requires),('node gate uses a later capability',row)
        else: assert len(requires)>=2,('cross-node case needs multiple contracts',row)

def audit(freeze=False,task_filter=None):
    catalogue=(json.loads((SUITES/'manifest.json').read_text()) if task_filter is not None
               else {'schema_version':1,'suites':{}})
    if task_filter is not None and not (SUITES/task_filter).is_dir():
        raise ValueError('Unknown embedded task: '+task_filter)
    for directory in sorted(p for p in SUITES.iterdir() if p.is_dir()):
        if task_filter is not None and directory.name!=task_filter: continue
        task=directory.name; source=ROOT/'tasks'/task/'requirements.yaml'; tree=yaml.safe_load(source.read_text()); nodes={n['id']:n for n in leaves(tree)}
        plan=json.loads((directory/'case-plan.json').read_text()); specs={p.stem.removesuffix('.spec') for p in directory.glob('*.spec.ts')}
        mutable=[r['fixture'] for r in plan if r.get('fixture')]
        assert len(mutable)==len(set(mutable)),(task,'mutable fixture reused across cases')
        validate_plan(plan,nodes,specs)
        if task=='hackathon--github':
            from frozen_setup import github_setup_features, frozen_setup_dependencies, setup_generation_order
            from build_embedded_tests import CASES
            helpers=(directory/'helpers.ts').read_text()
            recipes={(r['node_id'],r['title']):r for rows in CASES[task].values() for r in rows}
            for row in plan:
                recipe=recipes.get((row['node_id'],row['title'].split(': ',1)[1]))
                # Node witness titles include provenance; match the generated recipe title.
                assert recipe is not None,('missing source recipe',row['title'])
                expected=github_setup_features(recipe['body'],helpers)-{row['node_id']}
                assert set(row.get('setup_requires',[]))==expected,('helper setup closure mismatch',row)
            setup_generation_order(tree,frozen_setup_dependencies(directory,{'name':task},tree))
        names=set()
        for row in plan:
            source_text=(directory/row['file']).read_text(); title=row['title']; assert title not in names; names.add(title)
            assert f'test({json.dumps(title)}' in source_text,(task,title)
            assert not re.search(r'test\.(skip|fixme|only)\s*\(',source_text)
            assert 'await ' in source_text and ('expect(' in source_text or 'h.values(' in source_text or 'h.persisted(' in source_text or 'h.formula(' in source_text)
        for spec in directory.glob('*.spec.ts'):
            assert len(re.findall(r'^test\(',spec.read_text(),re.M))==sum(r['file']==spec.name for r in plan)
        if freeze:
            review_date, spec_revision = REVIEWED_RELEASES[task]
            from build_embedded_models import build as build_model
            build_model(task)
            (directory/'requirements.yaml').write_bytes(source.read_bytes())
            task_readme = README
            if task == 'hackathon--github':
                task_readme += '\nRevision 16 retains all 310 prior cases and adds 14 cross-stage compatibility witnesses for cold public discovery, the authenticated directory, team/repository settings, sign-out privacy, the homepage search viewport, named repositories, commit entry, and Issues/Pull requests discovery. The three remote reports contain 70 navigation failures and one evaluator-side ReferenceError (uniqueAccount is not defined); these tests do not claim to reconstruct that unavailable helper. Requirements, fixtures and existing assertions are unchanged. Navigation read models remain scoped to the current identity and repository permissions.\n'
                task_readme += '\nRevision 15 retains all 303 prior cases and adds seven regressions for email-only recovery submission, credential preservation/replacement, named repository/team data readiness after directory entry, and sign-out history privacy. The recovery helper now always submits Email using an allowed action; an already visible code must not bypass that requirement step. Data-readiness checks are compatibility witnesses, not reconstructed evaluator source. Requirements and fixtures remain unchanged; no member-role hiding or global Member uniqueness is required.\n'
                task_readme += '\nRevision 14 preserves all 297 prior cases and adds six regressions: four navigation-readiness compatibility checks, upper-right account-menu placement, and member-scoped role checks with multiple Member rows. Immediate visibility checks explicitly supplement business requirements to detect deferred route commits and same-session loading flicker. They are not copies of the unavailable official navigation helper. A global exact Member text locator is intentionally not required: distinct member rows may legitimately share that role. Original requirements and fixtures remain unchanged.\n'
                task_readme += '\nRevision 13 corrects the public-navigation and heading assertions, checks the literal saved Parent team value and unique recovery feedback, and removes implicit login reloads. Nine self-test regressions cover immediate recovery fields, Sign in link availability, keyboard account-menu navigation, repository access entry, pointer/keyboard member role selection, and isolated member removal/readdition/duplicates. These are reconstructed requirement checks, not official self-test source; the exact cause of the eleven remote homepage navigation failures remains unverified. All other prior cases and phases remain.\n'
                task_readme += '\nRevision 12 adds nine Stage 1 regressions: direct homepage Sign up, registration/login/recovery password clearing, both organization identities, prescribed account-menu organization entry, and visitor/nonmember People and Teams boundaries with positive member reads. All 279 prior cases and phases remain. Server privacy is checked in the example implementation harness; browser source review alone does not certify backend authorization.\n'
                task_readme += '\nRevision 11 adds seven regressions for exact search link names and owner metadata, shared repository identity across search/files/issues/PRs, slash branch browsing and web writes, exact Base/Compare accessible names, optional Request changes summaries, and independent organization identifier/display-name validation. Helpers no longer accept owner/name links or lowercase comparison labels. All 272 prior cases and their phases remain. The contradictory Stage1 Acme Demo identifier scenario is interpreted according to its atomic validation prose; requirements.yaml remains unchanged.\n'
                task_readme += '\nRevision 10 aligns all 100 original scenarios with the supplied canonical accounts and named records, while retaining the original 172 additional source-reviewed cases in their existing phases. Regression fixtures use a regression- prefix and actual role accounts. The earlier Revision 9 additionally corrects review-field scoping, permits existing pending-check setters and commit-count comparison summaries, and verifies that PR commit lists exclude base ancestors. Revision 9 is grounded in the full hackathon--github requirements folder supplied on 2026-10-02. Source recipes and frozen gates were reviewed together: isolated registration rejections and legal boundaries, duplicate email, team parent changes and duplicate names, last-Owner membership refusal, positive Write/Triage authority, exact review summaries and an independent public check-setter witness. Native selects remain mandatory only where prescribed; permitted action labels and hidden/disabled unavailable controls are accepted. Optional Comment review decisions and non-Open PR filter dimensions are no longer mandatory. coverage-review.json records remaining semantic and harness gaps; product execution is not certified by this source review.\n'
            if task == 'hackathon--sheet':
                task_readme += '\nFor Sheet, coverage-review.json records concrete behavior witnesses and remaining gaps; node-gate coverage does not certify complete semantic coverage. Cell-value assertions preserve significant whitespace and data inside ordinary controls, reading live input/textarea values and removing named dropdown/filter decorations and hidden controls. Date witnesses use ISO date-only inputs and unambiguous English month names, including cases whose chronological and lexical orders differ. Other supported date grammars, timezone and locale interpretation remain unverified. Save-failure and delayed-selection witnesses learn HTTP writes from successful UI operations and require an adapter for other transports; lifecycle/storage/process failure coverage remains incomplete. Revision 10 retains all 196 prior cases and adds 23 regressions (219 total), covering malformed numbers and row-zero references, zero arithmetic and pivot records, adjacent deletion among four sheets, wide/tall CSV import, instant selection, delayed responses, failed grid Enter, rule create/modify/delete failures and exact contextual messages, changed numerical bounds, typed date and formula sorting, failed sorting/filtering retries, and SUM/AVERAGE Refresh rejection and retry. Configuration witnesses retain native-select support; native controls are not forbidden by the requirements. The phrase "new range" is interpreted as modified numerical bounds; no unmentioned cell-range control is imposed.\n'
            if task == 'hackathon--sheet':
                task_readme += '\nRevision 11 preserves all 219 earlier cases and adds 21 requirement regressions (240 total): unchanged imported formula text explicitly committed through the formula bar or grid and exported as values; nonactive worksheet deletion; stable multistep formula errors and dependency repair; accepted lowercase reference copying; blank and object-property-named pivot column groups; entirely deleted pivot source columns beside identical headers; and condition-to-value filter transitions. Official test assumptions outside the atomic requirements and unresolved validation-message lifetime behavior are excluded.\n'
            (directory/'README.md').write_text(task_readme)
            write(directory/'fixtures.json',fixtures(task,plan))
            if task=='hackathon--github':
                from github_coverage_review import coverage_review
                write(directory/'coverage-review.json',coverage_review(tree,plan))
            if task=='hackathon--sheet':
                from sheet_coverage_review import coverage_review
                write(directory/'coverage-review.json',coverage_review(tree,plan))
            reviews=[]
            for row in plan:
                node=nodes[row['node_id']]
                reviews.append({**row,'status':'reviewed','frozen':True,'reviewer':'Codex source review','review_date':review_date,
                                'basis':'Atomic description + inherited role, scope, state and entry contracts; source review only',
                                'requirement_quote':node['description'],'file_sha256':sha(directory/row['file']),
                                'requirement_quotes':{rid:nodes[rid]['description'] for rid in row['requires']},
                                'runtime_status':'not_run_against_product'})
            write(directory/'review.json',{'schema_version':1,'review_status':'reviewed','frozen':True,'cases':reviews})
            paths=sorted(p for p in directory.rglob('*') if p.is_file() and p.name!='suite-origin.json')
            manifest={'schema_version':1,'name':task,'root_name':tree['name'],'official':False,'review_status':'reviewed','frozen':True,'trusted':True,
                      'review_date':review_date,'review_kind':'source_review','runtime_status':'not_run_against_product',
                      'requirements_sha256':requirements_digest(tree),'spec_revision':spec_revision,'spec_count':len(specs),'case_count':len(plan),'node_ids':sorted(nodes),
                      'node_spec_count':len(nodes),'integration_spec_count':len(specs)-len(nodes),
                      'node_case_count':sum(r['phase']=='node' for r in plan),'integration_case_count':sum(r['phase']=='integration' for r in plan),
                      'files':{p.relative_to(directory).as_posix():sha(p) for p in paths}}
            write(directory/'suite-origin.json',manifest)
        else:
            from embedded_suites import verify_directory
            manifest=verify_directory(directory,tree,task)
        catalogue['suites'][task]={'root_name':tree['name'],'requirements_sha256':requirements_digest(tree),
                                 'spec_count':len(specs),'case_count':len(plan),'review_status':'reviewed','frozen':True,'trusted':True,'official':False}
        print(task,len(nodes),'atomic gates',len(specs)-len(nodes),'integration files',len(plan),'reviewed cases')
    if freeze: write(SUITES/'manifest.json',catalogue)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--task',choices=['hackathon--github','hackathon--sheet'])
    args=parser.parse_args(); audit(args.freeze,args.task)
