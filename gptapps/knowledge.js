// Builder-only file upload UI. The browser never receives the OpenAI API key.
let knowledgeMode=false,knowledgeBusy=false,knowledgeJob=null,knowledgeJobs=[],knowledgeOwner=null,knowledgeTimer=0,knowledgeLimits={};
function knowledgeContext(){return wizard||((knowledgeMode&&current)?current.id:null);}
function stopKnowledgePolling(){if(knowledgeTimer)clearTimeout(knowledgeTimer);knowledgeTimer=0;}
function resetKnowledge(){stopKnowledgePolling();knowledgeMode=false;knowledgeJob=null;knowledgeOwner=null;$('knowledge-files').value='';}
function sameKnowledgeFiles(files,job){return !!job&&files.length===job.files.length&&job.files.every(item=>files.some(file=>file.name===item.name&&file.size===item.size));}
function knowledgeError(error){$('knowledge-error').textContent=error.message||String(error);}
async function knowledgeJSON(path,body){return api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}

function renderKnowledge(){
 const files=Array.from($('knowledge-files').files),job=knowledgeJob;
 const entries=job?job.files:files.map(file=>({name:file.name,size:file.size,status:'selected'}));
 $('knowledge-file-list').replaceChildren();
 const labels={selected:'Selected',queued:'Waiting',uploading:'Uploading…',uploaded:'Uploaded',failed:'Failed'};
 for(const file of entries){const row=element('li'),size=file.size<1024?file.size+' B':(file.size/1024).toFixed(1)+' KiB';row.append(element('span',file.name),element('span',size+' · '+(labels[file.status]||file.status),'knowledge-file-detail'));$('knowledge-file-list').append(row);}
 let text='Choose files to begin.';
 if(files.length&&!job)text=files.length+' file'+(files.length===1?'':'s')+' selected.';
 if(job){
  const option=Array.from($('knowledge-recent').options).find(option=>option.value===job.id);
  if(option)option.textContent=job.files[0].name+(job.files.length>1?' + '+(job.files.length-1)+' more':'')+' · '+job.status;
  knowledgeJobs=knowledgeJobs.map(item=>item.id===job.id?job:item);
  const uploaded=job.files.filter(file=>file.status==='uploaded').length,counts=job.file_counts||{};
  text=job.status==='ready'?'All '+job.files.length+' files are indexed and ready.':
       job.status==='indexing'?'Indexing '+(counts.completed||0)+' of '+job.files.length+' files…':
       job.status==='failed'?'This collection is not ready to use.':
       'Uploaded '+uploaded+' of '+job.files.length+' files.'+(!knowledgeBusy?' Reselect the same files to resume.':'');
  if(job.status==='failed')$('knowledge-error').textContent=job.error||'Knowledge indexing failed.';
  $('knowledge-progress').hidden=false;
  $('knowledge-progress').value=job.status==='ready'?100:job.status==='indexing'?50+50*(counts.completed||0)/job.files.length:50*uploaded/job.files.length;
 }else $('knowledge-progress').hidden=true;
 $('knowledge-status').textContent=text;
 const ready=job?.status==='ready',canIndex=job?.status==='uploading'&&job.files.every(file=>file.status==='uploaded');
 $('knowledge-upload').disabled=knowledgeBusy||busy||(!files.length&&!canIndex)||((ready||job?.status==='indexing')&&sameKnowledgeFiles(files,job));
 $('knowledge-upload').textContent=job?.status==='failed'?'Upload new collection':canIndex?'Index uploaded files':'Upload and index';
 $('knowledge-use').disabled=knowledgeBusy||busy||!ready;
 $('knowledge-use').textContent=wizard?'Use these files':'Use files for this app';
 $('knowledge-check').hidden=!job||job.status!=='indexing';
 $('knowledge-check').disabled=knowledgeBusy||busy;
 $('knowledge-files').disabled=knowledgeBusy||busy;
 $('knowledge-recent').disabled=knowledgeBusy||busy;
 $('knowledge-close').disabled=knowledgeBusy||busy;
}

async function loadKnowledgeCollections(owner){
 const jobs=await api('/api/knowledge');
 if(knowledgeContext()!==owner)return;
 knowledgeJobs=jobs;$('knowledge-recent').replaceChildren(element('option','Choose a collection…'));
 for(const job of jobs){const option=element('option',job.files[0].name+(job.files.length>1?' + '+(job.files.length-1)+' more':'')+' · '+job.status);option.value=job.id;$('knowledge-recent').append(option);}
 $('knowledge-recent-row').hidden=!jobs.length;
 if(!knowledgeJob&&wizard?.draft.knowledge_upload_id)knowledgeJob=jobs.find(job=>job.id===wizard.draft.knowledge_upload_id)||null;
 $('knowledge-recent').value=knowledgeJob?.id||'';renderKnowledge();
}

function updateKnowledgePanel(){
 const visible=builderEnabled&&((wizard&&steps[wizard.step]?.key==='knowledge_files')||(knowledgeMode&&!wizard));
 $('knowledge-panel').hidden=!visible;
 $('knowledge-controls').hidden=!visible;
 $('knowledge-panel').classList.toggle('knowledge-manage',knowledgeMode&&!wizard);
 $('knowledge-close').hidden=!!wizard;
 $('messages').hidden=visible;
 document.querySelector('footer').hidden=knowledgeMode&&!wizard;
 $('form').hidden=knowledgeMode&&!wizard;
 $('note').hidden=knowledgeMode&&!wizard;
 if(!visible){stopKnowledgePolling();knowledgeOwner=null;return;}
 $('knowledge-title').textContent=wizard?'Add your knowledge files':'Knowledge files · '+current.name;
 $('knowledge-description').textContent=wizard?'Choose all the documents your GPT needs, then upload and index them. You can also type none in the chat.':'Choose a complete collection for this app. Using it replaces the attached knowledge; earlier OpenAI files and stores are retained.';
 $('knowledge-files').accept=(knowledgeLimits.extensions||[]).join(',');
 const owner=knowledgeContext();
 if(owner!==knowledgeOwner){knowledgeOwner=owner;knowledgeJob=null;$('knowledge-files').value='';$('knowledge-error').textContent='';$('knowledge-guidance').hidden=true;loadKnowledgeCollections(owner).catch(error=>{if(knowledgeContext()===owner)knowledgeError(error);});}
 renderKnowledge();
}

async function pollKnowledge(owner,attempt=0){
 stopKnowledgePolling();const id=knowledgeJob?.id;if(!id)return;
 try{
  const job=await api('/api/knowledge/status?id='+encodeURIComponent(id));
  if(knowledgeContext()!==owner||knowledgeJob?.id!==id)return;
  knowledgeJob=job;renderKnowledge();
  if(job.status==='indexing'&&attempt<300)knowledgeTimer=setTimeout(()=>pollKnowledge(owner,attempt+1),2000);
 }catch(error){if(knowledgeContext()===owner&&knowledgeJob?.id===id)knowledgeError(error);}
}

async function uploadKnowledge(){
 if(knowledgeBusy||busy)return;
 const owner=knowledgeContext(),files=Array.from($('knowledge-files').files);
 if((knowledgeJob?.status==='indexing'||knowledgeJob?.status==='ready')&&sameKnowledgeFiles(files,knowledgeJob))return;
 const maxFile=knowledgeLimits.max_file_bytes||25*1024**2,maxTotal=knowledgeLimits.max_total_bytes||100*1024**2;
 try{
  if(files.length>(knowledgeLimits.max_files||100)||files.some(file=>!file.size||file.size>maxFile)||files.reduce((sum,file)=>sum+file.size,0)>maxTotal)throw new Error('Choose up to 100 nonempty files, at most 25 MiB each and 100 MiB total.');
  const resumable=knowledgeJob?.status==='uploading'&&(sameKnowledgeFiles(files,knowledgeJob)||knowledgeJob.files.every(file=>file.status==='uploaded'));
  if(!files.length&&!resumable)throw new Error('Choose one or more files first.');
  knowledgeBusy=true;stopKnowledgePolling();$('knowledge-error').textContent='';updateChrome();
  if(!resumable)knowledgeJob=await knowledgeJSON('/api/knowledge',{files:files.map(file=>({name:file.name,size:file.size}))});
  renderKnowledge();
  for(let index=0;index<knowledgeJob.files.length;index++){
   const item=knowledgeJob.files[index];if(item.status==='uploaded'&&!files.length)continue;
   const file=files.find(file=>file.name===item.name&&file.size===item.size);
   if(!file)throw new Error('Reselect all the original files to resume this collection.');
   $('knowledge-status').textContent='Uploading '+item.name+' ('+(index+1)+' of '+knowledgeJob.files.length+')…';
   const response=await fetch('/api/knowledge/file?id='+encodeURIComponent(knowledgeJob.id)+'&index='+index,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
   const data=await response.json();if(!response.ok)throw new Error(data.error||'Knowledge upload failed');knowledgeJob=data;renderKnowledge();
  }
  knowledgeJob=await knowledgeJSON('/api/knowledge/index',{upload_id:knowledgeJob.id});
  await loadKnowledgeCollections(owner);
 }catch(error){
  if(knowledgeJob){try{knowledgeJob=await api('/api/knowledge/status?id='+encodeURIComponent(knowledgeJob.id));}catch{}}
  if(knowledgeContext()===owner)knowledgeError(error);
 }finally{knowledgeBusy=false;updateChrome();if(knowledgeContext()===owner&&knowledgeJob?.status==='indexing')pollKnowledge(owner);}
}

async function useKnowledge(){
 if(knowledgeBusy||busy||knowledgeJob?.status!=='ready')return;
 const job=knowledgeJob;
 if(wizard&&steps[wizard.step]?.key==='knowledge_files'){
  clearChatFiles();setInput('');
  wizard.draft.knowledge_upload_id=job.id;wizard.draft.knowledge_files=job.files.map(file=>file.name);wizard.history=[];
  setupMessage('All '+job.files.length+' knowledge files are indexed and will be attached to your application.');
  wizard.step++;updateChrome();setupMessage(steps[wizard.step].question);$('input').focus();return;
 }
 if(!knowledgeMode||!current)return;
 knowledgeBusy=true;updateChrome();$('knowledge-error').textContent='';
 try{
  await knowledgeJSON('/api/knowledge/bind',{app_id:current.id,upload_id:job.id});
  apps=await api('/api/apps');current=apps.find(app=>app.id===current.id);
  knowledgeBusy=false;await start();
  $('welcome')?.append(element('p',job.files.length+' knowledge files are attached and ready. Start a new conversation to use them.','knowledge-success'));
 }catch(error){knowledgeError(error);}
 finally{knowledgeBusy=false;updateChrome();}
}

function initKnowledge(){
 $('knowledge-files').onchange=()=>{const files=Array.from($('knowledge-files').files);if(!sameKnowledgeFiles(files,knowledgeJob)){stopKnowledgePolling();knowledgeJob=null;$('knowledge-recent').value='';}$('knowledge-error').textContent='';renderKnowledge();};
 $('knowledge-upload').onclick=uploadKnowledge;
 $('knowledge-use').onclick=useKnowledge;
 $('knowledge-close').onclick=()=>{if(!knowledgeBusy&&!busy){resetKnowledge();updateChrome();}};
 $('knowledge-check').onclick=()=>{if(!knowledgeBusy&&!busy)pollKnowledge(knowledgeContext());};
 $('knowledge-recent').onchange=()=>{stopKnowledgePolling();knowledgeJob=knowledgeJobs.find(job=>job.id===$('knowledge-recent').value)||null;$('knowledge-files').value='';$('knowledge-error').textContent='';renderKnowledge();if(knowledgeJob?.status==='indexing')pollKnowledge(knowledgeContext());};
}
