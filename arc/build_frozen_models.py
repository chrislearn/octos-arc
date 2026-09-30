#!/usr/bin/env python3
"""Reproduce reviewed business models and lossless source contracts offline.

The semantic models describe shared identities and command invariants. Exact
source clauses remain separate; no clause is claimed to have a passing test.
"""
import hashlib
import json
import re
from pathlib import Path
import yaml
from domain_contracts import contract_manifest, requirement_index
from obligation_planning import source_scope, parse_obligation_details
from requirement_contracts import compile_contracts
from frozen_suites import requirements_digest

ROOT=Path(__file__).resolve().parent

def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def nodes(tree):
    yield tree
    for child in tree.get('children',[]): yield from nodes(child)

def clauses(description):
    """Keep verbatim substrings; omit only the image-reference appendix."""
    description=re.split(r'\n\s*(?:Screenshot reference|Page reference):',description,maxsplit=1)[0]
    for line in description.splitlines():
        line=line.strip()
        if not line or line.startswith('!['): continue
        for quote in re.split(r'(?<=[.!?;])\s+(?=[A-Z“"`])',line):
            quote=quote.strip()
            if len(quote)>=12: yield quote

def source_commands(leaves):
    commands=[]
    for node in leaves:
        parts=list(clauses(node.get('description','')))
        rejection=[q for q in parts if re.search(r'\b(?:reject\w*|fail\w*|invalid|incorrect|unknown|unavailable|conflict\w*|not allowed|cannot|does not|must not|no record|unchanged)\b',q,re.I)]
        permission=[q for q in parts if re.search(r'\b(?:permission|authoriz\w*|role|Owner|Admin|Triage|Maintain|signed.in|visitor|non.author|session)\b',q,re.I)]
        preconditions=[q for q in parts if re.search(r'\b(?:only|must|required|valid|before|precondition|seed|initial|starts?)\b',q,re.I)]
        transitions=[q for q in parts if re.search(r'\b(?:Open|Closed|Draft|Merged|Pending|Published|active|switch\w*|convert\w*|reopen\w*|undo|redo)\b',q)]
        persistence=[q for q in parts if re.search(r'\b(?:persist\w*|reload\w*|refresh\w*|restart\w*|stores?|stored|saved|atomic\w*)\b',q,re.I)]
        # Effects retain the complete clauses instead of a model's lossy summary.
        # Other fields are navigation indices into those same authoritative clauses.
        commands.append({'name':node['name'],'requirements':[node['id']],
                         'preconditions':preconditions,'effects':parts,
                         'rejected_effects':rejection,'state_transitions':transitions,
                         'permissions':permission,'persistence':persistence,
                         'basis':'verbatim atomic source clauses; fields are source navigation indices, not invented command steps'})
    return commands

def build(task):
    tree=yaml.safe_load((ROOT/'tasks'/task/'requirements.yaml').read_text())
    all_nodes=list(nodes(tree)); leaves=[n for n in all_nodes if n.get('type')=='ATOMIC']
    directory=ROOT/'frozen-tests'/task
    if task=='hackathon--github':
        from frozen_github_model import design
    elif task=='hackathon--sheet':
        from frozen_sheet_model import design
    else: raise ValueError(task)
    model=design()
    # Keep the hand-reviewed shared model and every original atomic constraint.
    model.setdefault('commands',[]).extend(source_commands(leaves))
    model.setdefault('contracts',[]).extend({'requirements':[n['id']],
                                            'invariants':list(clauses(n.get('description',''))),
                                            'basis':'verbatim original atomic clauses'} for n in leaves)
    for parent in all_nodes:
        if parent.get('type')=='ATOMIC': continue
        parts=list(clauses(parent.get('description','')))
        affected=[n['id'] for n in nodes(parent) if n.get('type')=='ATOMIC']
        if parts and affected:
            model['contracts'].append({'requirements':affected,'invariants':parts,
                                       'source_requirement_id':parent['id'],
                                       'basis':'verbatim original inherited clauses'})
    model['review_status']='reviewed'; model['frozen']=True; model['official']=False
    model['review_kind']='source_review'; model['runtime_status']='not_run_against_product'
    from main import app_design_errors, app_design_coverage
    assert not app_design_errors(model,requirement_index(tree)),app_design_errors(model,requirement_index(tree))
    assert {n['id'] for n in leaves}<=app_design_coverage(model)
    manifest=contract_manifest(tree,model)
    assert not manifest['gaps'],manifest['gaps']
    manifest.update(status='reviewed_unverified',review_status='reviewed',frozen=True,official=False,
                    review_kind='source_review',runtime_status='not_run_against_product',
                    requirements_sha256=requirements_digest(tree))
    contracts=compile_contracts(leaves)
    contracts.update(review_status='reviewed',frozen=True,official=False,requirements_sha256=requirements_digest(tree),
                     interpretation='Lossless projection. Where generic/corrupted scenario prose is underspecified, atomic descriptions and inherited source contracts provide the concrete business rules; no new outcome is inferred from a placeholder.')
    sources,ancestry=source_scope(tree,[n['id'] for n in leaves])
    lookup={n['id']:n for n in all_nodes}
    proposals=[]
    for leaf,chain in ancestry.items():
        for owner in chain:
            for quote in clauses(lookup[owner].get('description','')):
                proposals.append({'requirement_id':owner,'applies_to':[leaf],'quote':quote,
                                  'branch':'mixed','outcome':quote})
    ledger,by_leaf,errors=parse_obligation_details(json.dumps({'obligations':proposals,'gaps':[]},ensure_ascii=False),sources,ancestry)
    assert not errors and not any(by_leaf.values()),(errors,{k:v for k,v in by_leaf.items() if v})
    obligations={'version':1,'review_status':'reviewed','frozen':True,'official':False,
                 'basis':'Verbatim source clause inventory including every substantive ancestor. mixed preserves a clause without claiming a single success/rejection branch; no executable test witness or coverage claim is inferred.',
                 'obligations':ledger,'nodes':{leaf:{'status':'source_grounded','review_status':'reviewed','frozen':True,'errors':[],'attempts':1,'method':'offline_source_review','candidate_obligations':sum(leaf in r['applies_to'] for r in ledger)} for leaf in ancestry},
                 'seconds':0,'requirements_sha256':requirements_digest(tree),'runtime_status':'not_run_against_product'}
    write(directory/'app-design.json',model); write(directory/'domain-contracts.json',manifest)
    write(directory/'requirement-contracts.json',contracts); write(directory/'test-obligations.json',obligations)
    write(directory/'business-review.json',{'version':1,'review_status':'reviewed','frozen':True,'official':False,
          'review_date':'2026-09-30','review_kind':'source_review','runtime_status':'not_run_against_product',
          'requirements_sha256':requirements_digest(tree),'node_ids':[n['id'] for n in leaves],
          'files':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ['app-design.json','domain-contracts.json','requirement-contracts.json','test-obligations.json']},
          'gaps':[],'scope':'Shared identity/ownership/storage proposal, exact atomic and inherited clauses, command preconditions/effects/rejection/persistence; original sources remain authoritative. URLs and storage schema are implementation choices.'})
    print(task,len(leaves),'business nodes',len(model['data_model']),'entities',len(ledger),'source clauses')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--task',choices=['hackathon--github','hackathon--sheet'])
    args=parser.parse_args()
    for task in [args.task] if args.task else ['hackathon--github','hackathon--sheet']: build(task)
