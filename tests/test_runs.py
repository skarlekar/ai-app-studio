import tempfile
import unittest
from pathlib import Path
from gptapps.runs import RunStore, MAX_ARTIFACT_BYTES
from test_agents_config import managed


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=RunStore(self.temp.name);self.app=managed()
    def create(self,**kw):return self.store.create(self.app,kw.get('session_id'),kw.get('submission_id','request-1'),'hello',[])

    def test_duplicate_submission_is_identical_and_conflicts_fail(self):
        first=self.create();second=self.create()
        self.assertEqual(first['id'],second['id'])
        with self.assertRaisesRegex(ValueError,'submission'):
            self.store.create(self.app,None,'request-1','different',[])

    def test_only_one_active_turn_and_changed_config_requires_new_conversation(self):
        run=self.create()
        with self.assertRaisesRegex(ValueError,'active'):
            self.create(session_id=run['session_id'],submission_id='request-2')
        self.store.finish(run['id'],{'role':'assistant','content':'done'})
        self.app['instructions']='different'
        with self.assertRaisesRegex(ValueError,'configuration changed'):
            self.create(session_id=run['session_id'],submission_id='request-2')

    def test_cross_app_access_and_public_payload_filter(self):
        run=self.create()
        with self.assertRaisesRegex(ValueError,'not found'):self.store.get('other-app',run['id'])
        public=self.store.get(self.app['id'],run['id'])
        self.assertNotIn('payload',public);self.assertNotIn('instructions',str(public))
        self.assertNotIn('data',public)

    def test_events_are_ordered_and_survive_restart(self):
        run=self.create();self.store.event(run['id'],{'type':'status','message':'First'})
        self.store.event(run['id'],{'type':'status','message':'Second'})
        other=RunStore(self.temp.name);events=other.events(self.app['id'],run['id'])
        self.assertEqual([e['message'] for e in events],['First','Second'])
        self.assertEqual(len(other.events(self.app['id'],run['id'],events[0]['sequence'])),1)

    def test_completion_is_saved_once_and_session_is_scoped(self):
        run=self.create();message={'role':'assistant','content':'Done'}
        self.store.finish(run['id'],message);self.store.finish(run['id'],message)
        saved=self.store.get_session(self.app['id'],run['session_id'])
        self.assertEqual(len(saved['messages']),2)
        with self.assertRaises(ValueError):self.store.get_session('other',run['session_id'])

    def test_artifacts_require_valid_paths_sizes_and_ownership(self):
        run=self.create();self.store.update(run['id'],provider_session_id='sess-test',turn_id='turn-test')
        base={'id':'artifact-test','session_id':'sess-test','turn_id':'turn-test',
              'path':'/workspace/outputs/report.txt','size_bytes':5}
        for change in ({'path':'/workspace/outputs/../secret.txt'},{'path':'/workspace/outputs/page.html'},
                       {'path':'/workspace/outputs/run.py'},{'size_bytes':MAX_ARTIFACT_BYTES+1},
                       {'session_id':'another'},{'turn_id':'another'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.store.artifact(run['id'],{**base,**change},[b'hello'])
        result=self.store.artifact(run['id'],base,[b'hello'])
        data=self.store.artifact_content(self.app['id'],result['id'])
        self.assertEqual(data['path'].read_bytes(),b'hello')
        with self.assertRaises(ValueError):self.store.artifact_content('other',result['id'])
        with self.assertRaises(ValueError):self.store.artifact(run['id'],{**base,'id':'wrong-size'},[b'too much'])

    def test_tool_ledger_deduplicates_committed_results(self):
        run=self.create();self.store.tool_begin(run['id'],'turn','call','lookup',{'q':'x'})
        result={'success':True,'output':'found'};self.store.tool_finish(run['id'],'turn','call',result)
        self.assertEqual(self.store.tool_begin(run['id'],'turn','call','lookup',{'q':'x'})['result'],result)
        with self.assertRaises(ValueError):self.store.tool_begin(run['id'],'turn','call','different',{})

    def test_archive_expires_saved_downloads_and_source_links_without_losing_text(self):
        run=self.create();message={'role':'assistant','content':'Keep this answer',
            'artifacts':[{'id':'a'*32,'name':'answer.txt','size':5}],
            'citations':[{'source_id':'file-test','run_id':run['id'],'title':'Guide'}]}
        self.store.finish(run['id'],message);self.store.archive(self.app['id'],run['session_id'])
        saved=self.store.get_session(self.app['id'],run['session_id'])
        self.assertEqual(saved['messages'][-1]['content'],'Keep this answer')
        self.assertTrue(saved['messages'][-1]['artifacts'][0]['expired'])
        self.assertTrue(saved['messages'][-1]['citations'][0]['expired'])
        self.assertTrue(saved['run']['result']['message']['artifacts'][0]['expired'])

