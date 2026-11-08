// Optional: node --test tests/test_chat_stream.js (no npm dependencies).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../gptapps/chat.js'),'utf8');
const isolated=source.slice(source.indexOf('async function streamChat('),source.indexOf('async function sendChat('));
const wire=event=>'data: '+JSON.stringify(event)+'\r\n\r\n';

function client(response){
 const context=vm.createContext({TextDecoder,Uint8Array,fetch:async()=>response});
 vm.runInContext(isolated,context);return context.streamChat;
}
test('decodes arbitrary UTF-8 and SSE boundaries before returning completion',async()=>{
 const chunks=new TextEncoder().encode(wire({type:'delta',delta:'¡Buenos días!\n'})+wire({type:'done',session_id:'saved',message:{content:'¡Buenos días!\n'}}));
 let index=0;
 const response=new Response(new ReadableStream({pull(controller){if(index<chunks.length)controller.enqueue(chunks.slice(index,index+=1));else controller.close();}}),{headers:{'Content-Type':'text/event-stream'}});
 const events=[];
 const result=await client(response)({},event=>events.push(event));
 assert.equal(events[0].delta,'¡Buenos días!\n');assert.equal(result.session_id,'saved');
});
test('surfaces an error after partial text and cancels the response body',async()=>{
 let cancelled=false;
 const response=new Response(new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode(wire({type:'delta',delta:'partial'})+wire({type:'error',error:'incomplete; no turn saved'})));},cancel(){cancelled=true;}}),{headers:{'Content-Type':'text/event-stream'}});
 const events=[];
 await assert.rejects(client(response)({},event=>events.push(event)),/incomplete/);
 assert.equal(events.length,1);assert.equal(cancelled,true);
});
test('never treats an early EOF as a completed answer',async()=>{
 const response=new Response(wire({type:'delta',delta:'partial'}),{headers:{'Content-Type':'text/event-stream'}});
 await assert.rejects(client(response)({},()=>{}),/before completion was confirmed/);
});
test('preserves errors returned before streaming starts',async()=>{
 const response=new Response(JSON.stringify({error:'Unresolved configuration'}),{status:400,headers:{'Content-Type':'application/json'}});
 await assert.rejects(client(response)({},()=>{}),/Unresolved configuration/);
});
test('rejects an old server JSON response instead of pretending to stream it',async()=>{
 const response=new Response('{}',{headers:{'Content-Type':'application/json'}});
 await assert.rejects(client(response)({},()=>{}),/Restart the server/);
});
