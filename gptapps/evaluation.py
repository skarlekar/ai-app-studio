"""Owner-reviewed behavioral comparisons, separate from deterministic protocol tests.

Reports contain prompts and answers. Store them with private runtime data.
Preparing a report never calls a provider; execution is an explicit CLI option.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time

from .runs import fingerprint
from .spec import validate
from .version import build_info


def code_revision():
    digest=hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_suite(suite):
    if not isinstance(suite,dict) or set(suite)!={'name','version','thresholds','cases'}:
        raise ValueError('Evaluation suite requires name, version, thresholds and cases')
    if any(not isinstance(suite[k],str) or not suite[k].strip() for k in ('name','version')):
        raise ValueError('Evaluation suite needs a name and version')
    thresholds=suite['thresholds']
    if not isinstance(thresholds,dict) or set(thresholds)!={'min_pass_rate','max_latency_seconds'}:
        raise ValueError('Set owner-agreed pass-rate and latency thresholds')
    for key,upper in [('min_pass_rate',1),('max_latency_seconds',3600)]:
        number=thresholds[key]
        if type(number) not in (int,float) or not math.isfinite(number) or not 0<number<=upper:
            raise ValueError('Invalid evaluation threshold')
    cases=suite['cases']
    if not isinstance(cases,list) or not 1<=len(cases)<=50:raise ValueError('Use 1–50 evaluation cases')
    ids=set()
    for case in cases:
        if not isinstance(case,dict) or set(case)-{'id','prompt','rubric','min_artifacts','attachments','critical'}:
            raise ValueError('Unknown evaluation case fields')
        for key in ('id','prompt'):
            if not isinstance(case.get(key),str) or not case[key].strip():raise ValueError('Each case needs an ID and prompt')
        if case['id'] in ids or len(case['prompt'])>16000:raise ValueError('Duplicate case ID or oversized prompt')
        ids.add(case['id']);rubric=case.get('rubric')
        if not isinstance(rubric,list) or not rubric or any(not isinstance(x,str) or not x.strip() for x in rubric) or len(set(rubric))!=len(rubric):
            raise ValueError('Every case needs distinct human-review rubric checks')
        if type(case.get('min_artifacts',0)) is not int or not 0<=case.get('min_artifacts',0)<=100:
            raise ValueError('Invalid expected artifact count')
        if type(case.get('critical',True)) is not bool:raise ValueError('critical must be boolean')
        from .attachments import validate_attachments
        validate_attachments(case.get('attachments'))
    return suite


def prepare_report(app,suite):
    validate(app);validate_suite(suite)
    baseline=copy.deepcopy(app);baseline['runtime']['api']='responses'
    baseline['runtime'].pop('agents',None)
    return {'schema_version':'1.0','created_at':time.time(),'build':build_info(),
            'app_id':app['id'],'configuration':fingerprint(app),'code_revision':code_revision(),
            'baseline_configuration':fingerprint(baseline),'suite':copy.deepcopy(suite),
            'cases':[{'id':case['id'],'candidate':None,'baseline':None,'review':None} for case in suite['cases']]}


def run_suite(app,suite,execute):
    report=prepare_report(app,suite)
    baseline=copy.deepcopy(app);baseline['runtime']['api']='responses';baseline['runtime'].pop('agents',None)
    for case,row in zip(suite['cases'],report['cases']):
        for name,config in [('baseline',baseline),('candidate',app)]:
            start=time.monotonic()
            try:
                result=execute(copy.deepcopy(config),case['prompt'],copy.deepcopy(case.get('attachments',[])))
                message=result['message']
                # Only the public final answer/receipt is recorded; no reasoning or raw events.
                row[name]={'state':'completed','message':message,'usage':message.get('routing',{}).get('answer_usage',result.get('usage',{}))}
            except Exception:
                row[name]={'state':'failed','error':'Execution failed. Inspect private local run records and provider logs.'}
            row[name]['latency_seconds']=round(time.monotonic()-start,3)
    return report


def release_gate(app,report):
    reasons=[];passed=0
    try:
        if report['schema_version']!='1.0':raise ValueError('Unsupported evaluation report')
        suite=validate_suite(report['suite'])
        if report['configuration']!=fingerprint(app):reasons.append('Application configuration changed; rerun evaluations')
        if report['code_revision']!=code_revision():reasons.append('Runtime code changed; rerun evaluations')
        if [r['id'] for r in report['cases']]!=[c['id'] for c in suite['cases']]:raise ValueError('Report cases do not match the suite')
        for case,row in zip(suite['cases'],report['cases']):
            technical=True
            for label in ('baseline','candidate'):
                result=row.get(label) or {}
                if result.get('state')!='completed' or not result.get('message',{}).get('content'):
                    technical=False
                latency=result.get('latency_seconds')
                if type(latency) not in (int,float) or not math.isfinite(latency) or not 0<=latency<=suite['thresholds']['max_latency_seconds']:
                    technical=False
            artifacts=(row.get('candidate') or {}).get('message',{}).get('artifacts',[])
            if len(artifacts)<case.get('min_artifacts',0):technical=False
            review=row.get('review') or {};checks=review.get('checks') or {}
            reviewed=bool(isinstance(review.get('reviewer'),str) and review['reviewer'].strip() and isinstance(review.get('notes'),str) and review['notes'].strip())
            reviewed=reviewed and set(checks)==set(case['rubric']) and all(type(v) is bool for v in checks.values())
            if not technical:reasons.append(case['id']+': execution, artifact or latency checks failed or unexecuted')
            if not reviewed:reasons.append(case['id']+': complete human rubric review is required')
            success=technical and reviewed and all(checks.values())
            if success:passed+=1
            elif case.get('critical',True):reasons.append(case['id']+': critical acceptance case did not pass')
        rate=passed/len(suite['cases'])
        if rate<suite['thresholds']['min_pass_rate']:reasons.append('Reviewed pass rate is below the agreed threshold')
        return {'approved':not reasons,'status':'approved' if not reasons else 'release_hold','pass_rate':rate,'reasons':reasons}
    except (KeyError,TypeError,ValueError,AttributeError,ZeroDivisionError):
        return {'approved':False,'status':'release_hold','reasons':['Missing or invalid evaluation report']}
