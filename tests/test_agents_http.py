import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from test_agents_config import managed
from test_launchers import ROOT,request,stop,unused_port,wait_ready


class AgentsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
        self.apps=self.folder/'apps';self.apps.mkdir();self.app=managed();self.other=managed(name='Other')
        for app in (self.app,self.other):(self.apps/(app['id']+'.json')).write_text(json.dumps(app))
        self.base=f'http://127.0.0.1:{unused_port()}';self.log=(self.folder/'server.log').open('w')
        self.proc=subprocess.Popen([sys.executable,str(ROOT/'tests/serve_managed_fixture.py'),str(self.apps),str(self.folder/'data'),self.base.rsplit(':',1)[1]],stdout=self.log,stderr=self.log)
        try:wait_ready(self.proc,self.base,self.folder/'server.log',builder=True)
        except Exception:self.tearDown();raise
    def tearDown(self):stop(self.proc);self.log.close();self.tmp.cleanup()
    def get(self,path):
        with request(self.base,path) as response:return json.load(response)
    def post(self,path,body):
        with request(self.base,path,body) as response:return response.status,json.load(response)
    def start(self):return self.post('/api/runs',{'app_id':self.app['id'],'message':'hello','submission_id':'http-request-1'})[1]
    def wait(self,run):
        for _ in range(100):
            value=self.get('/api/runs/'+run['id']+'?app='+self.app['id'])
            if value['state'] in ('completed','failed','needs_reconciliation','cancelled'):return value
            time.sleep(.03)
        self.fail('Task did not finish')

    def test_async_run_history_events_and_duplicate_submission(self):
        run=self.start();result=self.wait(run);self.assertEqual(result['state'],'completed',result)
        self.assertEqual(self.start()['id'],run['id'])
        lookup=self.get('/api/runs?app='+self.app['id']+'&submission_id=http-request-1')
        self.assertEqual(lookup['id'],run['id'])
        saved=self.get('/api/sessions?app='+self.app['id']+'&id='+run['session_id'])
        self.assertEqual(saved['messages'][-1]['content'],'A verified briefing.')
        with request(self.base,'/api/runs/'+run['id']+'/events?app='+self.app['id']) as response:
            stream=response.read().decode();self.assertIn('"type": "done"',stream)
            self.assertIn('"type": "delta"',stream)

    def test_runtime_metadata_and_configuration_check(self):
        apps=self.get('/api/apps');self.assertEqual(apps[0]['runtime']['api'],'agents')
        config=self.get('/api/config');self.assertTrue(config['runtimes']['agents']['fixed_only'])
        status,result=self.post('/api/runtime/check',{'name':'Draft','instructions':'Help','api':'agents','model':'test-agent'})
        self.assertEqual(status,200);self.assertEqual(result['provider_access'],'not_verified')

    def test_cross_app_run_and_artifact_access_is_rejected(self):
        run=self.start();result=self.wait(run)
        with self.assertRaises(urllib.error.HTTPError) as error:self.get('/api/runs/'+run['id']+'?app='+self.other['id'])
        self.assertEqual(error.exception.code,404);error.exception.close()
        artifact=result['artifacts'][0]
        with request(self.base,'/api/artifacts/'+artifact['id']+'/content?app='+self.app['id']) as response:
            self.assertEqual(response.read(),b'hello')
            self.assertIn('attachment;',response.headers['Content-Disposition'])
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        with self.assertRaises(urllib.error.HTTPError) as error:self.get('/api/artifacts/'+artifact['id']+'/content?app='+self.other['id'])
        error.exception.close()

    def test_cleanup_requires_explicit_confirmation(self):
        run=self.start();self.wait(run)
        body={'app_id':self.app['id'],'session_id':run['session_id']}
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/sessions/cleanup',body)
        error.exception.close()
        _,result=self.post('/api/sessions/cleanup',{**body,'confirm':True})
        self.assertTrue(result['archived']);self.assertFalse(result['cleanup_pending'])
