"""Synthetic managed-provider HTTP/browser fixture; makes no OpenAI requests."""
import os
import json
from pathlib import Path
import sys
sys.path.insert(0,os.environ.get('GPTAPPS_FIXTURE_RUNTIME_ROOT',str(Path(__file__).resolve().parents[1])))
from test_agents_runtime import FakeAgents
from gptapps.web import serve

if '--setup-fixture' in sys.argv:
    import gptapps.web as web
    from gptapps.setup import SetupInterpreter
    from test_framework import response
    os.environ['OPENAI_SETUP_MODEL']='synthetic-setup'
    class SetupClient:
        def create(self,payload):
            item=json.loads(payload['input'][0]['content']);field=item['field'];reply=item['reply']
            value=[] if field in ('starters','tools','knowledge_files','actions') else reply
            return response(json.dumps({'status':'accept','value':value,'message':'Synthetic setup value recorded.'}))
    web.SetupInterpreter=lambda client=None:SetupInterpreter(SetupClient())

client=FakeAgents()
if '--slow' in sys.argv:
    from contextlib import contextmanager
    import threading
    original=client.create
    @contextmanager
    def slow(*args):
        client.status='in_progress';client.wait.clear()
        threading.Timer(3,client.wait.set).start()
        with original(*args) as events:yield events
    client.create=slow
client.metadata=[{'id':'artifact-example','session_id':'sess-test','turn_id':'turn-1',
                  'path':'/workspace/outputs/briefing.txt','size_bytes':5}]
serve(sys.argv[1],sys.argv[2],port=int(sys.argv[3]),builder='--standalone' not in sys.argv,agents_client=client)
