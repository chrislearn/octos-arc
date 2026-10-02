// Target-specific diagnostic adapter. Run with an isolated app copy and JSON output path.
// Uses the example implementation routes; this is not a portable acceptance gate.
const fs=require('fs'),path=require('path'),os=require('os');
const appRoot=process.argv[2], output=process.argv[3];
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'v17-org-rollback-'));process.env.ARC_DATA_DIR=directory;
const express=require(path.join(appRoot,'backend/node_modules/express'));
const load=name=>require(path.join(appRoot,'backend/lib',name))[name];
const organizations=load('organizations'), teams=load('teams'),repositories=load('repositories'), grants=load('repositoryGrants'),sessions=load('sessions');
const owner='acc-spec-owner',member='acc-bob-reviewer',orgId='org-atomicity-probe',teamId='team-atomicity-probe',repoId='repo-atomicity-probe';
organizations.create({id:orgId,identifier:'atomicity-probe',displayName:'Atomicity probe',owners:[owner],members:[owner,member]});
teams.create({id:teamId,organizationId:orgId,name:'atomicity-team',parentId:null,directMembers:[member]});
repositories.create({id:repoId,name:'atomicity-repo',ownerId:orgId,ownerType:'organization',visibility:'Private',branches:[],files:[]});
grants.create({id:'grant-atomicity-probe',repositoryId:repoId,subjectType:'account',subjectId:member,role:'Write'});
const session=sessions.create({accountId:owner,active:true});
const snapshot=()=>({organization:organizations.get(orgId),team:teams.get(teamId),directGrants:grants.list(g=>g.repositoryId===repoId&&g.subjectId===member)});
const before=snapshot(),app=express();app.use(express.json());require(path.join(appRoot,'backend/routes/organizations'))(app);app.use((e,req,res,next)=>res.status(e.status||500).json({error:e.message}));
(async()=>{
 const server=app.listen(0,'127.0.0.1');await new Promise(resolve=>server.once('listening',resolve));
 const rename=fs.renameSync;let injected=0;
 fs.renameSync=function(source,target){if(path.dirname(target)===directory && path.basename(target)==='teams.json'){injected++;throw new Error('Injected team-store persistence failure');}return rename.apply(this,arguments);};
 let response,body;
 try {response=await fetch(`http://127.0.0.1:${server.address().port}/api/organizations/atomicity-probe/members/bob-reviewer`,{method:'DELETE',headers:{'x-session-id':session.id}});body=await response.json();}
 finally {fs.renameSync=rename;await new Promise(resolve=>server.close(resolve));}
 const after=snapshot();const result={requirement:'REQ-2-2 inherited atomic removal contract',injected,status:response.status,response:body,before,after,rollbackPreserved:JSON.stringify(before)===JSON.stringify(after)};
 fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({status:result.status,injected,rollbackPreserved:result.rollbackPreserved,memberRemains:after.organization.members.includes(member),teamMemberRemains:after.team.directMembers.includes(member),directGrantRemains:after.directGrants.length>0}));
 fs.rmSync(directory,{recursive:true,force:true});
})().catch(e=>{console.error(e);process.exitCode=1;});
