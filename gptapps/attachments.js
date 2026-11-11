/* Shared composer intake for Studio and every standalone export. Files stay local until Send. */
let chatFiles=[];
let chatFileLimits={max_files:5,max_file_bytes:10*1024*1024,max_total_bytes:20*1024*1024,
 extensions:['.pdf','.txt','.md','.json','.csv','.tsv','.xml','.html','.doc','.docx','.rtf','.odt','.ppt','.pptx','.xls','.xlsx','.c','.cpp','.cs','.css','.go','.java','.js','.php','.py','.rb','.sh','.tex','.ts','.yaml','.yml','.png','.jpg','.jpeg','.webp']};
function selectChatFiles(existing,incoming,limits=chatFileLimits){
 const result=[...existing];
 for(const file of incoming){
  const extension=file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if(!limits.extensions.includes(extension))throw new Error('Unsupported file type: '+file.name);
  if(!file.size||file.size>limits.max_file_bytes)throw new Error('Files must be nonempty and at most 10 MiB each.');
  if(!result.some(item=>item.name===file.name&&item.size===file.size&&item.lastModified===file.lastModified))result.push(file);
 }
 if(result.length>limits.max_files)throw new Error('Attach up to 5 files per message.');
 if(result.reduce((sum,file)=>sum+file.size,0)>limits.max_total_bytes)throw new Error('Attachments must total at most 20 MiB.');
 return result;
}
async function chatFilePayload(files){
 const payload=[];
 for(const file of files){
  const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
  for(let offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
  payload.push({name:file.name,data:btoa(binary)});
 }
 return payload;
}
function attachmentsBlocked(){return busy||knowledgeBusy||knowledgeMode||(wizard&&steps[wizard.step]?.key==='knowledge_files')||(!wizard&&!current);}
function renderChatFiles(){
 const list=$('chat-file-list');list.replaceChildren();
 chatFiles.forEach((file,index)=>{
  const item=element('li',undefined,'chat-file-chip');
  item.append(element('span',file.name,'chat-file-name'),element('span',(file.size/1024).toFixed(1)+' KiB','chat-file-size'));
  const remove=element('button','×','chat-file-remove');remove.type='button';remove.setAttribute('aria-label','Remove '+file.name);
  remove.disabled=attachmentsBlocked();remove.onclick=()=>{chatFiles=chatFiles.filter((_,i)=>i!==index);renderChatFiles();};
  item.append(remove);list.append(item);
 });
 $('chat-attachment-help').hidden=!chatFiles.length;
 $('input').required=!chatFiles.length;
 updateAttachmentControls();
}
function updateAttachmentControls(){
 const blocked=attachmentsBlocked();$('chat-attach').disabled=blocked;$('chat-files').disabled=blocked;
 document.querySelectorAll('.chat-file-remove').forEach(button=>button.disabled=blocked);
}
function clearChatFiles(){chatFiles=[];renderChatFiles();}
function addChatFiles(files){
 if(attachmentsBlocked())return showError(new Error('Wait for the current task to finish or return to chat. For permanent knowledge, use the knowledge file picker and index controls.'));
 try{chatFiles=selectChatFiles(chatFiles,Array.from(files));$('error').textContent='';renderChatFiles();}
 catch(error){showError(error);}
}
function initChatAttachments(){
 $('chat-attach').onclick=()=>$('chat-files').click();
 $('chat-files').onchange=()=>{addChatFiles($('chat-files').files);$('chat-files').value='';};
 let dragDepth=0;
 const hasFiles=event=>Array.from(event.dataTransfer?.types||[]).includes('Files');
 document.addEventListener('dragenter',event=>{if(!hasFiles(event))return;event.preventDefault();dragDepth++;if(!attachmentsBlocked())$('form').classList.add('file-drop-active');});
 document.addEventListener('dragover',event=>{if(!hasFiles(event))return;event.preventDefault();event.dataTransfer.dropEffect=attachmentsBlocked()?'none':'copy';});
 document.addEventListener('dragleave',event=>{if(!hasFiles(event))return;dragDepth=Math.max(0,dragDepth-1);if(!dragDepth)$('form').classList.remove('file-drop-active');});
 document.addEventListener('drop',event=>{if(!hasFiles(event))return;event.preventDefault();dragDepth=0;$('form').classList.remove('file-drop-active');addChatFiles(event.dataTransfer.files);});
 renderChatFiles();
}
