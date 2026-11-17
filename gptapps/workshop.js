// Shared managed-task UI. Recovery storage contains IDs only, never message/file contents.
function safeRunId(value){return typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);}
function activeRun(run){return !!run&&!['completed','failed','cancelled','needs_reconciliation'].includes(run.state);}
function artifactUrl(app,id){if(!safeRunId(id))throw new Error('Invalid artifact identity');return '/api/artifacts/'+id+'/content?app='+encodeURIComponent(app);}
function sourceUrl(app,run,source){if(!safeRunId(run))throw new Error('Invalid run identity');return '/api/sources?app='+encodeURIComponent(app)+'&run='+run+'&source='+encodeURIComponent(source);}
function usageLabel(usage){return usage&&Number.isSafeInteger(usage.total_tokens)&&usage.total_tokens>=0?usage.total_tokens.toLocaleString()+' recorded tokens':'Usage pending or unavailable; inspect the provider trace.';}
function recoveryMarker(run){return {id:safeRunId(run.id)?run.id:null,session_id:typeof run.session_id==='string'?run.session_id.slice(0,128):null,submission_id:typeof run.submission_id==='string'?run.submission_id.slice(0,128):null};}
if(typeof module!=='undefined'&&module.exports)module.exports={safeRunId,activeRun,artifactUrl,sourceUrl,usageLabel,recoveryMarker};
let workshopGeneration=0,workshopRun=null,workshopController=null,runtimeAvailability={};
function workshopMarkers(app){try{const items=JSON.parse(localStorage.getItem('studio-managed-'+app)||'[]');return Array.isArray(items)?items.filter(x=>x&&typeof x.submission_id==='string'&&/^[A-Za-z0-9_-]{8,128}$/.test(x.submission_id)).slice(-50):[];}catch{return [];}}
function workshopRemember(app,run){try{const marker=recoveryMarker(run);const list=workshopMarkers(app).filter(x=>x.submission_id!==marker.submission_id);list.push(marker);localStorage.setItem('studio-managed-'+app,JSON.stringify(list.slice(-50)));}catch{}}
function workshopForget(app,run){try{const list=workshopMarkers(app).filter(x=>!(run.id&&x.id===run.id)&&x.submission_id!==run.submission_id);localStorage.setItem('studio-managed-'+app,JSON.stringify(list));}catch{}}
function workshopDetach(){workshopGeneration++;workshopController?.abort();workshopController=null;workshopRun=null;if(typeof $==='function'&&$('execution-status'))$('execution-status').hidden=true;}
function updateRuntimeChoices(){
 const key=wizard?steps[wizard.step]?.key:null,show=key==='api',agents=wizard?.draft?.api==='agents';
 if($('quality-status')){$('quality-status').hidden=!!wizard||!current;$('quality-label').textContent=current?.evaluation?.approved?'Reviewed evaluation passed':'Experimental · release hold';$('quality-detail').textContent=current?.evaluation?.approved?'The recorded app configuration passed its owner-reviewed suite.': 'Run task-specific evaluations and complete human review before production.';}
 $('runtime-choices').hidden=!show;$('agent-settings').hidden=!(agents&&key==='model');
 $('runtime-responses').disabled=busy||knowledgeBusy;$('runtime-agents').disabled=busy||knowledgeBusy;
 $('runtime-responses').onclick=()=>{setInput('responses');$('form').requestSubmit();};
 $('runtime-agents').onclick=()=>{setInput('agents');$('form').requestSubmit();};
 $('agents-environment').value=wizard?.draft?.agents?.environment||'openai_hosted';
 $('agents-environment').onchange=()=>{if(wizard)wizard.draft.agents={environment:$('agents-environment').value};};
 $('runtime-availability').textContent=runtimeAvailability.agents?.available?'Agents support is installed. Model/tool access still needs a live check.':'To run Agents inside Studio, restart with ./start.sh --agents or ./docker-start.sh --agents. Generated Agents apps include optional dependency installation.';
 $('runtime-suggest').disabled=busy||knowledgeBusy;
 $('runtime-suggest').onclick=async()=>{if(!wizard)return;loading(true);try{const context='Suggest which runtime best fits this app. Purpose: '+(wizard.draft.description||'')+' Instructions: '+(wizard.draft.instructions||'').slice(0,8000)+' Requested tools: '+(wizard.draft.tools||[]).join(', ');const result=await api('/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({field:'api',message:context})});setupMessage('AI suggestion: '+result.message+' Review the choice before continuing.');if(['responses','agents'].includes(result.value))setInput(result.value);}catch(e){showError(e);}finally{loading(false);}};
}
function workshopArtifacts(m,box){
 if(m.role!=='assistant')return;
 if(m.artifacts?.length){const list=element('div',undefined,'managed-artifacts');for(const item of m.artifacts){if(!safeRunId(item.id))continue;const row=element('div',undefined,'managed-artifact');row.append(element('strong',item.name||'Output file'),element('span',(item.size/1024).toFixed(1)+' KiB'));if(item.expired)row.append(element('span','Expired under the retention policy'));else{const link=element('a','Download file');link.href=artifactUrl(current.id,item.id);link.setAttribute('download','');row.append(link);}list.append(row);}box.append(list);}
 if(m.execution?.runtime==='agents'){const note=element('details',undefined,'managed-receipt');note.append(element('summary','Execution receipt'));note.append(element('p','Agents API · OpenAI-managed orchestration · '+m.execution.state));if(m.routing?.requested_model)note.append(element('p','Fixed model: '+m.routing.requested_model));note.append(element('p',usageLabel(m.routing?.answer_usage)));box.append(note);}
}
function workshopSide(run){
 if(!$('execution-status'))return;$('execution-status').hidden=!run;
 if(!run)return;
 $('execution-model').textContent='Agents API · '+(run.model||current?.runtime?.model||'Configured fixed model');
 $('execution-state').textContent=run.state.replaceAll('_',' ');
 $('execution-policy').textContent='OpenAI-managed session. Fixed model selected by the app owner; no Decisions classification.';
 $('execution-usage').textContent=usageLabel(run.usage);
 $('execution-identity').textContent=run.provider_session_id?'Session: '+run.provider_session_id:'Waiting for provider session confirmation';
}
function workshopPanel(run,pending){
 let panel=pending.querySelector('.managed-task');
 if(!panel){panel=element('section',undefined,'managed-task');panel.setAttribute('aria-label','Managed task progress');pending.append(panel);}
 panel.replaceChildren();panel.append(element('div','MANAGED WORKSHOP','managed-kicker'),element('h3',run.state==='completed'?'Your results are saved':'Your task is '+run.state.replaceAll('_',' ')));
 const status=element('p',run.error||'The application server manages this task independently of this browser connection.');status.setAttribute('role','status');panel.append(status);
 const timeline=element('ol',undefined,'managed-timeline');const labels=[['queued','Accepted'],['preparing','Prepare workspace'],['running','Perform the task'],['finalizing','Validate and save outputs'],['completed','Completed']];const rank={queued:0,preparing:1,running:2,waiting_for_tool:2,reconnecting:2,finalizing:3,completed:4};for(let i=0;i<labels.length;i++){const line=element('li',labels[i][1]);line.dataset.state=rank[run.state]>i?'done':rank[run.state]===i?'current':'pending';timeline.append(line);}panel.append(timeline);
 const buttons=element('div',undefined,'managed-buttons');
 if(activeRun(run)&&safeRunId(run.id)){const cancel=element('button','Cancel task');cancel.type='button';cancel.disabled=run.state==='cancelling';cancel.onclick=async()=>{try{const updated=await api('/api/runs/'+run.id+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:current.id})});workshopRun=updated;workshopPanel(updated,pending);workshopSide(updated);}catch(e){showError(e);}};buttons.append(cancel);}
 if(run.state==='reconnecting'||run.state==='needs_reconciliation'||!safeRunId(run.id)){const refresh=element('button','Reconcile saved status');refresh.type='button';refresh.onclick=()=>workshopRecoverMarker(current.id,recoveryMarker(run)).catch(showError);buttons.append(refresh);}
 const leave=element('button',activeRun(run)?'Leave task running':'New conversation');leave.type='button';leave.onclick=()=>start(false).catch(showError);buttons.append(leave);panel.append(buttons);workshopSide(run);
}
async function workshopObserve(run,pending,token,app){
 workshopController=new AbortController();const parts=new Map();
 const result=await streamChat({},event=>{
  if(token!==workshopGeneration)return;
  if(event.type==='task'){workshopRun={...workshopRun,state:event.state,error:event.error};workshopPanel(workshopRun,pending);}
  else if(event.type==='delta'){const key=(event.output_index||0)+':'+(event.content_index||0);parts.set(key,(parts.get(key)||'')+(event.delta||''));renderMarkdown(pending.querySelector('.body'),[...parts.values()].join('\n'));scrollChat();}
 },'/api/runs/'+run.id+'/events?app='+encodeURIComponent(app),workshopController.signal);
 if(token!==workshopGeneration)return;
 workshopForget(app,run);sid=result.session_id;pending.replaceWith(message(result.message));
 const saved=await api('/api/runs/'+run.id+'?app='+encodeURIComponent(app));workshopRun=saved;workshopSide(saved);routingShow(result.message?.routing,'saved');await sessions();
}
async function sendManaged(text){
 const app=current.id;workshopDetach();const token=workshopGeneration;loading(true);$('welcome')?.remove();
 const chosen=[...chatFiles];message({role:'user',content:text,attachments:chosen});setInput('');
 const pending=message({role:'assistant',content:''});const submission=crypto.randomUUID();
 let run={id:null,session_id:sid,submission_id:submission,state:'queued',model:current.runtime.model};
 workshopRemember(app,run);workshopRun=run;workshopPanel(run,pending);
 try{
  const attachments=await chatFilePayload(chosen);
  run=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:app,session_id:sid,message:text,attachments,submission_id:submission})});
  run.submission_id=submission;workshopRemember(app,run);workshopRun=run;sid=run.session_id;clearChatFiles();workshopPanel(run,pending);
  await workshopObserve(run,pending,token,app);
 }catch(e){if(token!==workshopGeneration)return;
  try{const saved=await api('/api/runs?app='+encodeURIComponent(app)+'&submission_id='+submission);run={...saved,submission_id:submission};workshopRemember(app,run);}catch{}
  workshopRun={...run,state:['failed','cancelled','needs_reconciliation'].includes(run.state)?run.state:'reconnecting',error:e.message+' The task may still be working; reconcile saved status before resubmitting.'};workshopPanel(workshopRun,pending);showError(e);
 }finally{if(token===workshopGeneration){loading(false);if(workshopRun&&workshopRun.state!=='completed'){$('input').disabled=true;$('send').disabled=true;$('chat-attach').disabled=true;}else $('input').focus();}}
}
async function workshopRecoverMarker(app,marker){
 const run=marker.id?await api('/api/runs/'+marker.id+'?app='+encodeURIComponent(app)):await api('/api/runs?app='+encodeURIComponent(app)+'&submission_id='+encodeURIComponent(marker.submission_id));
 run.submission_id=marker.submission_id;
 if(run.state==='needs_reconciliation')await api('/api/runs/'+run.id+'/reconcile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:app})});
 const saved=await api('/api/sessions?app='+encodeURIComponent(app)+'&id='+encodeURIComponent(run.session_id));
 if(current?.id!==app||wizard)return;
 workshopDetach();sid=saved.id;clearChatFiles();$('messages').replaceChildren();saved.messages.forEach(message);routingRestore(saved.messages);await sessions();
 await workshopRestore(saved);
}
async function workshopRecover(){
 if(current?.runtime?.api!=='agents')return;
 const markers=workshopMarkers(current.id);if(!markers.length)return;
 try{await workshopRecoverMarker(current.id,markers.at(-1));}
 catch(e){showError(new Error('A previous task has no confirmed outcome. Check saved conversations or OpenAI Agents logs before resubmitting. '+e.message));}
}
async function workshopRestore(saved){
 const run=saved.run;if(!run)return;workshopRun=run;workshopSide(run);
 if(run.state==='completed'||saved.archived)return;
 const token=workshopGeneration,app=current.id;loading(activeRun(run));const pending=message({role:'assistant',content:''});workshopPanel(run,pending);
 if(!activeRun(run)){loading(false);$('input').disabled=true;$('send').disabled=true;return;}
 try{await workshopObserve(run,pending,token,app);}catch(e){if(token===workshopGeneration){workshopRun={...run,state:'reconnecting',error:'Connection interrupted; provider work may continue.'};workshopPanel(workshopRun,pending);showError(e);}}
 finally{if(token===workshopGeneration){loading(false);if(workshopRun?.state!=='completed'){$('input').disabled=true;$('send').disabled=true;}}}
}
async function workshopCleanup(){
 if(!current||!sid?.startsWith('managed-'))return showError(new Error('Open a managed conversation first.'));
 if(!confirm('Delete this conversation’s provider session, uploaded runtime files and generated artifacts? The local text transcript remains archived. Shared knowledge is retained.'))return;
 try{const result=await api('/api/sessions/cleanup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:current.id,session_id:sid,confirm:true})});showError(new Error(result.cleanup_pending?'Local files archived; provider cleanup is pending and will be retried while the server runs.':'Runtime files deleted; this conversation is archived.'));await sessions();}
 catch(e){showError(e);}
}
