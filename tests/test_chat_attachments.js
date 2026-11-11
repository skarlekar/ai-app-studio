const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../gptapps/attachments.js'),'utf8');
function helpers(){const context=vm.createContext({Uint8Array,btoa,File});vm.runInContext(source,context);return context;}
test('selection validates all files atomically, supports multiple batches, and deduplicates',()=>{
 const c=helpers(),a=new File(['alpha'],'notes.txt',{lastModified:1}),b=new File(['beta'],'brief.md');
 assert.equal(c.selectChatFiles([a],[a,b]).length,2);
 assert.throws(()=>c.selectChatFiles([a],[b,new File(['x'],'run.exe')]),/Unsupported/);
 assert.throws(()=>c.selectChatFiles([],[{name:'big.pdf',size:11*1024*1024}]),/10 MiB/);
 assert.throws(()=>c.selectChatFiles([],[1,2,3].map(i=>({name:i+'.pdf',size:8*1024*1024}))),/20 MiB/);
 assert.throws(()=>c.selectChatFiles([],[1,2,3,4,5,6].map(i=>({name:i+'.txt',size:1}))),/5 files/);
});
test('encodes actual bytes of multiple selected files for the server',async()=>{
 const c=helpers(),files=[new File(['AMBER-42'],'notes.txt'),new File(['other'],'brief.md')];
 const payload=await c.chatFilePayload(files);
 assert.equal(payload[0].name,'notes.txt');assert.equal(Buffer.from(payload[0].data,'base64').toString(),'AMBER-42');
 assert.equal(payload[1].name,'brief.md');
});
test('a read failure rejects the entire submission instead of silently skipping a file',async()=>{
 const c=helpers();await assert.rejects(c.chatFilePayload([{name:'bad.txt',arrayBuffer:async()=>{throw new Error('File unavailable');}}]),/File unavailable/);
});
function ui(){
 const listeners={},nodes={};
 function node(){return {children:[],hidden:false,classList:{add(){},remove(){}},setAttribute(){},append(...items){this.children.push(...items);},replaceChildren(){this.children=[];}};}
 ['chat-file-list','chat-attachment-help','input','chat-attach','chat-files','error','form'].forEach(id=>nodes[id]=node());
 const c=vm.createContext({Uint8Array,btoa,File,busy:false,knowledgeBusy:false,knowledgeMode:false,wizard:null,current:{id:'app'},
  $:id=>nodes[id],element:()=>node(),showError:e=>{nodes.error.textContent=e.message;},
  document:{addEventListener:(type,callback)=>{listeners[type]=callback;},querySelectorAll:()=>[]}});
 vm.runInContext(source,c);c.initChatAttachments();return {c,nodes,listeners};
}
test('drop attaches files without navigating, permits removal, and ignores text drags',()=>{
 const {c,nodes,listeners}=ui();let prevented=0;
 const file=new File(['useful'],'notes.txt');
 listeners.drop({preventDefault(){prevented++;},dataTransfer:{types:['Files'],files:[file]}});
 assert.equal(prevented,1);assert.equal(nodes['chat-file-list'].children.length,1);assert.equal(nodes.input.required,false);
 const remove=nodes['chat-file-list'].children[0].children[2];remove.onclick();
 assert.equal(nodes['chat-file-list'].children.length,0);assert.equal(nodes.input.required,true);
 listeners.drop({preventDefault(){prevented++;},dataTransfer:{types:['text/plain'],files:[]}});assert.equal(prevented,1);
});
test('busy or knowledge panel blocks dropped files, while preserving current selection',()=>{
 const {c,nodes,listeners}=ui();c.addChatFiles([new File(['x'],'notes.txt')]);c.busy=true;
 listeners.drop({preventDefault(){},dataTransfer:{types:['Files'],files:[new File(['y'],'other.md')]}});
 assert.equal(nodes['chat-file-list'].children.length,1);assert.match(nodes.error.textContent,/Wait/);
 c.busy=false;c.clearChatFiles();assert.equal(nodes['chat-file-list'].children.length,0);
});
test('knowledge setup uses its dedicated uploader rather than transient chat attachments',()=>{
 const {c,nodes,listeners}=ui();c.wizard={step:0};c.steps=[{key:'knowledge_files'}];
 listeners.drop({preventDefault(){},dataTransfer:{types:['Files'],files:[new File(['x'],'reference.pdf')]}});
 assert.equal(nodes['chat-file-list'].children.length,0);assert.match(nodes.error.textContent,/knowledge|Wait/);
});
