"""Explicit, conservative configuration for the optional managed runtime."""
import re

DEFAULTS = {'environment':'openai_hosted', 'network_access':'disabled', 'review':'auto_review',
            'tool_policy':'read_only', 'max_run_seconds':300, 'max_application_tool_calls':12,
            'artifact_retention_days':7}
SDK_REQUIREMENT = 'openai==3.13.0'


def validate_agents_config(runtime):
    model=runtime.get('model')
    if (not isinstance(model,str) or model.lower() in ('auto','default') or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',model) or runtime.get('routing')):
        raise ValueError('Agents requires an explicit fixed model; Auto and server defaults are not supported')
    supplied=runtime.get('agents',{})
    if not isinstance(supplied,dict) or set(supplied)-set(DEFAULTS):
        raise ValueError('Unsupported Agents settings; credentials, network overrides and custom environments are not accepted')
    settings={**DEFAULTS,**supplied}
    if settings['environment'] not in ('openai_hosted','none'):
        raise ValueError('Agents environment must be openai_hosted or none')
    for key in ('network_access','review','tool_policy'):
        if settings[key]!=DEFAULTS[key]:
            raise ValueError('Agents requires disabled sandbox network, auto_review and read_only business tools')
    for key,low,high in (('max_run_seconds',10,3600),('max_application_tool_calls',1,100),('artifact_retention_days',1,365)):
        value=settings[key]
        if type(value) is not int or not low<=value<=high:
            raise ValueError(f'Invalid Agents {key}; use {low}–{high}')
    return settings


def compatibility_issues(app):
    runtime=app['runtime'];settings=validate_agents_config(runtime);issues=[]
    for tool in runtime.get('hosted_tools',[]):
        if tool not in ('web_search','code_interpreter'):
            issues.append(('agents_tool_unsupported',f'Agents adapter does not support {tool}; choose Responses or remove that capability explicitly.'))
        elif tool=='code_interpreter' and settings['environment']=='none':
            issues.append(('agents_workspace_required','Data analysis requires an OpenAI-hosted workspace.'))
    if runtime.get('output_schema'):
        issues.append(('agents_schema_unsupported','Strict output schemas require the Responses runtime in this release.'))
    return [{'severity':'blocker','code':code,'message':message} for code,message in issues]
