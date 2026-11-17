import os
import unittest
from unittest.mock import patch
from gptapps.setup import SetupInterpreter
from test_framework import FakeClient
from test_setup import interpretation


class RuntimeSetupTests(unittest.TestCase):
    def test_explicit_runtime_choices_do_not_need_ai_inference(self):
        setup=SetupInterpreter(FakeClient())
        self.assertEqual(setup.interpret('api','Agents API')['value'],'agents')
        self.assertEqual(setup.interpret('api','Responses')['value'],'responses')

    def test_agents_default_and_auto_require_clarification(self):
        setup=SetupInterpreter(FakeClient())
        for model in ('auto','default','Use the server default'):
            result=setup.interpret('model',model,runtime_api='agents')
            self.assertEqual(result['status'],'clarify')
            self.assertIn('fixed model',result['message'])

    @patch.dict(os.environ,{'OPENAI_SETUP_MODEL':'test-setup'})
    def test_free_form_runtime_interpretation_is_validated(self):
        setup=SetupInterpreter(FakeClient(interpretation('agents')))
        self.assertEqual(setup.interpret('api','Let OpenAI manage the task')['value'],'agents')
        setup=SetupInterpreter(FakeClient(interpretation('arbitrary')))
        with self.assertRaises(ValueError):setup.interpret('api','something else')
