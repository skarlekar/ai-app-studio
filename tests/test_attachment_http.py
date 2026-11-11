"""Actual HTTP and exported-app requests, recorded locally without an OpenAI connection."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error

from gptapps.build import build_app
from test_framework import app
from test_attachments import attached
from test_launchers import ROOT, request, stop, unused_port, wait_ready


class AttachmentHTTPTests(unittest.TestCase):
    def exercise(self, standalone):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);target=folder/'application'
            build_app(app(),target)
            port=unused_port();base=f'http://127.0.0.1:{port}';logfile=folder/'server.log'
            capture=folder/'payload.json'
            env={**os.environ,'GPTAPPS_CAPTURE_REQUESTS':str(capture),'OPENAI_SETUP_MODEL':'test-setup'}
            if standalone:env['GPTAPPS_FIXTURE_RUNTIME_ROOT']=str(target)
            with logfile.open('w') as log:
                process=subprocess.Popen([sys.executable,str(ROOT/'tests/serve_fixture.py'),str(target/'app.json'),str(folder/'data'),str(port),'--standalone'],env=env,stdout=log,stderr=log) if standalone else None
                if not standalone:
                    apps=folder/'apps';apps.mkdir();(apps/'app.json').write_text(json.dumps(app()))
                    process=subprocess.Popen([sys.executable,str(ROOT/'tests/serve_fixture.py'),str(apps),str(folder/'data'),str(port)],env=env,stdout=log,stderr=log)
                try:
                    wait_ready(process,base,logfile,builder=not standalone)
                    with request(base,'/api/config') as result:
                        self.assertEqual(json.load(result)['chat_attachments']['max_files'],5)
                    with request(base,'/static/attachments.js') as result:self.assertIn(b'dragover',result.read())
                    # Exceed the previous 1.5MB JSON limit and preserve exact file bytes.
                    files=[attached('large.txt',b'AMBER-42 '*200000),attached('other.csv',b'name,amount\nExample,12\n')]
                    with request(base,'/api/chat',{'app_id':app()['id'],'message':'Compare both files','attachments':files,'stream':True}) as result:
                        events=[json.loads(line[6:]) for line in result.read().decode().splitlines() if line.startswith('data: ')]
                    self.assertEqual(events[-1]['type'],'done')
                    content=json.loads(capture.read_text())['input'][0]['content']
                    self.assertEqual(content[0]['text'],'Compare both files')
                    self.assertEqual(base64.b64decode(content[1]['file_data'].split(',',1)[1]),b'AMBER-42 '*200000)
                    self.assertEqual(content[2]['filename'],'other.csv')
                    sid=events[-1]['session_id']
                    with request(base,'/api/sessions?app='+app()['id']+'&id='+sid) as result:
                        saved=json.load(result);self.assertEqual(saved['messages'][0]['attachments'][0]['name'],'large.txt')
                        self.assertNotIn('file_data',json.dumps(saved));self.assertNotIn('data',saved['messages'][0]['attachments'][0])
                    with request(base,'/api/chat',{'app_id':app()['id'],'session_id':sid,'message':'What about the earlier file?'}) as result:json.load(result)
                    self.assertEqual(json.loads(capture.read_text())['input'][0]['content'],content)
                    before=capture.read_bytes()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request(base,'/api/chat',{'app_id':app()['id'],'message':'Invalid','attachments':[attached('../bad.txt')]})
                    self.assertEqual(error.exception.code,400);error.exception.close();self.assertEqual(capture.read_bytes(),before)
                    if not standalone:
                        with request(base,'/api/setup',{'field':'description','message':'Read the brief','attachments':[attached('brief.md')]}) as result:self.assertEqual(json.load(result)['status'],'accept')
                        parts=json.loads(capture.read_text())['input'][0]['content']
                        self.assertEqual(parts[1]['filename'],'brief.md')
                finally:stop(process)

    def test_studio_http_intake(self):self.exercise(False)
    def test_standalone_http_intake(self):self.exercise(True)
