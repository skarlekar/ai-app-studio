// Only bounded, public routing metadata is rendered; raw evidence is never copied.
function routingText(value,limit=500){return typeof value==='string'?value.slice(0,limit):'';}
function routingLabel(labels,key){return typeof key==='string'&&Object.hasOwn(labels,key)?labels[key]:'';}
function routingModel(value){return typeof value==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}$/.test(value)?value:'';}
function routingClear(){
 $('routing-status').hidden=true;$('routing-status').dataset.state='';
 for(const id of ['routing-state','routing-model','routing-route','routing-summary'])$(id).textContent='';
 $('routing-detail-list').replaceChildren();$('routing-details').open=false;$('routing-details').hidden=true;
}
function routingBegin(){routingClear();$('routing-status').hidden=false;$('routing-status').dataset.state='selecting';$('routing-state').textContent='Selecting answer model…';}
function routingFailed(){
 $('routing-status').hidden=false;$('routing-status').dataset.state='failed';
 $('routing-state').textContent='Attempt failed · not confirmed saved';
}
function routingShow(record,state='attempt'){
 routingClear();
 if(!record||typeof record!=='object'||Array.isArray(record)||!['auto','fixed'].includes(record.mode))return;
 const requested=routingModel(record.requested_model),reported=routingModel(record.reported_model),router=routingModel(record.router_model);
 $('routing-status').hidden=false;$('routing-status').dataset.state=state==='saved'?'saved':'attempt';
 $('routing-state').textContent=state==='saved'?'Saved turn':'Current attempt · not confirmed saved';
 $('routing-model').textContent=reported?'Answer model (reported): '+reported:requested?'Answer model (requested): '+requested:'Answer model: not reported';
 const routes={economy:'Economy route',balanced:'Balanced route',advanced:'Advanced route'},tasks={extraction:'Extraction',summary:'Summary',transformation:'Transformation',explanation:'Explanation',reasoning:'Reasoning',coding:'Coding',other:'Other task'};
 const labels=[record.mode==='fixed'?'Fixed model':routingLabel(routes,record.route)||'Auto — cost-first'];
 if(routingLabel(tasks,record.task))labels.push(routingLabel(tasks,record.task));if(record.fallback===true)labels.push('Fallback used');
 $('routing-route').textContent=labels.join(' · ');
 // The optional AI assessment is separate from the server-authored policy facts.
 const assessment=routingText(record.request_assessment,320);
 $('routing-summary').textContent=(assessment?'Request assessment: '+assessment+'\n\n':record.explanation_status==='unavailable'?'Request assessment unavailable; policy reason retained.\n\n':'')+routingText(record.summary,500);
 const list=$('routing-detail-list');
 const detail=(label,value)=>{if(value===undefined||value===null||value==='')return;const row=element('div',undefined,'routing-detail');row.append(element('dt',label),element('dd',String(value)));list.append(row);};
 const count=(label,value)=>{if(typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=Number.MAX_SAFE_INTEGER)detail(label,String(Math.round(value*100)/100));};
 if(reported&&requested)detail('Requested answer model',requested);
 if(router)detail('Router model',router);
 detail('Policy version',routingText(record.policy_version,100));
 const reasons={fixed_model:'Fixed model configured',classified:'Effort classification accepted; policy cost rank applied',lowest_cost_eligible:'Lowest cost rank among eligible models',single_eligible:'Only one eligible model',only_eligible_candidate:'Only one eligible model',router_timeout:'Router timeout',router_unavailable:'Router unavailable',invalid_decision:'Invalid router decision',uncertain:'Uncertain router decision',low_probability:'Decision below policy threshold',tier_unavailable:'Preferred tier unavailable',fallback:'Configured fallback'};
 if(record.selection_reason)detail('Applied rules',routingText(record.selection_reason,600));
 else if(Array.isArray(record.reason_codes)){const known=record.reason_codes.slice(0,12).map(code=>routingLabel(reasons,code)).filter(Boolean);if(known.length)detail('Applied rules',known.join('; '));}
 const explanationStates={generated:'AI-generated request assessment; policy facts shown separately',unavailable:'Unavailable; policy reason retained',not_needed:'Not requested for this selection rule'};
 const explanationState=routingLabel(explanationStates,record.explanation_status);
 if(explanationState)detail('Request explanation',explanationState);
 else if(record.mode==='auto'&&state==='saved')detail('Request explanation','Not recorded for this saved turn');
 const explanationErrors={invalid:'Invalid or incomplete explanation',refused:'Explanation declined',timeout:'Explanation timed out',unavailable:'Explanation service unavailable'};
 detail('Explanation status',routingLabel(explanationErrors,record.explanation_reason));
 const explanationModel=routingModel(record.explanation_model),explanationReported=routingModel(record.explanation_reported_model);
 if(explanationModel)detail('Explanation model (requested)',explanationModel);
 if(explanationReported)detail('Explanation model (reported)',explanationReported);
 const evidence=record.evidence&&typeof record.evidence==='object'?record.evidence:{};
 const coverage={current_chars:'Request characters considered',app_chars:'App evidence characters',history_messages:'Recent messages considered',history_omitted_messages:'Older messages omitted',history_chars:'History characters considered',files:'Attachment count',text_files:'Text attachments',image_files:'Image attachments',excerpt_chars:'Attachment excerpt characters',truncated_files:'Truncated attachment excerpts',metadata_only_files:'Metadata-only attachments'};
 for(const [key,label] of Object.entries(coverage))count(label,evidence[key]);
 const flags={app_truncated:'App evidence truncated',history_truncated:'History evidence truncated',unknown_document_context:'Binary document context usage unknown'};
 for(const [key,label] of Object.entries(flags))if(typeof evidence[key]==='boolean')detail(label,evidence[key]?'Yes':'No');
 const probabilities=record.probabilities&&typeof record.probabilities==='object'?record.probabilities:{};
 for(const [key,label] of [['effort','Effort classification probability'],['task','Task classification probability']]){
  const value=probabilities[key];if(typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1)detail(label,(value*100).toFixed(1)+'%');
 }
 count('Model selection time (ms)',record.selection_ms);count('Answer time (ms)',record.answer_ms);count('Explanation time (ms)',record.explanation_ms);
 for(const [key,label] of [['router_usage','Router'],['explanation_usage','Explanation'],['answer_usage','Answer']]){
  const usage=record[key];if(!usage||typeof usage!=='object')continue;
  count(label+' input tokens',usage.input_tokens);count(label+' output tokens',usage.output_tokens);count(label+' total tokens',usage.total_tokens);
 }
 $('routing-details').hidden=!list.children.length;
}
function routingRestore(messages){
 routingClear();if(!Array.isArray(messages))return;
 for(let i=messages.length-1;i>=0;i--){const message=messages[i];if(message?.role==='assistant'&&message.routing){routingShow(message.routing,'saved');return;}}
}
