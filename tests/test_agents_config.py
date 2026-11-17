import copy
import unittest
from gptapps.spec import from_chat_input, validate, analyze


def managed(**changes):
    return from_chat_input({'name':'Workshop','instructions':'Preserve these instructions.\n',
                            'api':'agents','model':'test-agent',**changes})


class AgentsConfigTests(unittest.TestCase):
    def test_legacy_response_config_is_not_mutated(self):
        app=from_chat_input({'name':'Legacy','instructions':'Help'})
        original=copy.deepcopy(app);validate(app)
        self.assertEqual(app,original)
        self.assertEqual(app['runtime']['api'],'responses')

    def test_explicit_managed_config_and_defaults(self):
        app=managed()
        self.assertEqual(app['schema_version'],'2.0')
        self.assertEqual(app['runtime']['api'],'agents')
        self.assertEqual(app['runtime']['agents']['environment'],'openai_hosted')
        self.assertEqual(app['runtime']['agents']['network_access'],'disabled')
        self.assertEqual(app['runtime']['agents']['review'],'auto_review')
        self.assertEqual(app['instructions'],'Preserve these instructions.\n')

    def test_agents_requires_fixed_model_and_disallows_auto(self):
        for model in (None,'auto','default',''):
            with self.subTest(model=model),self.assertRaisesRegex(ValueError,'explicit fixed model'):
                managed(model=model)

    def test_agents_settings_fail_closed(self):
        for settings in ({'network_access':'enabled'},{'review':'none'}, {'tool_policy':'write'},
                         {'environment':'self_hosted'},{'max_run_seconds':True},
                         {'max_run_seconds':0},{'env':{'SECRET':'value'}},
                         {'artifact_retention_days':0}):
            with self.subTest(settings=settings),self.assertRaises(ValueError):managed(agents=settings)

    def test_capability_report_does_not_silently_drop_tools(self):
        app=managed(tools=['image_generation'])
        self.assertIn('agents_tool_unsupported',{i['code'] for i in analyze(app)['issues']})
        self.assertFalse(analyze(app)['runtime_ready'])
        app=managed(tools=['code_interpreter'],agents={'environment':'none'})
        self.assertFalse(analyze(app)['runtime_ready'])

    def test_unknown_runtime_and_legacy_agents_are_rejected(self):
        with self.assertRaises(ValueError):managed(api='invented')
        app=managed();app['schema_version']='1.0'
        with self.assertRaises(ValueError):validate(app)

    def test_schema_output_requires_explicit_adapter(self):
        app=managed();app['runtime']['output_schema']={'type':'object'}
        self.assertFalse(analyze(app)['runtime_ready'])

