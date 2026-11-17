import copy
import tempfile
import json
from pathlib import Path
import subprocess
import sys
import unittest
from gptapps.evaluation import prepare_report, run_suite, release_gate
from test_agents_config import managed


def suite():
    return {'name':'Owner acceptance','version':'1','thresholds':{'min_pass_rate':1.0,'max_latency_seconds':60},
            'cases':[{'id':'briefing','prompt':'Create a summary','rubric':['Correct answer','Follows instructions'],
                      'min_artifacts':0}]}


class EvaluationTests(unittest.TestCase):
    def test_unexecuted_or_unreviewed_report_holds_release(self):
        app=managed();report=prepare_report(app,suite())
        self.assertFalse(release_gate(app,report)['approved'])
        report['cases'][0]['candidate']={'state':'completed','latency_seconds':1,'message':{'content':'Answer'}}
        report['cases'][0]['baseline']={'state':'completed','latency_seconds':1,'message':{'content':'Answer'}}
        self.assertFalse(release_gate(app,report)['approved'])

    def test_review_requires_every_rubric_and_current_configuration(self):
        app=managed();report=run_suite(app,suite(),lambda app,prompt,files:{'message':{'content':'Answer'}})
        case=report['cases'][0]
        case['review']={'reviewer':'Owner','notes':'Compared both answers','checks':{'Correct answer':True,'Follows instructions':True}}
        self.assertTrue(release_gate(app,report)['approved'])
        changed=copy.deepcopy(app);changed['instructions']+=' Changed'
        self.assertFalse(release_gate(changed,report)['approved'])
        case['review']['checks']['Correct answer']=False
        self.assertFalse(release_gate(app,report)['approved'])

    def test_failure_or_missing_artifact_holds_even_with_positive_review(self):
        app=managed();s=suite();s['cases'][0]['min_artifacts']=1
        report=run_suite(app,s,lambda app,prompt,files:{'message':{'content':'Answer'}})
        report['cases'][0]['review']={'reviewer':'Owner','notes':'Checked','checks':{'Correct answer':True,'Follows instructions':True}}
        self.assertFalse(release_gate(app,report)['approved'])

    def test_runner_compares_responses_and_candidate_and_records_no_hidden_reasoning(self):
        calls=[]
        def execute(app,prompt,files):
            calls.append(app['runtime']['api']);return {'message':{'content':'Answer','routing':{'answer_usage':{'total_tokens':10}}}}
        report=run_suite(managed(),suite(),execute)
        self.assertEqual(calls,['responses','agents'])
        self.assertEqual(report['cases'][0]['candidate']['usage'],{'total_tokens':10})
        self.assertFalse(release_gate(managed(),report)['approved'])

    def test_missing_thresholds_duplicates_and_unknown_fixture_fields_rejected(self):
        for mutate in (lambda s:s.pop('thresholds'),lambda s:s['cases'].append(s['cases'][0]),lambda s:s['cases'][0].update(secret='x')):
            s=suite();mutate(s)
            with self.assertRaises(ValueError):prepare_report(managed(),s)

    def test_cli_prepares_private_report_without_provider_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);app=root/'app.json';app.write_text(json.dumps(managed()))
            data=root/'suite.json';data.write_text(json.dumps(suite()));out=root/'report.json'
            result=subprocess.run([sys.executable,'-m','gptapps','evaluate',str(app),'--suite',str(data),'--out',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIsNone(json.loads(out.read_text())['cases'][0]['candidate'])
            check=subprocess.run([sys.executable,'-m','gptapps','check',str(app),'--release-report',str(out)],capture_output=True,text=True)
            self.assertEqual(check.returncode,2,check.stderr)
            self.assertIn('release_hold',check.stdout)
