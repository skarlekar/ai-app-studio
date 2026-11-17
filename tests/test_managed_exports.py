import json
from pathlib import Path
import tempfile
import unittest
import os
import subprocess
import sys
from test_launchers import ROOT,request,unused_port,wait_ready,stop
from gptapps.build import build_app
from test_agents_config import managed
from test_framework import app


class ManagedExportTests(unittest.TestCase):
    def test_both_runtimes_export_every_shared_module_without_runtime_data(self):
        with tempfile.TemporaryDirectory() as folder:
            for index,config in enumerate((app(),managed())):
                target=Path(folder)/str(index);build_app(config,target)
                for name in ('agents_config.py','agents_client.py','agents_runtime.py','runs.py','tools.py','workshop.js','workshop.css'):
                    self.assertTrue((target/'gptapps'/name).is_file(),name)
                self.assertEqual(json.loads((target/'app.json').read_text())['runtime']['api'],config['runtime']['api'])
                self.assertFalse(list(target.rglob('*.sqlite3')))
                requirements=(target/'requirements.txt').read_text()
                self.assertEqual(requirements,'openai==3.13.0\n' if config['runtime']['api']=='agents' else '')
                self.assertIn('launcher_agents',(target/'start.sh').read_text())
                self.assertIn('requirements.txt',(target/'Dockerfile').read_text())
                self.assertTrue((target/'gptapps/build-info.json').is_file())

    def test_framework_and_generated_launchers_offer_optional_agents_support(self):
        root=Path(__file__).resolve().parents[1]
        for path in ('scripts/launcher-common.sh','gptapps/templates/launcher-common.sh'):
            content=(root/path).read_text();self.assertIn('--agents',content)
            self.assertIn('launcher_agents()',content)
        self.assertIn('WITH_AGENTS',(root/'Dockerfile').read_text())

    def test_generated_managed_app_runs_its_own_runtime_with_injected_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);app=managed();target=folder/'standalone';build_app(app,target)
            port=unused_port();base=f'http://127.0.0.1:{port}';logfile=folder/'server.log'
            env={**os.environ,'GPTAPPS_FIXTURE_RUNTIME_ROOT':str(target)}
            with logfile.open('w') as log:
                proc=subprocess.Popen([sys.executable,str(ROOT/'tests/serve_managed_fixture.py'),str(target/'app.json'),str(folder/'data'),str(port),'--standalone'],env=env,stdout=log,stderr=log)
                try:
                    wait_ready(proc,base,logfile,builder=False)
                    with request(base,'/api/runs',{'app_id':app['id'],'message':'Make a file','submission_id':'export-request'}) as response:run=json.load(response)
                    with request(base,'/api/runs/'+run['id']+'/events?app='+app['id']) as response:
                        self.assertIn('"type": "done"',response.read().decode())
                    with request(base,'/api/sessions?app='+app['id']+'&id='+run['session_id']) as response:
                        saved=json.load(response);artifact=saved['messages'][-1]['artifacts'][0]
                    with request(base,'/api/artifacts/'+artifact['id']+'/content?app='+app['id']) as response:self.assertEqual(response.read(),b'hello')
                    for name in ('workshop.js','workshop.css'):
                        with request(base,'/static/'+name) as response:self.assertGreater(len(response.read()),100)
                finally:stop(proc)

    @unittest.skipUnless(os.environ.get('GPTAPPS_TEST_AGENTS_VENV'),'Set GPTAPPS_TEST_AGENTS_VENV to a disposable pinned SDK environment')
    def test_generated_agents_launcher_uses_pinned_optional_sdk(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);target=folder/'standalone';build_app(managed(),target)
            port=unused_port();base=f'http://127.0.0.1:{port}';logfile=folder/'server.log'
            env={**os.environ,'GPTAPPS_PYTHON':sys.executable,'GPTAPPS_AGENTS_VENV':os.environ['GPTAPPS_TEST_AGENTS_VENV'],'OPENAI_API_KEY':'test-only-no-request'}
            with logfile.open('w') as log:
                proc=subprocess.Popen(['bash',str(target/'start.sh'),'--port',str(port),'--no-browser'],env=env,stdout=log,stderr=log)
                try:
                    wait_ready(proc,base,logfile,builder=False)
                    with request(base,'/api/config') as response:self.assertTrue(json.load(response)['runtimes']['agents']['available'])
                finally:stop(proc)

    @unittest.skipUnless(os.environ.get('GPTAPPS_TEST_DOCKER')=='1','Set GPTAPPS_TEST_DOCKER=1 for real managed-image verification')
    def test_managed_images_include_sdk_assets_and_python_without_private_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'standalone';build_app(managed(),target)
            for context,tag,extra in [(ROOT,'ai-app-studio:workshop-test',['--build-arg','WITH_AGENTS=1']),
                                      (target,'ai-app-studio:workshop-export-test',[])]:
                build=subprocess.run(['docker','build',*extra,'--tag',tag,str(context)],capture_output=True,text=True)
                self.assertEqual(build.returncode,0,build.stderr[-3000:])
                probe='import sys,pathlib; from importlib.metadata import version; from gptapps.agents_client import sdk_available; assert sys.version_info>=(3,11); assert version("openai")=="3.13.0" and sdk_available(); assert pathlib.Path("/app/gptapps/workshop.js").is_file(); assert pathlib.Path("/app/gptapps/workshop.css").is_file(); assert not pathlib.Path("/app/app.json").exists()'
                result=subprocess.run(['docker','run','--rm',tag,'python','-c',probe],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
