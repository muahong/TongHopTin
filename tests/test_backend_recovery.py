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
