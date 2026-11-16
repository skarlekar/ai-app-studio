"""Offline contract checks for the optional public request assessment."""
import copy,io,json,os,tempfile,unittest,urllib.error,urllib.request
from unittest.mock import patch
from gptapps.explanations import ExplanationClient,ExplanationFailure,explain_selection
from gptapps.routing import ModelRouter
from test_routing import app,policy,Recorder,decision,attachment


def response(summary='Basic Spanish greetings for a beginner',reason='Common greetings and translations need a short direct answer with little synthesis.'):
 return {'status':'completed','model':'gpt-6-luna','usage':{'input_tokens':75,'output_tokens':30,'total_tokens':105},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'request_summary':summary,'effort_reason':reason})}]}]}

class Explainer:
 def __init__(self,result=None,error=None):self.result=response() if result is None else result;self.error=error;self.calls=[]
 def create(self,payload,timeout=3):
  self.calls.append((copy.deepcopy(payload),timeout))
  if self.error:raise self.error
  return self.result

class ExplanationTests(unittest.TestCase):
 def selected(self):return {**ModelRouter(Recorder()).select(app(),'Teach Spanish greetings',[],[],[]),'mode':'auto'}
 def test_assessment_uses_bounded_untrusted_evidence_and_cannot_change_selection(self):
  record=self.selected();original=copy.deepcopy(record);client=Explainer()
  history=[{'role':'user','content':'HISTORY'*4000} for _ in range(10)]
  files=[attachment('notes.txt','PRIVATE'*1000),attachment('guide.pdf',b'%PDF-private-binary')]
  result=explain_selection(record,app(),'Teach Spanish greetings',history,files,client)
  self.assertIn('Spanish greetings',result['request_assessment']);self.assertIn('little synthesis',result['request_assessment'])
  self.assertEqual(record,original);self.assertEqual(result['requested_model'],original['requested_model'])
  payload,timeout=client.calls[0];self.assertEqual(timeout,3);self.assertEqual(len(client.calls),1)
  self.assertEqual(payload['model'],'gpt-6-luna');self.assertFalse(payload['store']);self.assertEqual(payload['reasoning'],{'effort':'none'})
  self.assertEqual(payload['max_output_tokens'],512);self.assertNotIn('tools',payload)
  self.assertEqual(payload['text']['format']['name'],'routing_explanation');self.assertTrue(payload['text']['format']['strict'])
  evidence=json.loads(payload['input'][0]['content'])['evidence'];self.assertLessEqual(len(evidence['history']),8)
  self.assertLessEqual(sum(len(item['content']) for item in evidence['history']),16000)
  self.assertLessEqual(len(evidence['files'][0]['excerpt']),4000)
  self.assertNotIn('excerpt',evidence['files'][1]);self.assertNotIn('%PDF-private-binary',json.dumps(payload))
  self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('Teach Spanish greetings',json.dumps(result))
  self.assertEqual(result['explanation_usage']['total_tokens'],105)
 def test_different_assessments_survive_without_rewriting_policy_facts(self):
  for summary,reason in [('Basic Spanish greetings','A short vocabulary answer needs little synthesis.'),('Compare transport options across several cities','Balancing cost, time and transfers needs multi-step analysis.')]:
   with self.subTest(summary=summary):
    record=self.selected();result=explain_selection(record,app(),summary,[],[],Explainer(response(summary,reason)))
    self.assertIn(summary,result['request_assessment']);self.assertIn(reason,result['request_assessment'])
    self.assertEqual(result['selection_reason'],record['selection_reason'])
 def test_failed_or_invalid_explanation_retains_policy_and_separate_usage(self):
  invalid=[{'status':'incomplete','output':[]}, {'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'private'}]}]},response('x'*121),response(reason=' '),response(reason='bad\x00value'),{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"request_summary":"ok","effort_reason":"ok","model":"attacker"}'}]}]}]
  clients=[Explainer(result=item) for item in invalid]+[Explainer(error=ExplanationFailure('timeout')),Explainer(error=ValueError('private provider error'))]
  for client in clients:
   with self.subTest(client=type(client).__name__):
    record=self.selected();result=explain_selection(record,app(),'Help',[],[],client)
    self.assertEqual(result['explanation_status'],'unavailable');self.assertNotIn('request_assessment',result)
    self.assertEqual(result['requested_model'],record['requested_model']);self.assertEqual(result['selection_reason'],record['selection_reason'])
    self.assertNotIn('private provider error',json.dumps(result));self.assertEqual(len(client.calls),1)
 def test_fixed_single_candidate_and_fallback_do_not_request_assessment(self):
  for code in ('fixed_model','single_eligible','router_unavailable','low_probability'):
   client=Explainer();record={**self.selected(),'reason_codes':[code]}
   result=explain_selection(record,app(),'Help',[],[],client)
   self.assertEqual(client.calls,[]);self.assertEqual(result['explanation_status'],'not_needed')
 def test_provider_model_and_usage_are_bounded_and_whitelisted(self):
  raw=response();raw['model']='<script>fake</script>';raw['usage'].update(total_tokens=True,secret='private usage')
  result=explain_selection(self.selected(),app(),'Help',[],[],Explainer(raw))
  self.assertNotIn('explanation_reported_model',result);self.assertNotIn('private usage',json.dumps(result))
  self.assertNotIn('total_tokens',result['explanation_usage'])

class Opener:
 def __init__(self,result=None,error=None):self.result=result if result is not None else io.BytesIO(json.dumps(response()).encode());self.error=error;self.calls=[]
 def open(self,request,timeout):
  self.calls.append((request,timeout))
  if self.error:raise self.error
  return self.result

@patch.dict(os.environ,{'OPENAI_API_KEY':'test-only-not-a-real-key'})
class ExplanationClientTests(unittest.TestCase):
 def test_fixed_responses_endpoint_timeout_and_no_redirects(self):
  opener=Opener();handlers=[]
  def build(*items):handlers.extend(items);return opener
  with patch('gptapps.explanations.urllib.request.build_opener',side_effect=build):
   result=ExplanationClient().create({'store':False},timeout=3)
  request,timeout=opener.calls[0];self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
  self.assertEqual(timeout,3);self.assertEqual(request.get_method(),'POST');self.assertEqual(result['status'],'completed')
  redirect=next(item for item in handlers if isinstance(item,urllib.request.HTTPRedirectHandler))
  self.assertIsNone(redirect.redirect_request(request,None,302,'Found',{},'https://evil.invalid'))
 def test_transport_provider_and_oversized_failures_are_safe_without_retries(self):
  for opener in [Opener(error=TimeoutError('private')),Opener(error=urllib.error.HTTPError('url',429,'private',{},io.BytesIO(b'private'))),Opener(io.BytesIO(b'x'*65537)),Opener(io.BytesIO(b'{invalid'))]:
   with self.subTest(opener=type(opener).__name__),patch('gptapps.explanations.urllib.request.build_opener',return_value=opener):
    with self.assertRaises(ExplanationFailure) as failure:ExplanationClient().create({})
    self.assertNotIn('private',str(failure.exception));self.assertEqual(len(opener.calls),1)
 def test_missing_key_does_not_open_transport(self):
  with patch.dict(os.environ,{},clear=True),patch('gptapps.explanations.urllib.request.build_opener') as build:
   with self.assertRaises(ExplanationFailure):ExplanationClient().create({})
   build.assert_not_called()

class NestedJSONFailureTests(unittest.TestCase):
 def test_parser_recursion_during_assessment_keeps_the_optional_failure_boundary(self):
  record={**ModelRouter(Recorder()).select(app(),'Help',[],[],[]),'mode':'auto'}
  with patch('gptapps.explanations.json.loads',side_effect=RecursionError('private nested JSON')):
   result=explain_selection(record,app(),'Help',[],[],Explainer())
  self.assertEqual(result['explanation_status'],'unavailable')
  self.assertEqual(result['requested_model'],record['requested_model'])
  self.assertNotIn('private nested JSON',json.dumps(result))
 def test_parser_recursion_in_transport_is_a_safe_explanation_failure(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only-not-a-real-key'}),patch('gptapps.explanations.urllib.request.build_opener',return_value=Opener()),patch('gptapps.explanations.json.loads',side_effect=RecursionError('private nesting')):
   with self.assertRaises(ExplanationFailure):ExplanationClient().create({})
 def test_deeply_nested_provider_json_is_unavailable_on_supported_pythons(self):
  raw=b'['*2000+b'0'+b']'*2000
  with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only-not-a-real-key'}),patch('gptapps.explanations.urllib.request.build_opener',return_value=Opener(io.BytesIO(raw))):
   with self.assertRaises(ExplanationFailure):ExplanationClient().create({})
