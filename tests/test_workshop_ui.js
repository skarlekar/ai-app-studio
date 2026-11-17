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
