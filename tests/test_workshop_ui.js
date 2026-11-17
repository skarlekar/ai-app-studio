const {test}=require('node:test');const assert=require('node:assert/strict');
const ui=require('../gptapps/workshop.js');
test('task identities and states are validated before creating links or recovering',()=>{
 assert.equal(ui.safeRunId('a'.repeat(32)),true);assert.equal(ui.safeRunId('../private'),false);
 assert.equal(ui.activeRun({state:'running'}),true);assert.equal(ui.activeRun({state:'needs_reconciliation'}),false);
 assert.equal(ui.activeRun({state:'completed'}),false);
});
test('artifact and source URLs stay on the scoped application endpoints',()=>{
 const link=ui.artifactUrl('app & other','a'.repeat(32));
 assert.equal(link,'/api/artifacts/'+ 'a'.repeat(32)+'/content?app=app%20%26%20other');
 assert.throws(()=>ui.artifactUrl('app','../../secret'));
 assert.equal(ui.sourceUrl('app','b'.repeat(32),'file-x').startsWith('/api/sources?app=app&run='),true);
});
test('unknown or unavailable usage is described without inventing a dollar amount',()=>{
 assert.match(ui.usageLabel(null),/pending/i);
 assert.match(ui.usageLabel({total_tokens:42}),/42/);
 assert.doesNotMatch(ui.usageLabel({total_tokens:42}),/\$/);
});
test('local recovery markers carry identities only, never prompts or attachment bytes',()=>{
 const item=ui.recoveryMarker({id:'a'.repeat(32),session_id:'managed-example',submission_id:'request-test',message:'SECRET',attachments:['SECRET']});
 assert.deepEqual(Object.keys(item).sort(),['id','session_id','submission_id']);
 assert.doesNotMatch(JSON.stringify(item),/SECRET/);
});

const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const chatSource=fs.readFileSync(path.join(__dirname,'../gptapps/chat.js'),'utf8');
const workshopSource=fs.readFileSync(path.join(__dirname,'../gptapps/workshop.js'),'utf8');
class ViewNode{
 constructor(text='',className=''){this.textContent=text;this.className=className;this.children=[];this.value='';this.disabled=false;this.dataset={};this.classList={add(){},remove(){}};}
 append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}
 replaceChildren(...nodes){this.children=[];this.append(...nodes);}
 setAttribute(){}
 querySelector(selector){return this.children.find(n=>n.className===selector.slice(1))||null;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 replaceWith(node){const parent=this.parent,index=parent?.children.indexOf(this);if(index>=0){node.remove();parent.children[index]=node;node.parent=parent;}}
 focus(){}
}
function managedView(fetch){
 const nodes={},storage=new Map();const get=id=>nodes[id]||(nodes[id]=new ViewNode());
 const c=vm.createContext({fetch,Response,AbortController,crypto:require('node:crypto').webcrypto,console,
  document:{querySelectorAll:()=>[]},$:get,current:{id:'app',runtime:{api:'agents',model:'test-agent'}},sid:null,busy:false,wizard:null,knowledgeBusy:false,
  chatFiles:[{name:'brief.txt',size:5}],localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
  element:(tag,text='',className='')=>new ViewNode(text,className),setInput:text=>{get('input').value=text;},
  chatFilePayload:async files=>files,clearChatFiles:()=>{c.chatFiles=[];},routingClear(){},routingShow(){},routingRestore(){},
  closeHistory(){},resetKnowledge(){},welcome(){get('messages').replaceChildren(new ViewNode('Welcome'));},sessions:async()=>{},
  renderMarkdown:(node,text)=>{node.textContent=text;},scrollChat(){},showError:error=>{get('error').textContent=error.message;},
  updateChrome:()=>{for(const id of ['input','send','chat-attach'])get(id).disabled=c.busy;},
  message:m=>{const node=new ViewNode();node.append(new ViewNode(m.content||'','body'));get('messages').append(node);return node;}});
 vm.runInContext(chatSource.slice(chatSource.indexOf('async function api('),chatSource.indexOf('function element(')),c);
 vm.runInContext(workshopSource,c);
 vm.runInContext(chatSource.slice(chatSource.indexOf('async function start('),chatSource.indexOf('const steps=')),c);
 c.streamChat=async()=>({session_id:'managed-accepted',message:{role:'assistant',content:'Done'}});
 return {c,nodes,storage,get,state:()=>vm.runInContext('workshopRun',c)};
}
const jsonResponse=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
const accepted={id:'a'.repeat(32),session_id:'managed-accepted',state:'running',model:'test-agent'};
async function reached(predicate){for(let i=0;i<30&&!predicate();i++)await Promise.resolve();assert.ok(predicate(),'Reached async boundary');}

test('leaving active work restores an editable new conversation',async()=>{
 const {c,get}=managedView(async()=>jsonResponse({}));c.busy=true;c.updateChrome();
 await c.start(false);
 assert.equal(c.busy,false);assert.equal(get('input').disabled,false);assert.equal(get('send').disabled,false);assert.equal(get('chat-attach').disabled,false);
});

test('definite rejection restores draft and files and forgets nonexistent work',async()=>{
 const {c,get,storage,state}=managedView(async(path,options)=>options?.method==='POST'?jsonResponse({error:'Install optional Agents support'},400):jsonResponse({error:'Run not found'},404));
 await c.sendManaged('My original question');
 assert.equal(get('input').value,'My original question');assert.equal(get('input').disabled,false);
 assert.equal(c.chatFiles[0].name,'brief.txt');assert.equal(state(),null);
 assert.deepEqual(JSON.parse(storage.get('studio-managed-app')),[]);
 assert.match(get('error').textContent,/Install optional Agents support/);
});

test('ambiguous network failure keeps recovery identity and blocks duplicate submission',async()=>{
 const {c,get,storage,state}=managedView(async(path,options)=>{if(options?.method==='POST')throw new TypeError('Connection lost');return jsonResponse({error:'Run not found'},404);});
 await c.sendManaged('Original request');
 assert.equal(state().state,'reconnecting');assert.equal(get('input').disabled,true);
 assert.equal(JSON.parse(storage.get('studio-managed-app')).length,1);
});

test('late acceptance cannot overwrite a detached conversation or open a stale observer',async()=>{
 let reply,posted=false,observations=0;
 const {c,storage}=managedView(async(path,options)=>{if(options?.method==='POST'){posted=true;return new Promise(resolve=>reply=resolve);}return jsonResponse(accepted);});
 c.streamChat=async()=>{observations++;return {session_id:accepted.session_id,message:{content:'Done'}};};
 const sending=c.sendManaged('Background task');await reached(()=>posted);await c.start(false);
 reply(jsonResponse(accepted,202));await sending;
 assert.equal(c.sid,null);assert.equal(observations,0);assert.equal(c.busy,false);
 assert.equal(JSON.parse(storage.get('studio-managed-app'))[0].id,accepted.id);
});

test('late result snapshot cannot replace the status of a new conversation',async()=>{
 let resolveSnapshot,reading=false;
 const {c,state}=managedView(async(path,options)=>{if(options?.method==='POST')return jsonResponse(accepted,202);reading=true;return new Promise(resolve=>resolveSnapshot=resolve);});
 const sending=c.sendManaged('Task');await reached(()=>reading);await c.start(false);
 resolveSnapshot(jsonResponse({...accepted,state:'completed'}));await sending;
 assert.equal(c.sid,null);assert.equal(state(),null);assert.equal(c.busy,false);
});
