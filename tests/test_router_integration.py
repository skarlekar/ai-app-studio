import base64,copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from gptapps.runtime import Runtime
from gptapps.spec import from_chat_input,validate
from gptapps.setup import SetupInterpreter
from gptapps.extensions import Registry,scoring_example
from test_framework import app,response,FakeClient


def policy():
 caps=['text','documents','images','web_search','image_generation','code_interpreter','file_search','function_calling','structured_output']
 return {'mode':'cost_first','version':'test-v1','router_model':'gpt-6-luna','fallback_model':'test-balanced','candidates':[
  {'model':'test-'+tier,'tier':tier,'cost_rank':i,'context_window':200000,'max_output_tokens':32768,'capabilities':caps}
  for i,tier in enumerate(['economy','balanced','advanced'])]}

def decision(effort='economy'):
 values=['economy','balanced','advanced','uncertain']
 return {'model':'gpt-6-luna','answers':[
  {'type':'choice','name':'effort','choice':effort,'probabilities':[{'value':v,'probability':.97 if v==effort else .01} for v in values],'confidence':.96},
  {'type':'choice','name':'task','choice':'summary','probabilities':[{'value':v,'probability':.94 if v=='summary' else .01} for v in ['extraction','summary','transformation','explanation','reasoning','coding','other']],'confidence':.9}],
  'usage':{'input_tokens':100,'output_tokens':0}}

class Decisions:
 def __init__(self,*items):self.items=iter(items);self.requests=[]
 def create(self,payload,timeout=2):self.requests.append(copy.deepcopy(payload));return next(self.items)

class RouterRuntimeTests(unittest.TestCase):
 def config(self):
  item=app();item['runtime']['model']=None;item['runtime']['routing']=policy();return item
 def test_switches_models_across_turns_and_preserves_original_files_and_history(self):
  decider=Decisions(decision(),decision('advanced'));client=FakeClient(response('First',model='test-economy-snapshot'),response('Second',model='test-advanced'))
  file={'name':'notes.txt','data':base64.b64encode(b'AMBER-42').decode()}
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,client,decisions_client=decider);config=self.config()
   first=runtime.chat(config,'Summarize',attachments=[file]);second=runtime.chat(config,'Now reason deeply',first['session_id'])
   self.assertEqual([r['model'] for r in client.requests],['test-economy','test-advanced'])
   self.assertEqual(client.requests[0]['input'][0]['content'][1]['file_data'].split(',')[1],file['data'])
   self.assertEqual(client.requests[1]['input'][0],client.requests[0]['input'][0])
   self.assertNotIn('routing',client.requests[1]['input'][1])
   self.assertEqual(first['message']['routing']['reported_model'],'test-economy-snapshot')
   self.assertEqual(second['message']['routing']['requested_model'],'test-advanced')
   self.assertEqual(runtime.get_session(config['id'],first['session_id'])['messages'][-1]['routing'],second['message']['routing'])
 def test_pins_model_across_function_rounds_and_records_aggregate_usage(self):
  registry=Registry();scoring_example(registry);config=self.config();config['bindings']['function_tools']=['cosine_score']
  call={'type':'function_call','name':'cosine_score','call_id':'c','arguments':'{"left":[1],"right":[1]}'}
  client=FakeClient(response(output=[call]),response('1'));decider=Decisions(decision())
  with tempfile.TemporaryDirectory() as folder:
   result=Runtime(folder,client,registry,decisions_client=decider).chat(config,'Score')
   self.assertEqual([p['model'] for p in client.requests],['test-economy','test-economy']);self.assertEqual(len(decider.requests),1)
   self.assertEqual(result['message']['routing']['answer_usage']['total_tokens'],20)
 def test_stream_disconnect_checkpoint_after_router_prevents_answer_and_save(self):
  client=FakeClient(response());decider=Decisions(decision())
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,client,decisions_client=decider);config=self.config()
   def emit(event):
    if event['type']=='routing':raise BrokenPipeError('gone')
   with self.assertRaises(BrokenPipeError):runtime.chat(config,'Hi',emit=emit)
   self.assertEqual(client.requests,[]);self.assertEqual(runtime.list_sessions(config['id']),[])
 def test_fixed_mode_reports_requested_model_and_preserves_fingerprint_guard(self):
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,FakeClient(response('Hi'),response('Next')));config=app()
   first=runtime.chat(config,'Hi');self.assertEqual(first['message']['routing']['mode'],'fixed')
   self.assertNotIn('reported_model',first['message']['routing'])
   config['runtime']['model']='different'
   with self.assertRaisesRegex(ValueError,'configuration changed'):runtime.chat(config,'Again',first['session_id'])
 def test_auto_configuration_snapshot_and_setup_need_no_setup_api_call(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'policy.json';path.write_text(json.dumps(policy()))
   with patch.dict(os.environ,{'OPENAI_ROUTING_POLICY_FILE':str(path)}):
    draft=from_chat_input({'name':'Auto app','instructions':'Help','model':'auto'})
    self.assertIsNone(draft['runtime']['model']);self.assertEqual(draft['runtime']['routing']['fallback_model'],'test-balanced');validate(draft)
    result=SetupInterpreter(FakeClient()).interpret('model','auto');self.assertEqual(result['value'],'auto')
   with patch.dict(os.environ,{'OPENAI_ROUTING_POLICY_FILE':''}):
    with self.assertRaisesRegex(ValueError,'policy|routing|ROUTING'):from_chat_input({'name':'Auto','instructions':'Help','model':'auto'})
 def test_policy_change_still_rejects_old_conversation(self):
  config=self.config()
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,FakeClient(response()),decisions_client=Decisions(decision()))
   first=runtime.chat(config,'Hi');config['runtime']['routing']['version']='changed'
   with self.assertRaisesRegex(ValueError,'configuration changed'):runtime.chat(config,'Again',first['session_id'])
