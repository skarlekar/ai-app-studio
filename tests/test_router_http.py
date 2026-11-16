import base64,json,os,subprocess,sys,tempfile,unittest,zipfile,io
from pathlib import Path
from test_router_integration import policy
from test_launchers import ROOT,request,stop,unused_port,wait_ready
from gptapps.spec import from_chat_input
from gptapps.build import build_app

class RouterHTTPTests(unittest.TestCase):
 def test_auto_creation_stream_status_history_and_standalone_export(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);apps=root/'apps';apps.mkdir();policy_file=root/'policy.json';policy_file.write_text(json.dumps(policy()))
   capture=root/'answer.json';decision=root/'decision.json';port=unused_port();base=f'http://127.0.0.1:{port}';logfile=root/'server.log'
   env={**os.environ,'OPENAI_MODEL':'test-model','OPENAI_ROUTING_POLICY_FILE':str(policy_file),'GPTAPPS_CAPTURE_REQUESTS':str(capture),'GPTAPPS_CAPTURE_DECISION':str(decision)}
   with logfile.open('w') as log:
    process=subprocess.Popen([sys.executable,str(ROOT/'tests/serve_fixture.py'),str(apps),str(root/'data'),str(port)],env=env,stdout=log,stderr=log)
    try:
     wait_ready(process,base,logfile)
     with request(base,'/api/config') as response:self.assertTrue(json.load(response)['routing_available'])
     with request(base,'/api/setup',{'field':'model','message':'auto'}) as response:self.assertEqual(json.load(response)['value'],'auto')
     with request(base,'/api/apps',{'name':'Auto Docs','instructions':'Help','model':'auto'}) as response:aid=json.load(response)['id']
     files=[{'name':'notes.txt','data':base64.b64encode(b'AMBER-42').decode()},{'name':'guide.pdf','data':base64.b64encode(b'%PDF synthetic').decode()}]
     with request(base,'/api/chat',{'app_id':aid,'message':'Summarize these files','attachments':files,'stream':True}) as response:
      events=[json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith('data: ')]
     self.assertTrue(any(event['type']=='routing' for event in events));done=events[-1];self.assertEqual(done['type'],'done');sid=done['session_id']
     self.assertEqual(done['message']['routing']['reported_model'],'test-economy')
     evidence=json.loads(json.loads(decision.read_text())['input']);self.assertEqual(len(evidence['files']),2)
     pdf=next(f for f in evidence['files'] if f['name']=='guide.pdf');self.assertNotIn('excerpt',pdf)
     self.assertIn('data:application/pdf;base64,',json.dumps(json.loads(capture.read_text())['input']))
     with request(base,'/api/chat',{'app_id':aid,'session_id':sid,'message':'A complex follow-up'}) as response:self.assertEqual(json.load(response)['message']['routing']['requested_model'],'test-advanced')
     with request(base,'/api/chat',{'app_id':aid,'message':'router-timeout'}) as response:self.assertTrue(json.load(response)['message']['routing']['fallback'])
     with request(base,f'/api/sessions?app={aid}&id={sid}') as response:self.assertEqual(json.load(response)['messages'][-1]['routing']['requested_model'],'test-advanced')
     with request(base,f'/api/build?app={aid}') as response:
      with zipfile.ZipFile(io.BytesIO(response.read())) as package:
       self.assertTrue(all('gptapps/'+name in package.namelist() for name in ('routing.py','decisions.py','routing.js','routing.css')))
       manifest=json.loads(package.read('app.json'));self.assertIn('routing',manifest['runtime']);self.assertNotIn(str(policy_file),package.read('app.json').decode())
       self.assertFalse(any(name.endswith('.sqlite3') for name in package.namelist()))
    finally:stop(process)
 def test_exported_auto_launcher_needs_no_fixed_default_model(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);manifest=from_chat_input({'name':'Auto','instructions':'Help'})
   manifest['runtime']['routing']=policy();target=root/'export';build_app(manifest,target)
   port=unused_port();base=f'http://127.0.0.1:{port}';logfile=root/'startup.log'
   env={k:v for k,v in os.environ.items() if k not in ('OPENAI_MODEL','OPENAI_SETUP_MODEL','OPENAI_ROUTING_POLICY_FILE')}
   env.update(OPENAI_API_KEY='test-only-not-a-real-key',GPTAPPS_PYTHON=sys.executable)
   with logfile.open('w') as log:
    process=subprocess.Popen(['bash',str(target/'start.sh'),'--port',str(port),'--no-browser'],cwd=root,env=env,stdout=log,stderr=log)
    try:
     wait_ready(process,base,logfile,builder=False)
     with request(base,'/static/routing.js') as response:self.assertIn(b'routingShow',response.read())
    finally:stop(process)

@unittest.skipUnless(os.environ.get('GPTAPPS_TEST_DOCKER')=='1','Set GPTAPPS_TEST_DOCKER=1 for routing Docker verification')
class RouterDockerTests(unittest.TestCase):
 def test_builder_mounts_policy_and_auto_export_starts_without_default_model(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);path=root/'policy file.json';path.write_text(json.dumps(policy()))
   port=unused_port();base=f'http://127.0.0.1:{port}';logfile=root/'builder.log'
   env={**os.environ,'OPENAI_API_KEY':'test-only-not-a-real-key','OPENAI_MODEL':'test-model','GPTAPPS_CONTAINER_NAME':f'gpt-router-builder-{port}','GPTAPPS_DOCKER_IMAGE':'gpt-router-builder:test'}
   with logfile.open('w') as log:
    process=subprocess.Popen(['bash',str(ROOT/'docker-start.sh'),'--routing-policy',str(path),'--apps',str(root/'apps'),'--data',str(root/'data'),'--port',str(port),'--no-browser'],env=env,stdout=log,stderr=log)
    try:
     wait_ready(process,base,logfile,timeout=90)
     with request(base,'/api/config') as response:self.assertTrue(json.load(response)['routing_available'])
     with request(base,'/api/apps',{'name':'Docker Auto','instructions':'Help','model':'auto'}) as response:aid=json.load(response)['id']
     with request(base,f'/api/build?app={aid}') as response:
      target=root/'standalone';target.mkdir()
      with zipfile.ZipFile(io.BytesIO(response.read())) as package:package.extractall(target)
     self.assertFalse((target/'policy file.json').exists());self.assertIsNone(json.loads((target/'app.json').read_text())['runtime']['model'])
    finally:stop(process)
   port=unused_port();base=f'http://127.0.0.1:{port}';logfile=root/'export.log'
   env={k:v for k,v in env.items() if k not in ('OPENAI_MODEL','OPENAI_SETUP_MODEL','OPENAI_ROUTING_POLICY_FILE')}
   env.update(GPTAPPS_CONTAINER_NAME=f'gpt-router-app-{port}',GPTAPPS_DOCKER_IMAGE='gpt-router-app:test')
   with logfile.open('w') as log:
    process=subprocess.Popen(['bash',str(target/'docker-start.sh'),'--port',str(port),'--no-browser'],env=env,stdout=log,stderr=log)
    try:
     wait_ready(process,base,logfile,timeout=90,builder=False)
     with request(base,'/static/routing.js') as response:self.assertIn(b'routingShow',response.read())
    finally:stop(process)
