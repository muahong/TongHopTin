from types import SimpleNamespace
import pytest
from scripts import build_editorial as builder
from tonghoptin.automation import Pipeline


def test_unsupported_model_falls_back_and_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, 'BACKENDS', {'codex':True,'claude':True,'used':set()})
    monkeypatch.setattr(builder, 'codex_executable', lambda:'codex')
    calls=[]
    def rejected(*args, **kwargs):
        calls.append('codex')
        return SimpleNamespace(returncode=1,stdout='',stderr='ERROR: The model is not supported when using Codex with a ChatGPT account.')
    monkeypatch.setattr(builder.subprocess,'run',rejected)
    monkeypatch.setattr(builder,'claude_call',lambda *a: calls.append('claude') or {'groups':[]})
    builder.infer(tmp_path,'one',builder.GROUP_SCHEMA,'input')
    builder.infer(tmp_path,'two',builder.GROUP_SCHEMA,'input')
    assert calls==['codex','claude','claude']
    assert builder.BACKENDS['codex'] is False


def test_other_failures_are_not_silently_reclassified(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    monkeypatch.setattr(builder.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='',stderr='ERROR: Invalid output schema'))
    with pytest.raises(RuntimeError) as error:
        builder.codex_call(tmp_path,'bad',tmp_path/'schema',tmp_path/'pending','input','model','low')
    assert not isinstance(error.value,builder.QuotaExhausted)


def test_malformed_json_retries_once_with_full_input(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'BACKENDS',{'codex':False,'claude':True,'used':set()})
    calls=[]
    def call(folder,name,schema,prompt,model):
        calls.append((name,prompt,model))
        if len(calls)==1:raise ValueError('truncated JSON')
        return {'groups':[]}
    monkeypatch.setattr(builder,'claude_call',call)
    assert builder.infer(tmp_path,'batch',builder.GROUP_SCHEMA,'full source input')=={'groups':[]}
    assert len(calls)==2 and calls[1][0]=='batch-json-retry'
    assert 'full source input' in calls[1][1] and calls[1][2]==builder.POLISH[2]
    assert (tmp_path/'batch.json').exists()


def test_invalid_retry_is_not_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(builder,'BACKENDS',{'codex':False,'claude':True,'used':set()})
    calls=[]
    def fail(*args):calls.append(True);raise ValueError('invalid JSON')
    monkeypatch.setattr(builder,'claude_call',fail)
    with pytest.raises(ValueError):builder.infer(tmp_path,'batch',builder.GROUP_SCHEMA,'input')
    assert len(calls)==2 and not (tmp_path/'batch.json').exists()


def test_recovered_editorial_is_backed_up_after_crawl_only_backup(tmp_path,monkeypatch):
    (tmp_path/'docs').mkdir();(tmp_path/'docs/index.html').write_text('edited')
    state={'report':'frozen.json','archive_done':True,'status':'failed'}
    pipeline=Pipeline(tmp_path,tmp_path/'state.json',state)
    calls=[]
    monkeypatch.setattr(pipeline,'command',lambda *a,**k:calls.append('editorial'))
    monkeypatch.setattr(pipeline,'backup',lambda:calls.append('backup'))
    def stop_before_push(*a):
        calls.append('push');raise RuntimeError('stop')
    monkeypatch.setattr(pipeline,'git_publish',stop_before_push)
    with pytest.raises(RuntimeError):pipeline.run()
    assert calls==['editorial','backup','push']


@pytest.mark.parametrize("structured", [True, False])
def test_claude_requires_native_structured_output(tmp_path, monkeypatch, structured):
    import json
    monkeypatch.setattr(builder, 'claude_executable', lambda: 'claude')
    def run(command, **kwargs):
        assert json.loads(command[command.index('--json-schema')+1]) == builder.GROUP_SCHEMA
        envelope = {'result': 'malformed prose', 'is_error': False}
        if structured: envelope['structured_output'] = {'groups': []}
        return SimpleNamespace(returncode=0, stdout=json.dumps(envelope), stderr='')
    monkeypatch.setattr(builder.subprocess, 'run', run)
    if structured:
        assert builder.claude_call(tmp_path, 'batch', builder.GROUP_SCHEMA, 'input', 'sonnet') == {'groups': []}
    else:
        with pytest.raises(ValueError):
            builder.claude_call(tmp_path, 'batch', builder.GROUP_SCHEMA, 'input', 'sonnet')
