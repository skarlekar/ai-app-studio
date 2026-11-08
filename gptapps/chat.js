const $=id=>document.getElementById(id);let apps=[],current=null,sid=null,busy=false,wizard=null,builderEnabled=false;
async function api(path,options){const response=await fetch(path,options);const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed');return data}
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el}
function showError(error){$('error').textContent=error.message||String(error)}
function initial(name){return Array.from((name||'A').trim())[0]?.toUpperCase()||'A';}
function resizeComposer(){const input=$('input');input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px';}
function setInput(text){$('input').value=text;resizeComposer();}
function icon(name){const node=element('span',undefined,'icon icon-'+name);node.setAttribute('aria-hidden','true');return node;}
function emptyWorkspace(){
 wizard=null;sid=null;resetKnowledge();closeHistory();$('messages').replaceChildren();$('sessions').replaceChildren();setInput('');
 const box=element('div');box.id='welcome';box.append(element('div','YOUR APP STUDIO','welcome-kicker'),element('h2','Create your first application.'));
 const copy=element('p','Turn a GPT into a standalone app. Start the guided setup when you’re ready.');copy.id='description';box.append(copy);
 const button=element('button','Create application','empty-create');button.onclick=beginSetup;box.append(button);$('messages').append(box);updateChrome();
}
function closeHistory(){document.querySelector('aside').classList.remove('history-open');$('history-toggle').setAttribute('aria-expanded','false');}
function updateContinueButtons(){
 const last=$('messages').lastElementChild;
 document.querySelectorAll('.continue-response').forEach(button=>button.disabled=busy||knowledgeBusy||knowledgeMode||!!wizard||button.closest('.message')!==last);
}
function updateChrome(){
 const working=busy||knowledgeBusy;
 document.body.classList.toggle('builder-mode',builderEnabled);document.body.classList.toggle('is-setting-up',!!wizard);
 $('setup-controls').hidden=!wizard;
 $('setup-back').disabled=working||!wizard||wizard.step===0;
 $('setup-cancel').disabled=working;
 $('new').disabled=working||!!wizard||!current;
 $('create').disabled=working||!!wizard;
 $('download').disabled=working||!!wizard||!current;
 $('knowledge-open').disabled=working||!!wizard||!current;
 $('apps').disabled=working||!!wizard||!apps.length;
 $('input').disabled=working||(!wizard&&!current);$('send').disabled=working||(!wizard&&!current);
 updateContinueButtons();
 $('brand-title').textContent=builderEnabled?'App Studio':'Workspace';
 $('brand-subtitle').textContent=builderEnabled?'Ideas, made into applications.':'Your personal AI workspace.';
 $('catalog-count').textContent=apps.length+' '+(apps.length===1?'app':'apps');
 $('header-mark').textContent=wizard?'S':initial(current?.name);
 $('header-eyebrow').textContent=wizard?'APPLICATION SETUP':builderEnabled?'YOUR APP STUDIO':'YOUR WORKSPACE';
 $('name').textContent=wizard?'Create an application':current?.name||'App Studio';
 $('mode').textContent=wizard?(wizard.step===steps.length?'Review':'Step '+(wizard.step+1)+' of '+steps.length):builderEnabled?'Studio':'Personal';
 $('input').placeholder=wizard?'Write your answer…':current?'Message '+current.name+'…':'Create an application to begin…';
 document.title=wizard?'Create an application · App Studio':current?.name||'App Studio';
 updateKnowledgePanel();
}
function renderMarkdown(body, text) {
 if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') { body.textContent=text; return; }
 const fragment=DOMPurify.sanitize(marked.parse(text,{gfm:true,breaks:false,async:false}),{
  RETURN_DOM_FRAGMENT:true,
  ALLOWED_TAGS:['p','br','strong','em','del','s','pre','code','blockquote','ul','ol','li','h1','h2','h3','h4','h5','h6','hr','table','thead','tbody','tr','th','td','a','input'],
  ALLOWED_ATTR:['href','title','class','start','align','type','checked','disabled'],
  ALLOW_DATA_ATTR:false,ALLOW_ARIA_ATTR:false
 });
 for(const node of fragment.querySelectorAll('[class]')){const language=node.tagName==='CODE'&&(node.getAttribute('class')||'').match(/^language-[a-z0-9_-]+$/i);if(!language)node.removeAttribute('class');}
 for(const link of fragment.querySelectorAll('a')){
  if(!/^(https?:\/\/|mailto:)/i.test(link.getAttribute('href')||''))link.removeAttribute('href');
  link.target='_blank';link.rel='noopener noreferrer';
 }
 for(const input of fragment.querySelectorAll('input')){input.type='checkbox';input.disabled=true;}
 for(const table of fragment.querySelectorAll('table')){
  const wrapper=element('div',undefined,'table-scroll');table.replaceWith(wrapper);wrapper.append(table);
 }
 body.replaceChildren(fragment);
}
function scrollChat(force=false){const list=$('messages');if(force||list.scrollHeight-list.scrollTop-list.clientHeight<180)list.scrollTop=list.scrollHeight;}
function message(m){
 const box=element('div',undefined,'message '+m.role+(wizard?' setup':''));
 const role=element('div',m.role==='user'?'You':wizard?'Application setup':current.name,'role');if(m.role==='assistant'){const avatar=element('div',wizard?'S':initial(current?.name),'message-avatar');avatar.setAttribute('aria-hidden','true');box.append(avatar);}box.append(role);
 const body=element('div',undefined,'body');
 if(m.role==='assistant'&&!wizard)renderMarkdown(body,m.content||'');else body.textContent=m.content||'';
 box.append(body);
 for(const asset of m.assets||[]){const img=element('img');img.src='/assets/'+encodeURIComponent(asset);img.alt='Generated image';box.append(img);}
 const sources=element('div',undefined,'sources');
 for(const source of m.citations||[]){let el;if(/^https?:\/\//i.test(source.url||'')){el=element('a',source.title);el.href=source.url;el.target='_blank';el.rel='noopener noreferrer';}else el=element('span',source.title);sources.append(el);}
 box.append(sources);
 if(m.role==='assistant'&&m.incomplete_reason==='max_output_tokens'){
  const notice=element('div',undefined,'response-notice');notice.setAttribute('role','note');
  notice.append(element('p','This answer reached its length limit. Your partial answer is saved. Continue to ask for the next part.'));
  const button=element('button','Continue response','continue-response');button.type='button';
  button.onclick=()=>{
   if(busy||wizard||box!==$('messages').lastElementChild)return;
   if($('input').value.trim())return showError(new Error('Send or clear your draft before continuing this response.'));
   $('error').textContent='';sendChat('Continue the previous answer from where it stopped. Do not repeat what you already wrote.');
  };
  notice.append(button);box.append(notice);
 }
 $('messages').append(box);updateContinueButtons();scrollChat(true);return box;
}
async function streamChat(payload,onEvent){
 const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},body:JSON.stringify({...payload,stream:true})});
 if(!response.ok){const data=await response.json();throw new Error(data.error||'Request failed');}
 if(!response.body||!response.headers.get('Content-Type')?.includes('text/event-stream'))throw new Error('The server did not return a chat stream. Restart the server and refresh this page.');
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
 try{
  while(true){
   const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
   let match;
   while((match=/\r?\n\r?\n/.exec(buffer))){
    const frame=buffer.slice(0,match.index);buffer=buffer.slice(match.index+match[0].length);
    const data=frame.split(/\r?\n/).filter(line=>line.startsWith('data:')).map(line=>line.slice(5).replace(/^ /,'')).join('\n');
    if(!data)continue;
    let event;try{event=JSON.parse(data);}catch{throw new Error('The chat stream was invalid. Check saved conversations before retrying.');}
    if(event.type==='error')throw new Error(event.error||'Chat response failed');
    if(event.type==='done')return event;
    onEvent(event);
   }
   if(done)throw new Error('The connection ended before completion was confirmed. Check saved conversations before retrying.');
  }
 }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
async function sendChat(text){
 $('welcome')?.remove();const oldCount=$('messages').children.length;
 message({role:'user',content:text});setInput('');loading(true);
 const pending=message({role:'assistant',content:''}),body=pending.querySelector('.body');
 pending.classList.add('streaming');pending.setAttribute('aria-busy','true');pending.setAttribute('aria-live','off');body.textContent='Thinking…';
 const parts=new Map();let frame=0,active=true;
 const draw=()=>{frame=0;if(!active)return;const follow=$('messages').scrollHeight-$('messages').scrollTop-$('messages').clientHeight<180;
  const text=[...parts.values()].sort((a,b)=>a.index-b.index||a.part-b.part).map(p=>p.text).join('\n');
  if(text)renderMarkdown(body,text);else body.textContent='Thinking…';if(follow)scrollChat(true);
 };
 const schedule=()=>{if(!frame)frame=requestAnimationFrame(draw);};
 try{
  const result=await streamChat({app_id:current.id,session_id:sid,message:text},event=>{
   if(event.type==='reset'){parts.clear();$('status').textContent='Thinking…';schedule();}
   else if(event.type==='status')$('status').textContent=event.message;
   else if(event.type==='delta'){
    const index=event.output_index||0,part=event.content_index||0,key=index+':'+part;
    if(!parts.has(key))parts.set(key,{index,part,text:''});parts.get(key).text+=event.delta;
    $('status').textContent='Responding…';schedule();
   }
  });
  active=false;if(frame)cancelAnimationFrame(frame);frame=0;
  sid=result.session_id;const completed=message(result.message);pending.replaceWith(completed);await sessions().catch(showError);
 }catch(error){
  while($('messages').children.length>oldCount)$('messages').lastChild.remove();
  setInput(text);showError(error);try{await sessions();}catch{}
 }finally{active=false;if(frame)cancelAnimationFrame(frame);loading(false);$('input').focus();}
}
function welcome(){
 const box=element('div');box.id='welcome';box.append(element('div','A space for your next idea','welcome-kicker'));
 box.append(element('h2',current.name));const description=element('p',current.description);description.id='description';box.append(description);
 const starters=element('div');starters.id='starters';
 current.starters.forEach((text,index)=>{
  const button=element('button'),number=element('span',String(index+1).padStart(2,'0'),'starter-number'),arrow=icon('arrow-up-right');arrow.classList.add('starter-arrow');
  number.setAttribute('aria-hidden','true');arrow.setAttribute('aria-hidden','true');button.append(number,arrow,element('span',text,'starter-label'));
  button.onclick=()=>{setInput(text);$('input').focus();};starters.append(button);
 });
 box.append(starters);box.append(element('div','Pick a starting point, or make the conversation your own.','welcome-footnote'));
 $('messages').replaceChildren(box);
}
async function sessions(){const records=await api('/api/sessions?app='+encodeURIComponent(current.id));$('sessions').replaceChildren();if(!records.length)$('sessions').append(element('div','No conversations yet','empty'));for(const item of records){const button=element('button',item.title,'session'+(item.id===sid?' active':''));button.title=item.title;button.disabled=busy;button.onclick=async()=>{try{const saved=await api('/api/sessions?app='+encodeURIComponent(current.id)+'&id='+encodeURIComponent(item.id));sid=saved.id;$('messages').replaceChildren();saved.messages.forEach(message);closeHistory();await sessions()}catch(e){showError(e)}};$('sessions').append(button)}}
async function start(){closeHistory();wizard=null;resetKnowledge();sid=null;$('input').maxLength=16000;$('error').textContent='';$('apps').disabled=false;updateChrome();welcome();await sessions();$('input').focus()}
function loading(value){busy=value;$('send').disabled=value;$('apps').disabled=value||!!wizard;$('new').disabled=value;$('create').disabled=value;$('input').disabled=value;document.querySelectorAll('.session').forEach(b=>b.disabled=value);$('status').textContent=value?'Working…':'Ready';$('status').dataset.state=value?'busy':'ready';updateChrome()}
const steps=[
 {key:'name',question:'What is the name of your application?'},
 {key:'description',question:'Describe what it helps people do, or type skip.'},
 {key:'instructions',question:'Paste your GPT’s full instructions. I will preserve them as application configuration. Do not include API keys, passwords or credentials.'},
 {key:'starters',question:'Enter conversation starters, one per line (up to 12), or type none.'},
 {key:'tools',question:'Which capabilities / tool settings should be enabled? Choose web search, image generation, code interpreter, any combination, all, or none. Availability depends on the model.'},
 {key:'model',question:'Enter the OpenAI model ID, or type default to use the server’s OPENAI_MODEL setting. This app setting is separate from the server model used for setup.'},
 {key:'knowledge_files',question:'Choose your knowledge files in the upload panel, upload and index them, then select Use these files. You can select multiple documents. If your GPT has no knowledge files, type none.'},
 {key:'actions',question:'Type none, or paste your Actions as a JSON array. Each Action needs name, auth_type (none, api_key, oauth), and schema (an OpenAPI JSON object). Include definitions only, never credentials.\n\nExample:\n[{"name":"Lookup","auth_type":"none","schema":{"openapi":"3.1.0","info":{"title":"Lookup","version":"1.0"},"paths":{}}}]\n\nActions need reviewed backend adapters before execution.'}
];
function setupMessage(text,role='assistant'){message({role,content:text})}
function beginSetup(){resetKnowledge();closeHistory();wizard={step:0,draft:{},history:[]};sid=null;$('messages').replaceChildren();$('sessions').replaceChildren();$('name').textContent='Create an application';$('error').textContent='';setInput('');$('input').maxLength=1000000;$('apps').disabled=true;setupMessage('Tell me about your GPT. I’ll interpret your answers and ask when something is unclear; you’ll review everything before creating the app.');setupMessage(steps[0].question);updateChrome();$('input').focus()}
function previousSetupStep(){wizard.step=Math.max(0,wizard.step-1);wizard.history=[];updateChrome();setupMessage(steps[wizard.step].question)}
async function cancelSetup(){if(current)await start();else emptyWorkspace()}
function reviewDraft(){const d=wizard.draft;setupMessage('Review your application:\n\nName: '+d.name+'\nDescription: '+(d.description||'None')+'\nInstructions: '+d.instructions.length+' characters, preserved as entered\nStarters: '+(d.starters.join(' | ')||'None')+'\nCapabilities / tools: '+(d.tools.join(', ')||'None')+'\nModel: '+(d.model||'Server default')+'\nKnowledge files: '+(d.knowledge_files.join(', ')||'None')+'\nActions: '+(d.actions.map(a=>a.name+' ('+a.auth_type+')').join(', ')||'None')+'\n\nType create to save, back to revise Actions, or cancel to leave setup.');}
async function saveDraft(){
 const created=await api('/api/apps',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(wizard.draft)});
 apps=await api('/api/apps');$('apps').replaceChildren();
 for(const app of apps){const option=element('option',app.name);option.value=app.id;$('apps').append(option)}
 current=apps.find(a=>a.id===created.id);$('apps').value=current.id;wizard=null;await start();$('welcome')?.remove();
 $('messages').append(element('div','Application created. Your configuration is saved.','empty'));
 if(created.report.issues.length){const report=element('div',undefined,'message');report.append(element('div','Compatibility review','role'));report.append(element('div',created.report.issues.map(i=>'• '+i.message).join('\n'),'body'));$('messages').append(report)}
 const button=element('button','Download application configuration');button.onclick=downloadSpec;$('messages').append(button)
}
async function intake(text){
 if(/^cancel$/i.test(text.trim())){await cancelSetup();return}
 if(/^back$/i.test(text.trim())){setupMessage(text,'user');previousSetupStep();return}
 loading(true);
 try{
  if(wizard.step===steps.length&&/^create$/i.test(text.trim())){await saveDraft();return}
  const field=steps[wizard.step]?.key||'review';
  const result=await api('/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({field,message:text,history:wizard.history})});
  setupMessage(text,'user');
  if(result.status==='clarify'){
   wizard.history=[...wizard.history,{role:'user',content:text},{role:'assistant',content:result.message}].slice(-8);
   setupMessage(result.message);if(field==='knowledge_files'){$('knowledge-guidance').textContent=result.message;$('knowledge-guidance').hidden=false;}return
  }
  wizard.history=[];
  if(result.status==='back'){previousSetupStep();return}
  if(result.status==='cancel'){await cancelSetup();return}
  if(result.status==='create'){await saveDraft();return}
  if(result.status!=='accept'||field==='review')throw new Error('Could not interpret that reply. Please try again.');
  if(field==='knowledge_files'){
   delete wizard.draft.knowledge_upload_id;
   if(result.value.length){wizard.draft.knowledge_files=result.value;const prompt='Choose these documents in the upload panel, upload and index them, then select Use these files.';setupMessage(prompt);$('knowledge-guidance').textContent=prompt;$('knowledge-guidance').hidden=false;return;}
  }
  wizard.draft[field]=result.value;setupMessage(result.message);wizard.step++;updateChrome();
  if(wizard.step===steps.length)reviewDraft();else setupMessage(steps[wizard.step].question)
 }finally{loading(false);$('input').focus()}
}
async function downloadSpec(){try{const config=await api('/api/spec?app='+encodeURIComponent(current.id));const url=URL.createObjectURL(new Blob([JSON.stringify(config,null,2)],{type:'application/json'}));const link=element('a');link.href=url;link.download=current.id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){showError(e)}}
const createButton=element('button');createButton.append(icon('plus'),element('span','Create application'));createButton.id='create';createButton.hidden=true;createButton.onclick=()=>{if(!busy&&!wizard)beginSetup();};$('new').before(createButton);
const exportButton=element('button');exportButton.append(icon('download'),element('span','Download standalone app'));exportButton.id='download';exportButton.hidden=true;exportButton.onclick=async()=>{if(!current)return showError(new Error('Create an application first.'));try{const response=await fetch('/api/build?app='+encodeURIComponent(current.id));if(!response.ok)throw new Error('Application packaging failed');const url=URL.createObjectURL(await response.blob());const link=element('a');link.href=url;link.download=current.id+'-app.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){showError(error)}};$('new').after(exportButton);
const knowledgeButton=element('button');knowledgeButton.append(icon('layers'),element('span','Knowledge files'));knowledgeButton.id='knowledge-open';knowledgeButton.hidden=true;knowledgeButton.onclick=()=>{if(!busy&&!knowledgeBusy&&!wizard&&current){knowledgeMode=true;closeHistory();updateChrome();}};$('download').after(knowledgeButton);
$('new').onclick=()=>{if(current)start().catch(showError);else beginSetup();};
$('apps').onchange=()=>{current=apps.find(a=>a.id===$('apps').value);$('name').textContent=current.name;start().catch(showError)};
$('input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('form').requestSubmit()}};
$('form').onsubmit=async e=>{
 e.preventDefault();const raw=$('input').value,text=raw.trim();if(busy||knowledgeBusy||knowledgeMode||!text)return;$('error').textContent='';
 if(wizard){setInput('');try{await intake(steps[wizard.step]?.key==='instructions'?raw:text);}catch(error){setInput(raw);showError(error);}return;}
 await sendChat(text);
};
$('input').addEventListener('input',resizeComposer);
$('setup-back').onclick=()=>{if(wizard&&!busy&&!knowledgeBusy&&wizard.step>0)previousSetupStep();};
$('setup-cancel').onclick=()=>{if(!busy&&!knowledgeBusy)cancelSetup().catch(showError);};
$('history-toggle').onclick=()=>{const open=document.querySelector('aside').classList.toggle('history-open');$('history-toggle').setAttribute('aria-expanded',String(open));};
initKnowledge();
(async()=>{try{const config=await api('/api/config');builderEnabled=config.builder_enabled;knowledgeLimits=config.knowledge_uploads||{};$('create').hidden=!config.builder_enabled;$('download').hidden=!config.builder_enabled;$('knowledge-open').hidden=!config.builder_enabled;apps=await api('/api/apps');for(const app of apps){const option=element('option',app.name);option.value=app.id;$('apps').append(option)}current=apps[0];if(!current){if(config.builder_enabled)beginSetup();else throw new Error('No applications configured.')}else{$('name').textContent=current.name;await start()}}catch(error){showError(error);$('send').disabled=true}})();
