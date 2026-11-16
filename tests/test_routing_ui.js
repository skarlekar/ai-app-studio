// Dependency-free routing status and chat lifecycle checks.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const routingPath=path.join(root,'gptapps/routing.js');
const routingSource=fs.existsSync(routingPath)?fs.readFileSync(routingPath,'utf8'):'';
const chatSource=fs.readFileSync(path.join(root,'gptapps/chat.js'),'utf8');

class Node {
 constructor(tag='div',text=''){this.tagName=tag.toUpperCase();this.textContent=text;this.children=[];this.hidden=false;this.dataset={};this.attributes={};this.value='';this.classList={add(){},remove(){}};}
 set textContent(value){this.text=String(value);this.children=[];}
 get textContent(){return this.text+this.children.map(child=>child.textContent).join(' ');}
 set innerHTML(value){throw new Error('Routing must use safe text nodes');}
 setAttribute(name,value){this.attributes[name]=String(value);}
 append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}
 replaceChildren(...nodes){this.text='';this.children=[];this.append(...nodes);}
 querySelector(selector){if(selector==='.body')return this.children.find(node=>node.className==='body');return null;}
 get lastChild(){return this.children.at(-1);}
 get lastElementChild(){return this.lastChild;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(node=>node!==this);}
 replaceWith(node){const index=this.parent?.children.indexOf(this);if(index>=0){node.remove();node.parent=this.parent;this.parent.children[index]=node;}}
 focus(){}
}
function ui(){
 const nodes={};
 for(const id of ['routing-status','routing-state','routing-model','routing-route','routing-summary','routing-details','routing-detail-list','model-choices','model-auto','model-fixed','model-routing-help','messages','input','status','error','form','sessions'])nodes[id]=new Node();
 const element=(tag,text,className)=>{const node=new Node(tag,text===undefined?'':text);node.className=className||'';return node;};
 const c=vm.createContext({document:{createElement:tag=>new Node(tag)},$:id=>nodes[id],element});
 vm.runInContext(routingSource,c);
 return {c,nodes,element};
}
const record={mode:'auto',requested_model:'answer-2026-10-01',route:'economy',task:'summary',summary:'Economy route: routine summary.',reason_codes:['classified'],fallback:false,router_model:'router-2026-10-01',policy_version:'reviewed-v1',evidence:{history_messages:8,history_truncated:true,metadata_only_files:1,excerpt_chars:4000},router_usage:{input_tokens:80,output_tokens:4},selection_ms:20};
function renderer(c){assert.equal(typeof c.routingShow,'function','Routing status renderer is available');}

test('shows requested identity until the answering provider reports its model, separately from the router',()=>{
 const {c,nodes}=ui();renderer(c);
 c.routingShow(record);
 assert.match(nodes['routing-model'].textContent,/requested.*answer-2026-10-01/i);
 assert.match(nodes['routing-state'].textContent,/not confirmed saved/i);
 assert.match(nodes['routing-detail-list'].textContent,/Router model.*router-2026-10-01/);
 assert.equal(nodes['routing-details'].open,false);
 c.routingShow({...record,reported_model:'provider-answer-2026-10-02',answer_usage:{input_tokens:100,output_tokens:22},answer_ms:350},'saved');
 assert.match(nodes['routing-model'].textContent,/reported.*provider-answer-2026-10-02/i);
 assert.match(nodes['routing-detail-list'].textContent,/Requested answer model.*answer-2026-10-01/);
 assert.match(nodes['routing-state'].textContent,/Saved turn/);
 assert.match(nodes['routing-detail-list'].textContent,/Answer input tokens.*100/);
 assert.match(nodes['routing-detail-list'].textContent,/Router input tokens.*80/);
});

test('renders safe bounded text and whitelisted coverage without raw evidence or arbitrary usage fields',()=>{
 const {c,nodes}=ui();renderer(c);
 c.routingShow({...record,summary:'<img src=x onerror=alert(1)>',reported_model:'<script>bad</script>',fallback:true,reason_codes:['router_timeout'],evidence:{...record.evidence,excerpt:'SECRET-DOCUMENT',message:'SECRET-PROMPT',history_messages:'SECRET-NOT-A-COUNT'},router_usage:{input_tokens:80,secret:'SECRET-USAGE'}});
 assert.equal(nodes['routing-summary'].textContent,'<img src=x onerror=alert(1)>');
 assert.match(nodes['routing-route'].textContent,/Fallback used/);
 assert.match(nodes['routing-model'].textContent,/requested.*answer-2026-10-01/i);
 const details=nodes['routing-detail-list'].textContent;
 assert.doesNotMatch(details,/SECRET|<script>/);
 assert.match(details,/metadata.only.*1/i);
 assert.match(details,/Router timeout/i);
 c.routingShow(null);assert.equal(nodes['routing-status'].hidden,true);
});

test('beginning a turn clears stale model details and failed attempts never appear saved',()=>{
 const {c,nodes}=ui();renderer(c);
 c.routingShow({...record,reported_model:'old-answer'},'saved');
 c.routingBegin();
 assert.match(nodes['routing-state'].textContent,/Selecting.*model/i);
 assert.equal(nodes['routing-model'].textContent,'');
 assert.equal(nodes['routing-detail-list'].textContent,'');
 c.routingShow(record);c.routingFailed();
 assert.match(nodes['routing-state'].textContent,/not confirmed saved/i);
 c.routingRestore([{role:'assistant',routing:record},{role:'user',content:'next'},{role:'assistant',routing:{...record,requested_model:'latest-answer'}}]);
 assert.match(nodes['routing-model'].textContent,/latest-answer/);
 assert.match(nodes['routing-state'].textContent,/Saved turn/);
 c.routingRestore([{role:'assistant',content:'legacy'}]);assert.equal(nodes['routing-status'].hidden,true);
 c.routingClear();assert.equal(nodes['routing-detail-list'].textContent,'');
});

test('fixed turns work without a router and malformed metadata cannot claim a model identity',()=>{
 const {c,nodes}=ui();renderer(c);
 c.routingShow({mode:'fixed',requested_model:'fixed-model',summary:'Fixed model configured for this application.'},'saved');
 assert.match(nodes['routing-model'].textContent,/requested.*fixed-model/i);
 assert.match(nodes['routing-route'].textContent,/Fixed model/);
 assert.doesNotMatch(nodes['routing-detail-list'].textContent,/Router model/);
 c.routingShow({mode:'auto',requested_model:'x'.repeat(500),reported_model:{unexpected:true},router_model:'x'.repeat(500),summary:'x'.repeat(2000)});
 assert.doesNotMatch(nodes['routing-model'].textContent,/xxx|object Object/);
 assert.ok(nodes['routing-summary'].textContent.length<=501);
});

function sendClient(result){
 const {c,nodes,element}=ui();
 Object.assign(c,{chatFiles:[{name:'brief.pdf',size:4}],current:{id:'app'},sid:'session',requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},loading:()=>{},setInput:text=>{nodes.input.value=text;},showError:error=>{nodes.error.textContent=error.message;},chatFilePayload:async files=>files,sessions:async()=>{},clearChatFiles:()=>{c.chatFiles=[];},renderMarkdown:(node,text)=>{node.textContent=text;},scrollChat:()=>{},message:m=>{const node=element('div');node.append(element('div',m.content||'','body'));nodes.messages.append(node);return node;}});
 c.streamChat=async(payload,onEvent)=>{onEvent({type:'routing',routing:record});if(result instanceof Error)throw result;return result;};
 vm.runInContext(chatSource.slice(chatSource.indexOf('async function sendChat('),chatSource.indexOf('function welcome(')),c);
 return {c,nodes};
}
test('a streamed route stays unconfirmed until done and a failed attempt preserves draft and attachments',async()=>{
 const {c,nodes}=sendClient(new Error('Answer failed'));renderer(c);
 await c.sendChat('Summarize');
 assert.match(nodes['routing-model'].textContent,/answer-2026-10-01/);
 assert.match(nodes['routing-state'].textContent,/not confirmed saved/i);
 assert.equal(nodes.input.value,'Summarize');
 assert.equal(c.chatFiles.length,1);
 assert.equal(nodes.messages.children.length,0);
});

test('confirmed completion restores saved routing and clears successful attachments',async()=>{
 const saved={...record,reported_model:'reported-answer'};
 const {c,nodes}=sendClient({session_id:'saved',message:{role:'assistant',content:'Done',routing:saved}});renderer(c);
 await c.sendChat('Summarize');
 assert.match(nodes['routing-model'].textContent,/reported.*reported-answer/i);
 assert.match(nodes['routing-state'].textContent,/Saved turn/);
 assert.equal(c.chatFiles.length,0);
});

test('routing SSE events survive arbitrary boundaries and malformed records are safe to ignore',async()=>{
 const wire=event=>'data: '+JSON.stringify(event)+'\n\n';
 const response=new Response(wire({type:'routing',routing:record})+wire({type:'routing',routing:null})+wire({type:'done',session_id:'saved',message:{routing:record}}),{headers:{'Content-Type':'text/event-stream'}});
 const {c,nodes}=ui();renderer(c);Object.assign(c,{fetch:async()=>response,TextDecoder,Uint8Array});
 vm.runInContext(chatSource.slice(chatSource.indexOf('async function streamChat('),chatSource.indexOf('async function sendChat(')),c);
 const result=await c.streamChat({},event=>{if(event.type==='routing')c.routingShow(event.routing);});
 assert.equal(result.session_id,'saved');assert.equal(nodes['routing-status'].hidden,true);
});

test('model choices send the existing exact Auto/default values and explain unavailable routing',()=>{
 const {c,nodes}=ui();
 Object.assign(c,{wizard:{step:0},steps:[{key:'model'}],busy:false,knowledgeBusy:false,routingAvailable:true,routingError:'',setInput:text=>{nodes.input.value=text;}});
 nodes.form.requestSubmit=()=>{nodes.form.submitted=nodes.input.value;};
 const start=chatSource.indexOf('function updateModelChoices('),end=chatSource.indexOf('function renderMarkdown(');
 assert.ok(start>=0,'Model setup offers explicit mode choices');
 vm.runInContext(chatSource.slice(start,end),c);c.updateModelChoices();
 assert.equal(nodes['model-choices'].hidden,false);nodes['model-auto'].onclick();assert.equal(nodes.form.submitted,'auto');
 nodes['model-fixed'].onclick();assert.equal(nodes.form.submitted,'default');
 c.routingAvailable=false;c.routingError='Configure a routing policy first.';c.updateModelChoices();
 assert.equal(nodes['model-auto'].disabled,true);assert.equal(nodes['model-fixed'].disabled,false);
 assert.match(nodes['model-routing-help'].textContent,/Configure a routing policy/);
 c.wizard=null;c.updateModelChoices();assert.equal(nodes['model-choices'].hidden,true);
});

test('unrecognized enum and reason values cannot render inherited object properties or break the status',()=>{
 const {c,nodes}=ui();renderer(c);
 assert.doesNotThrow(()=>c.routingShow({...record,route:'constructor',task:'toString',reason_codes:[{toString:{}},'__proto__','router_timeout']}));
 assert.equal(nodes['routing-route'].textContent,'Auto — cost-first');
 assert.match(nodes['routing-detail-list'].textContent,/Router timeout/);
 assert.doesNotMatch(nodes['routing-detail-list'].textContent,/function|object Object|native code/);
});

test('shows actual router coverage and classification probabilities while keeping binary context explicitly unknown',()=>{
 const {c,nodes}=ui();renderer(c);
 c.routingShow({...record,reason_codes:['classified'],probabilities:{effort:0.87,task:0.9},evidence:{current_chars:80,app_chars:100,app_truncated:true,history_messages:8,history_omitted_messages:5,history_chars:1200,history_truncated:false,files:3,text_files:1,image_files:1,excerpt_chars:4000,truncated_files:1,metadata_only_files:2,unknown_document_context:true}});
 const details=nodes['routing-detail-list'].textContent;
 assert.match(details,/Request characters considered.*80/);
 assert.match(details,/App evidence characters.*100/);
 assert.match(details,/App evidence truncated.*Yes/);
 assert.match(details,/Older messages omitted.*5/);
 assert.match(details,/Attachment count.*3/);
 assert.match(details,/Image attachments.*1/);
 assert.match(details,/Truncated attachment excerpts.*1/);
 assert.match(details,/Binary document context usage unknown.*Yes/);
 assert.match(details,/Effort classification probability.*87.0%/);
 assert.match(details,/Task classification probability.*90.0%/);
 assert.match(details,/Required effort classified/);
});

test('keeps routing status in the shared sidebar below recent conversations, outside the chat composer',()=>{
 const html=fs.readFileSync(path.join(root,'gptapps/chat.html'),'utf8');
 const sidebar=html.match(/<aside\b[^>]*>([\s\S]*?)<\/aside>/)?.[1]||'';
 assert.match(sidebar,/<nav id="sessions"[\s\S]*?<section id="routing-status"/);
 assert.equal((html.match(/id="routing-status"/g)||[]).length,1);
 assert.doesNotMatch(html.match(/<footer>([\s\S]*?)<\/footer>/)?.[1]||'',/id="routing-status"/);
});
