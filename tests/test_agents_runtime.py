import base64
from contextlib import contextmanager
import copy
import tempfile
import threading
import time
import unittest
from gptapps.agents_runtime import ManagedRuntime
from gptapps.extensions import Registry, FunctionTool
from test_agents_config import managed


class FakeAgents:
    def __init__(self):
        self.created=[];self.sent=[];self.results=[];self.deleted=[];self.uploads=[]
        self.sid='sess-test';self.tid='turn-1';self.status='in_progress';self.text='A verified briefing.'
        self.wait=threading.Event();self.wait.set();self.actions=[];self.metadata=[];self.fail_create=False
    @contextmanager
    def create(self,agent,environment,message,run_id):
        self.created.append((agent,environment,message,run_id))
        if self.fail_create:raise OSError('ambiguous connection error')
        yield iter([{'type':'agent.session.created','session':{'id':self.sid,'environment':{'id':'env-test'}}},
                    {'type':'agent.session.turn.created','session_id':self.sid,'turn_id':self.tid,'turn':{'subagent_id':None}}])
    @contextmanager
    def events(self,sid):
        yield self._events()
    def _events(self):
        yield {'type':'agent.session.turn.output_text.delta','session_id':self.sid,'turn_id':self.tid,'delta':'A verified ','output_index':0,'content_index':0}
        self.wait.wait(2)
        if self.status=='in_progress' and not self.actions:self.status='completed'
        if self.actions:
            yield {'type':'agent.session.requires_action','session':self.session(self.sid)}
        yield {'type':'agent.session.idle','session':self.session(self.sid)}
    def session(self,sid):return {'id':sid,'environment':{'id':'env-test','status':'connected'},'status':'requires_action' if self.actions else 'idle' if self.status in ('completed','cancelled') else 'in_progress','required_actions':copy.deepcopy(self.actions)}
    def turns(self,sid):return [{'id':self.tid,'status':self.status,'subagent_id':None}]
    def turn(self,sid,tid):return {'id':tid,'status':self.status,'usage':{'total_tokens':25}}
    def items(self,sid):return [{'id':'message-1','type':'message','role':'assistant','phase':'final_answer','turn_id':self.tid,'content':[{'type':'output_text','text':self.text}]}] if self.status=='completed' else []
    def send(self,sid,message,submission):self.sent.append((sid,message,submission));self.tid='turn-2';self.status='in_progress'
    def tool_result(self,sid,tid,cid,result):self.results.append(result);self.actions=[];self.status='completed'
    def artifacts(self,sid):return self.metadata
    def content(self,sid,aid):return iter([b'hello'])
    def cancel(self,sid):self.status='cancelled';self.wait.set()
    def upload(self,name,raw):self.uploads.append((name,raw));return {'id':'file-test'}
    def attach(self,*args):pass
    def collection(self,sid):return {'id':sid,'file_counts':{'completed':1}}
    def inventory(self,sid):return [{'id':'file-knowledge','status':'completed','created_at':1}]
    def search(self,sid,query):return {'data':[{'file_id':'file-knowledge','filename':'Guide.txt','content':[{'type':'text','text':'Verified passage'}]}]}
    def delete(self,sid):self.deleted.append(sid)
    def delete_file(self,fid):self.deleted.append(fid)


class ManagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.client=FakeAgents();self.registry=Registry();self.app=managed()
        self.runtime=ManagedRuntime(self.tmp.name,client=self.client,registry=self.registry)
        self.addCleanup(self.runtime.close)
    def start(self,sid=None,submission='request-1',**kw):
        return self.runtime.start(self.app,kw.get('message','Make a briefing'),sid,submission,kw.get('attachments'))
    def done(self,run):
        end=time.monotonic()+4
        while time.monotonic()<end:
            result=self.runtime.store.get(self.app['id'],run['id'])
            if result['state'] in ('completed','failed','cancelled','needs_reconciliation'):return result
            time.sleep(.01)
        self.fail('Managed task did not finish')

    def test_managed_task_streams_saves_and_retries_without_duplicate_work(self):
        run=self.start();result=self.done(run)
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(result['result']['message']['content'],self.client.text)
        self.assertTrue(any(e['type']=='delta' for e in self.runtime.store.events(self.app['id'],run['id'])))
        self.assertEqual(self.start()['id'],run['id']);self.assertEqual(len(self.client.created),1)
        second=self.start(run['session_id'],'request-2');self.assertEqual(self.done(second)['state'],'completed')
        self.assertEqual(len(self.client.created),1);self.assertEqual(len(self.client.sent),1)

    def test_browser_observer_disconnection_does_not_stop_task(self):
        self.client.wait.clear();run=self.start()
        events=self.runtime.observe(self.app['id'],run['id']);next(events);events.close()
        self.client.wait.set();self.assertEqual(self.done(run)['state'],'completed')

    def test_observer_drains_events_committed_before_terminal_snapshot(self):
        from unittest.mock import patch
        completed={'state':'completed','result':{'session_id':'managed-test','message':{'content':'Final'}}}
        batches=[[],[{'type':'delta','sequence':1,'delta':'Final'}],
                 [{'type':'delta','sequence':1,'delta':'Final'}],[],[]]
        with patch.object(self.runtime.store,'get',return_value=completed), patch.object(self.runtime.store,'events',side_effect=batches):
            events=list(self.runtime.observe(self.app['id'],'synthetic'))
        self.assertTrue(any(e['type']=='delta' for e in events))
        self.assertEqual(events[-1]['type'],'done')

    def test_ambiguous_initial_submission_is_not_retried(self):
        self.client.fail_create=True;run=self.start();self.assertEqual(self.done(run)['state'],'needs_reconciliation')
        self.runtime.recover();time.sleep(.03);self.assertEqual(len(self.client.created),1)

    def test_read_only_tool_arguments_and_results_are_recorded(self):
        called=[]
        self.registry.add(FunctionTool('lookup','Lookup',{'type':'object','properties':{'q':{'type':'string'}},'required':['q'],'additionalProperties':False},lambda q:called.append(q) or {'found':True},replay_safe=True))
        self.app['bindings']['function_tools']=['lookup']
        self.client.actions=[{'type':'function_call','turn_id':'turn-1','call_id':'call-1','name':'lookup','arguments':{'q':'test'}}]
        run=self.start();self.assertEqual(self.done(run)['state'],'completed');self.assertEqual(called,['test'])
        self.assertTrue(self.client.results[0]['success'])

    def test_unapproved_write_and_non_replay_safe_handlers_block_before_submission(self):
        for read_only,replay_safe in ((False,True),(True,False)):
            self.registry=Registry();self.runtime.registry=self.registry
            self.registry.add(FunctionTool('write','Write',{'type':'object','properties':{},'additionalProperties':False},lambda:None,read_only=read_only,replay_safe=replay_safe))
            self.app['bindings']['function_tools']=['write']
            with self.assertRaises(ValueError):self.start()
        self.assertFalse(self.client.created)

    def test_cancel_is_confirmed_against_provider_turn(self):
        self.client.wait.clear();run=self.start()
        end=time.monotonic()+2
        while not self.runtime.store.get(self.app['id'],run['id'])['provider_session_id'] and time.monotonic()<end:time.sleep(.01)
        self.runtime.cancel(self.app['id'],run['id'])
        self.assertEqual(self.done(run)['state'],'cancelled')

    def test_knowledge_is_app_scoped_and_citations_are_saved(self):
        self.app['bindings']['vector_store_ids']=['vs-owner']
        self.client.actions=[{'type':'function_call','turn_id':'turn-1','call_id':'call-1','name':'search_knowledge','arguments':{'query':'policy'}}]
        result=self.done(self.start())
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(result['result']['message']['citations'][0]['title'],'Guide.txt')

    def test_completion_on_initial_stream_pins_knowledge_revision(self):
        self.app['bindings']['vector_store_ids']=['vs-owner']
        original=self.client.create
        @contextmanager
        def complete_immediately(*args):
            with original(*args) as events:
                def stream():
                    yield from events
                    self.client.status='completed'
                    yield {'type':'agent.session.idle','session':self.client.session(self.client.sid)}
                yield stream()
        self.client.create=complete_immediately
        run=self.start();self.assertEqual(self.done(run)['state'],'completed')
        self.assertTrue(self.runtime.store.conversation(self.app['id'],run['session_id'])['knowledge_revision'])

    def test_tool_delivery_error_does_not_leave_provider_work_unmanaged(self):
        self.registry.add(FunctionTool('lookup','Lookup',{'type':'object','properties':{},'additionalProperties':False},lambda:'ok',replay_safe=True))
        self.app['bindings']['function_tools']=['lookup']
        self.client.actions=[{'type':'function_call','turn_id':'turn-1','call_id':'call-1','name':'lookup','arguments':{}}]
        def rejected(*args):
            error=RuntimeError('invalid result');error.status_code=400;raise error
        self.client.tool_result=rejected
        result=self.done(self.start())
        self.assertEqual(result['state'],'failed')
        self.assertEqual(self.client.status,'cancelled')

    def test_artifact_must_belong_to_completed_turn(self):
        self.client.metadata=[{'id':'art-test','session_id':'sess-test','turn_id':'turn-1','path':'/workspace/outputs/report.txt','size_bytes':5}]
        result=self.done(self.start());self.assertEqual(result['state'],'completed',result)
        self.assertEqual(len(result['artifacts']),1)

    def test_none_environment_rejects_attachments_before_accepting_work(self):
        self.app['runtime']['agents']['environment']='none'
        with self.assertRaisesRegex(ValueError,'workspace'):
            self.start(attachments=[{'name':'hello.txt','data':base64.b64encode(b'hello').decode()}])
        self.assertFalse(self.client.created)

    def test_deadline_requests_cancellation_even_without_text_events(self):
        self.client.wait.clear();run=self.start()
        self.runtime.store.update(run['id'],created=time.time()-1000)
        self.assertEqual(self.done(run)['state'],'cancelled')

    def test_completed_run_is_not_reversed_by_cancel_race(self):
        result=self.done(self.start())
        cancelled=self.runtime.cancel(self.app['id'],result['id'])
        self.assertEqual(cancelled['state'],'completed')

    def test_restart_recovers_known_session_without_resubmitting(self):
        self.client.wait.clear();run=self.start()
        end=time.monotonic()+2
        while not self.runtime.store.get(self.app['id'],run['id'])['provider_session_id'] and time.monotonic()<end:time.sleep(.01)
        self.runtime.close();self.client.wait.set()
        other=ManagedRuntime(self.tmp.name,client=self.client,registry=self.registry);self.addCleanup(other.close)
        self.runtime=other;other.recover()
        self.assertEqual(self.done(run)['state'],'completed')
        self.assertEqual(len(self.client.created),1);self.assertFalse(self.client.sent)

    def recover_unsent_followup(self,state):
        first=self.done(self.start());pinned=self.runtime.store.internal(first['id'])['payload']['app']
        second=self.runtime.store.create(pinned,first['session_id'],'unsent-followup','A different question',[])
        self.runtime.store.update(second['id'],state=state)
        self.runtime.recover();result=self.done(second)
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(len(self.client.sent),1)
        self.assertEqual(result['turn_id'],'turn-2')

    def test_restart_sends_queued_followup_instead_of_reusing_previous_answer(self):
        self.recover_unsent_followup('queued')

    def test_restart_sends_definitely_unsent_preparing_followup(self):
        self.recover_unsent_followup('preparing')

    def test_followup_early_eof_reconnects_without_resending(self):
        first=self.done(self.start());original=self.client.events;calls=[]
        @contextmanager
        def truncated_once(sid):
            calls.append(sid)
            if len(calls)==1:yield iter([])
            else:
                with original(sid) as events:yield events
        self.client.events=truncated_once
        result=self.done(self.start(first['session_id'],'followup-eof'))
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(len(self.client.sent),1)
        self.assertGreaterEqual(len(calls),2)

    def test_deadline_supervises_durable_work_without_a_live_worker(self):
        first=self.done(self.start());pinned=self.runtime.store.internal(first['id'])['payload']['app']
        second=self.runtime.store.create(pinned,first['session_id'],'unobserved-followup','New question',[])
        self.client.send(self.client.sid,'New question','unobserved-followup')
        self.runtime.store.update(second['id'],state='needs_reconciliation',input_sent=True,turn_id='turn-2',created=time.time()-1000)
        end=time.monotonic()+2
        while time.monotonic()<end and self.client.status!='cancelled':time.sleep(.01)
        self.assertEqual(self.client.status,'cancelled')
        self.assertEqual(self.done(second)['state'],'cancelled')

    def test_unknown_followup_send_is_not_resubmitted_or_bound_to_old_turn(self):
        first=self.done(self.start());pinned=self.runtime.store.internal(first['id'])['payload']['app']
        second=self.runtime.store.create(pinned,first['session_id'],'unknown-followup','New question',[])
        self.runtime.store.update(second['id'],state='preparing',input_sent=True,previous_turn_ids=[first['turn_id']])
        self.runtime.recover();result=self.done(second)
        self.assertEqual(result['state'],'needs_reconciliation',result)
        self.assertFalse(self.client.sent);self.assertIsNone(result['result'])

    def test_same_data_directory_cannot_have_two_supervisors(self):
        with self.assertRaisesRegex(ValueError,'another server'):
            ManagedRuntime(self.tmp.name,client=self.client)

    def test_expired_workspace_stops_without_recreating_session(self):
        self.client.wait.clear();original=self.client.session
        self.client.session=lambda sid:{**original(sid),'environment':{'id':'env-test','status':'expired'}}
        result=self.done(self.start())
        self.assertEqual(result['state'],'failed')
        self.assertIn('workspace',result['error'].lower());self.assertEqual(len(self.client.created),1)

    def test_cleanup_deletes_only_owned_resources_and_retries_failures(self):
        result=self.done(self.start());sid=result['session_id']
        self.runtime.store.resource(sid,'file','file-owned')
        self.runtime.store.resource('another-conversation','file','file-other')
        original=self.client.delete
        self.client.delete=lambda sid:(_ for _ in ()).throw(OSError('offline'))
        first=self.runtime.cleanup(self.app['id'],sid)
        self.assertTrue(first['cleanup_pending'])
        self.assertNotIn('file-other',self.client.deleted)
        self.client.delete=original;self.runtime.maintenance()
        self.assertTrue(all(r['status']=='deletion_confirmed' for r in self.runtime.store.resources(sid)))

    def test_unapproved_pending_tool_cancels_provider_before_reporting_failure(self):
        self.client.actions=[{'type':'function_call','turn_id':'turn-1','call_id':'call-1','name':'delete_everything','arguments':{}}]
        result=self.done(self.start())
        self.assertEqual(result['state'],'failed')
        self.assertEqual(self.client.status,'cancelled')

    def test_invalid_artifact_never_becomes_a_saved_answer(self):
        self.client.metadata=[{'id':'art-test','session_id':'different','turn_id':'turn-1','path':'/workspace/outputs/report.txt','size_bytes':5}]
        result=self.done(self.start())
        self.assertEqual(result['state'],'failed')
        self.assertIsNone(result['result'])

    def test_manual_manifest_missing_optional_defaults_still_gets_deadline(self):
        self.app['runtime']['agents']={}
        result=self.done(self.start())
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(self.runtime.store.internal(result['id'])['payload']['app']['runtime']['agents']['max_run_seconds'],300)

