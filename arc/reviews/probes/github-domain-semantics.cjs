// Target-specific diagnostic adapter. Run with an isolated app copy and JSON output path.
// Uses the example implementation routes; this is not a portable acceptance gate.
const fs=require('fs'),path=require('path'),os=require('os');
const [appRoot,output]=process.argv.slice(2), directory=fs.mkdtempSync(path.join(os.tmpdir(),'v17-domain-probe-'));
process.env.ARC_DATA_DIR=directory;
const express=require(path.join(appRoot,'backend/node_modules/express'));
const load=name=>require(path.join(appRoot,'backend/lib',name))[name];
const repositories=load('repositories'),organizations=load('organizations'),teams=load('teams'),sessions=load('sessions');
const owner='acc-spec-owner',member='acc-bob-reviewer';
const session=sessions.create({accountId:owner,active:true});
const commits=[{id:'probe-root',message:'Initialize base',parents:[],files:{}},{id:'probe-main',message:'Base commit',parents:['probe-root'],files:{'README.md':'base'}},{id:'probe-feature',message:'Feature change',parents:['probe-main'],files:{'README.md':'feature'}},{id:'probe-sibling',message:'Unrelated branch change',parents:['probe-main'],files:{'README.md':'sibling'}}];
repositories.create({id:'repo-history-probe',name:'history-probe',ownerId:'acc-alice-dev',ownerType:'account',visibility:'Public',defaultBranch:'main',files:['README.md'],branches:[{name:'main',headCommitId:'probe-main',fileContents:{'README.md':'base'}},{name:'feature',headCommitId:'probe-feature',fileContents:{'README.md':'feature'}},{name:'sibling',headCommitId:'probe-sibling',fileContents:{'README.md':'sibling'}}],commits,pullRequests:[{id:'pr-history-probe',number:1,title:'Compare-only probe',status:'Open',author:'acc-alice-dev',base:'main',compare:'feature',baseCommit:'probe-main',compareCommit:'probe-feature',reviews:[],activity:[]}]});
for(const [id,owners] of [['last-owner-probe',[owner]],['two-owners-probe',[owner,member]]]) {
 organizations.create({id:'org-'+id,identifier:id,displayName:id,owners,members:[owner,member]});
 teams.create({id:'team-'+id,organizationId:'org-'+id,name:'guard-team',directMembers:[owner,member]});
}
const app=express();app.use(express.json());for(const name of ['organizations','branchProtections'])require(path.join(appRoot,'backend/routes',name))(app);
app.use((e,req,res,next)=>res.status(e.status||500).json({error:e.message}));
(async()=>{
 const server=app.listen(0,'127.0.0.1');await new Promise(resolve=>server.once('listening',resolve));const base=`http://127.0.0.1:${server.address().port}`;
 try{
 const response=await fetch(base+'/api/repositories/account/alice-dev/history-probe/pull-requests/1'),pr=await response.json();
 const before={org:organizations.get('org-last-owner-probe'),team:teams.get('team-last-owner-probe')};
 const guard=await fetch(base+'/api/organizations/last-owner-probe/members/spec-owner',{method:'DELETE',headers:{'x-session-id':session.id}}),guardBody=await guard.json();
 const after={org:organizations.get('org-last-owner-probe'),team:teams.get('team-last-owner-probe')};
 const valid=await fetch(base+'/api/organizations/two-owners-probe/members/bob-reviewer',{method:'DELETE',headers:{'x-session-id':session.id}});
 const result={prCompareOnly:{status:response.status,expected:['probe-feature'],actual:(pr.commits||[]).map(c=>c.id),response:pr},lastOwnerGuard:{status:guard.status,response:guardBody,allRelationshipsPreserved:JSON.stringify(before)===JSON.stringify(after)},otherOwnerRemoval:{status:valid.status,remainingOwners:organizations.get('org-two-owners-probe').owners,removedFromTeam:!teams.get('team-two-owners-probe').directMembers.includes(member)}};
 fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({...result,prCompareOnly:{...result.prCompareOnly,response:undefined}}));
 }finally{await new Promise(resolve=>server.close(resolve));fs.rmSync(directory,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
