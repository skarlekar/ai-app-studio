import unittest
from types import SimpleNamespace as NS
from gptapps.agents_client import AgentsClient, provider_error


class Recorder:
    def __init__(self):self.calls=[]
    def create(self,*args,**kwargs):self.calls.append(kwargs);return {'id':'sess-test'}


class AgentsClientTests(unittest.TestCase):
    def test_review_is_explicit_and_input_is_not_privileged(self):
        recorder=Recorder();client=AgentsClient(NS(beta=NS(agents=NS(sessions=recorder))))
        client.create({'model':'test-model','instructions':'Owner instructions'},
                      {'type':'openai_hosted','network':{'access':'disabled'}},'User question','run-test')
        call=recorder.calls[0]
        self.assertEqual(call['extra_body'],{'review':'auto_review'})
        self.assertEqual(call['agent']['instructions'],'Owner instructions')
        self.assertEqual(call['input'][0]['role'],'user')
        self.assertEqual(call['metadata'],{'studio_run_id':'run-test'})
        self.assertTrue(call['stream'])

    def test_incompatible_sdk_is_rejected_without_provider_call(self):
        with self.assertRaisesRegex(ValueError,'Agents support'):
            AgentsClient(NS(beta=NS())).sessions

    def test_provider_errors_do_not_expose_payloads_or_credentials(self):
        for code in (400,401,403,429,500):
            error=Exception('private instructions and sk-secret');error.status_code=code
            message=provider_error(error)
            self.assertIn(str(code),message)
            self.assertNotIn('sk-secret',message)
            self.assertNotIn('private instructions',message)

    def test_follow_up_has_idempotency_key(self):
        recorder=Recorder();client=AgentsClient(NS(beta=NS(agents=NS(sessions=NS(events=recorder)))))
        client.send('sess-test','follow up','submission-test')
        self.assertEqual(recorder.calls[0]['idempotency_key'],'submission-test')
        self.assertEqual(recorder.calls[0]['events'][0]['type'],'agent.session.input.message')

