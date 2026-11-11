const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../gptapps/knowledge.js'),'utf8');

test('clicking upload again while the same collection indexes never creates another provider mutation',async()=>{
 const file={name:'guide.txt',size:5},calls=[];
 const job={id:'saved-upload',status:'indexing',files:[{...file,status:'uploaded'}]};
 const nodes={'knowledge-files':{files:[file]},'knowledge-error':{},'knowledge-status':{}};
 const context=vm.createContext({busy:false,wizard:null,current:{id:'app'},clearTimeout:()=>{},
  $:id=>nodes[id],api:async path=>{calls.push(path);return {...job,status:path.endsWith('/index')?'indexing':'uploading'};},
  fetch:async path=>{calls.push(path);return {ok:true,json:async()=>job};}});
 vm.runInContext(source,context);
 vm.runInContext('knowledgeMode=true;knowledgeJob='+JSON.stringify(job)+';renderKnowledge=()=>{};updateChrome=()=>{};loadKnowledgeCollections=async()=>{};pollKnowledge=async()=>{};',context);
 await context.uploadKnowledge();
 assert.deepEqual(calls,[]);
});

test('using ready knowledge clears transient files before advancing to Actions',async()=>{
 let clears=0;
 const wizard={step:0,draft:{},history:[]};
 const context=vm.createContext({busy:false,knowledgeBusy:false,wizard,current:null,
  steps:[{key:'knowledge_files'},{key:'actions',question:'Actions?'}],
  clearChatFiles:()=>{clears++;},setInput:()=>{},setupMessage:()=>{},updateChrome:()=>{},
  $:()=>({focus(){}})});
 vm.runInContext(source,context);
 vm.runInContext('knowledgeJob={id:"ready-job",status:"ready",files:[{name:"reference.pdf"}]};',context);
 await context.useKnowledge();
 assert.equal(wizard.step,1);assert.equal(clears,1);assert.equal(wizard.draft.knowledge_files[0],'reference.pdf');
});
