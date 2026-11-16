import base64,copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from gptapps.runtime import Runtime
from gptapps.spec import from_chat_input,validate
from gptapps.setup import SetupInterpreter
from gptapps.extensions import Registry,scoring_example
from test_framework import app,response,FakeClient
from test_routing_explanation import Explainer as FakeExplanation


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
   runtime=Runtime(folder,client,decisions_client=decider,explanation_client=FakeExplanation());config=self.config()
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
   result=Runtime(folder,client,registry,decisions_client=decider,explanation_client=FakeExplanation()).chat(config,'Score')
   self.assertEqual([p['model'] for p in client.requests],['test-economy','test-economy']);self.assertEqual(len(decider.requests),1)
   self.assertEqual(result['message']['routing']['answer_usage']['total_tokens'],20)
 def test_stream_disconnect_checkpoint_after_router_prevents_answer_and_save(self):
  client=FakeClient(response());decider=Decisions(decision())
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,client,decisions_client=decider,explanation_client=FakeExplanation());config=self.config()
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
   runtime=Runtime(folder,FakeClient(response()),decisions_client=Decisions(decision()),explanation_client=FakeExplanation())
   first=runtime.chat(config,'Hi');config['runtime']['routing']['version']='changed'
   with self.assertRaisesRegex(ValueError,'configuration changed'):runtime.chat(config,'Again',first['session_id'])

class RoutingExplanationIntegrationTests(unittest.TestCase):
 def test_saved_prompt_specific_assessment_is_separate_from_policy_and_answer_input(self):
  class Explainer:
   def __init__(self):self.requests=[]
   def create(self,payload,timeout=3):
    self.requests.append(copy.deepcopy(payload))
    return {'status':'completed','model':'gpt-6-luna','usage':{'input_tokens':75,'output_tokens':30,'total_tokens':105},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'request_summary':'Basic Spanish greetings for a beginner','effort_reason':'Common greetings and translations need a short direct answer with little synthesis.'})}]}]}
  config=app();config['runtime']['model']=None;config['runtime']['routing']=policy()
  class StreamingAnswer(FakeClient):
   def stream(self,payload):yield {'type':'response.completed','response':self.create(payload)}
  client=StreamingAnswer(response('Hola'));explanation=Explainer();events=[]
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,client,decisions_client=Decisions(decision()),explanation_client=FakeExplanation());runtime.explanation_client=explanation
   result=runtime.chat(config,'Teach me basic greetings in Spanish.',emit=events.append)
   record=result['message']['routing']
   self.assertIn('request_assessment',record)
   self.assertIn('Spanish greetings',record['request_assessment'])
   self.assertIn('little synthesis',record['request_assessment'])
   self.assertIn('lowest',record['selection_reason'])
   self.assertIn('test-economy',record['selection_reason'])
   self.assertEqual(record['explanation_usage']['total_tokens'],105)
   self.assertEqual(record['requested_model'],'test-economy')
   self.assertEqual(record['explanation_status'],'generated')
   self.assertEqual(len(explanation.requests),1)
   self.assertEqual(len(client.requests),1)
   self.assertEqual(client.requests[0]['input'][-1]['content'],'Teach me basic greetings in Spanish.')
   self.assertNotIn('request_assessment',json.dumps(client.requests))
   self.assertEqual(runtime.get_session(config['id'],result['session_id'])['messages'][-1]['routing'],record)
   self.assertTrue(any(event.get('routing',{}).get('request_assessment') for event in events))
 def test_explanation_failure_does_not_retry_or_change_the_answer_model(self):
  from gptapps.explanations import ExplanationFailure
  config=app();config['runtime']['model']=None;config['runtime']['routing']=policy()
  explanation=FakeExplanation(error=ExplanationFailure('timeout'));client=FakeClient(response('Hola'))
  with tempfile.TemporaryDirectory() as folder:
   result=Runtime(folder,client,decisions_client=Decisions(decision()),explanation_client=explanation).chat(config,'Teach Spanish greetings')
   record=result['message']['routing'];self.assertEqual(record['explanation_status'],'unavailable')
   self.assertNotIn('request_assessment',record);self.assertEqual(len(explanation.calls),1)
   self.assertEqual(len(client.requests),1);self.assertEqual(client.requests[0]['model'],'test-economy')
 def test_disconnect_after_assessment_prevents_answer_and_save(self):
  config=app();config['runtime']['model']=None;config['runtime']['routing']=policy()
  explanation=FakeExplanation();client=FakeClient(response())
  with tempfile.TemporaryDirectory() as folder:
   runtime=Runtime(folder,client,decisions_client=Decisions(decision()),explanation_client=explanation)
   def emit(event):
    if event.get('routing',{}).get('request_assessment'):raise BrokenPipeError('gone')
   with self.assertRaises(BrokenPipeError):runtime.chat(config,'Teach Spanish greetings',emit=emit)
   self.assertEqual(len(explanation.calls),1);self.assertEqual(client.requests,[])
   self.assertEqual(runtime.list_sessions(config['id']),[])
 def test_fixed_chat_skips_explanation(self):
  explanation=FakeExplanation()
  with tempfile.TemporaryDirectory() as folder:
   Runtime(folder,FakeClient(response()),explanation_client=explanation).chat(app(),'Teach Spanish greetings')
   self.assertEqual(explanation.calls,[])
