import tempfile
import unittest
from gptapps.runtime import Runtime
from test_agents_config import managed
from test_agents_runtime import FakeAgents
from test_framework import FakeClient


class ManagedFacadeTests(unittest.TestCase):
    def test_shared_runtime_dispatches_and_restores_managed_history(self):
        with tempfile.TemporaryDirectory() as folder:
            provider=FakeAgents();runtime=Runtime(folder,client=FakeClient(),agents_client=provider)
            self.addCleanup(runtime.close);app=managed();events=[]
            result=runtime.chat(app,'hello',emit=events.append,submission_id='facade-request')
            self.assertEqual(result['message']['content'],provider.text)
            self.assertTrue(any(e['type']=='delta' for e in events))
            self.assertEqual(runtime.list_sessions(app['id'])[0]['id'],result['session_id'])
            self.assertEqual(runtime.get_session(app['id'],result['session_id'])['messages'][-1]['content'],provider.text)
            self.assertEqual(len(provider.created),1)
