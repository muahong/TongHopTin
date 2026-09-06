from datetime import datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tonghoptin import automation as auto


@pytest.mark.parametrize('hour,trigger,slot', [
    (7,'startup','2026-09-06-am'),(9,'morning','2026-09-06-am'),
    (20,'startup','2026-09-06-am'),(21,'startup','2026-09-06-pm'),
    (21,'evening','2026-09-06-pm'),(22,'morning','2026-09-06-pm'),
    (1,'evening','2026-09-05-pm')])
def test_shared_slots(hour, trigger, slot):
    assert auto.slot_key(datetime(2026,9,6,hour,tzinfo=auto.VN),trigger) == slot


def test_retry_after_push_failure_does_not_recollect_or_rewrite(tmp_path, monkeypatch):
    (tmp_path/'docs').mkdir();(tmp_path/'docs/index.html').write_bytes(b'edition')
    report=tmp_path/'report.json'
    report.write_text(json.dumps({'run_id':'test','articles':[{}],'sources':[],
                                 'start_date':'2026-09-06','end_date':'2026-09-06'}))
    state={'slot':'2026-09-06-am','status':'running'}
    pipeline=auto.Pipeline(tmp_path,tmp_path/'state.json',state)
    calls=[]
    monkeypatch.setattr(pipeline,'command',lambda name,*a,**k: calls.append(name) or 0)
    monkeypatch.setattr(pipeline,'backup',lambda: calls.append('backup'))
    def push(*a):
        calls.append('push');raise RuntimeError('offline')
    monkeypatch.setattr(pipeline,'git_publish',push)
    with pytest.raises(RuntimeError,match='offline'): pipeline.run(resume_report=report)
    assert state['status']=='failed' and not state.get('website_pushed')
    assert calls==['editorial','backup','push']
    monkeypatch.setattr(pipeline,'git_publish',lambda *a: calls.append('push-ok'))
    monkeypatch.setattr(auto,'verify_live',lambda *a: {'verified':True})
    pipeline.run()
    assert calls==['editorial','backup','push','push-ok']
    assert state['status']=='success' and state['live']['verified']


def test_failed_editorial_preserves_evidence_and_never_pushes_site(tmp_path,monkeypatch):
    report=tmp_path/'report.json';report.write_text(json.dumps({'run_id':'t','articles':[{}],'sources':[],
        'start_date':'2026-09-06','end_date':'2026-09-06'}))
    state={'slot':'2026-09-06-am'};p=auto.Pipeline(tmp_path,tmp_path/'state.json',state)
    def fail(*a,**k): raise RuntimeError('editorial failed')
    backup=[];monkeypatch.setattr(p,'command',fail)
    monkeypatch.setattr(p,'backup',lambda: backup.append(True))
    monkeypatch.setattr(p,'git_publish',lambda *a: pytest.fail('must not publish'))
    with pytest.raises(RuntimeError):p.run(resume_report=report)
    assert backup==[True] and state['status']=='failed'


def test_stale_website_is_failure(tmp_path,monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return b'old edition'
    monkeypatch.setattr(auto,'urlopen',lambda *a,**k:Response())
    with pytest.raises(RuntimeError,match='does not match'):
        auto.verify_live(tmp_path,hashlib.sha256(b'new').hexdigest(),timeout=0)


def test_wrong_day_cannot_complete_current_slot(tmp_path,monkeypatch):
    report=tmp_path/'old.json'
    report.write_text(json.dumps({'articles':[{}],'start_date':'2026-09-05','end_date':'2026-09-05'}))
    pipeline=auto.Pipeline(tmp_path,tmp_path/'state.json',{'slot':'2026-09-06-am'})
    monkeypatch.setattr(pipeline,'backup',lambda:None)
    with pytest.raises(RuntimeError,match='dates do not match'):
        pipeline.run(resume_report=report)
    assert pipeline.state['status']=='failed' and not pipeline.state.get('report')


def test_script_entrypoint_without_pythonpath(tmp_path):
    import os,subprocess,sys
    env=dict(os.environ);env.pop('PYTHONPATH',None)
    script = str(auto.ROOT/'scripts/build_editorial.py')
    result=subprocess.run([sys.executable,'-c',
        f'import runpy; runpy.run_path({script!r}); import tonghoptin.editorial'],
        cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0, result.stderr


def test_failed_model_output_is_not_cached(tmp_path,monkeypatch):
    from scripts import build_editorial as builder
    def fail(command,**kwargs):
        Path(command[command.index('--output-last-message')+1]).write_text('{"groups":[]}')
        return SimpleNamespace(returncode=1,stdout='',stderr='failed')
    monkeypatch.setattr(builder.subprocess,'run',fail)
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    with pytest.raises(RuntimeError):builder.infer(tmp_path,'batch','gpt-5.5',builder.GROUP_SCHEMA,'input')
    assert not (tmp_path/'batch.json').exists()


def test_codex_discovered_without_desktop_path(tmp_path,monkeypatch):
    from scripts import build_editorial as builder
    exe=tmp_path/'OpenAI/Codex/bin/version/codex.exe';exe.parent.mkdir(parents=True);exe.touch()
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path));monkeypatch.setattr(builder.shutil,'which',lambda _:None)
    assert builder.codex_executable()==str(exe)


def test_pipeline_lock_blocks_another_process_and_releases(tmp_path):
    import subprocess,sys
    script = ('from pathlib import Path; from tonghoptin.archive import collection_lock; '
              f'lock=collection_lock(Path({str(tmp_path)!r})); lock.__enter__()')
    with auto.collection_lock(tmp_path):
        blocked=subprocess.run([sys.executable,'-c',script],cwd=auto.ROOT,capture_output=True)
        assert blocked.returncode != 0
    released=subprocess.run([sys.executable,'-c',script],cwd=auto.ROOT,capture_output=True)
    assert released.returncode == 0, released.stderr


def test_completed_slot_does_not_invoke_pipeline(tmp_path,monkeypatch):
    folder=tmp_path/'output/automation';folder.mkdir(parents=True)
    key=auto.slot_key(datetime.now(auto.VN),'startup')
    (folder/(key+'.json')).write_text(json.dumps({'status':'success'}))
    monkeypatch.setattr(auto,'ROOT',tmp_path)
    monkeypatch.setattr('sys.argv',['automation','--trigger','startup'])
    monkeypatch.setattr(auto.Pipeline,'run',lambda *a:pytest.fail('duplicate execution'))
    assert auto.main()==0


def test_live_index_and_assets_must_match(tmp_path,monkeypatch):
    body=b'{"content": "articles/run/hash"}<img src="images/abcd.jpg">'
    mapping={'https://chuyenhay.com/?verify='+hashlib.sha256(body).hexdigest()[:16]:body}
    for asset in ['articles/run/hash.json','articles/run/hash.js','images/abcd.jpg']:
        path=tmp_path/'docs'/asset;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'asset')
        mapping['https://chuyenhay.com/'+asset]=b'asset'
    class Response:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return self.data
    monkeypatch.setattr(auto,'urlopen',lambda request,**k:Response(mapping[getattr(request,'full_url',request)]))
    result=auto.verify_live(tmp_path,hashlib.sha256(body).hexdigest(),timeout=0)
    assert len(result['assets_checked'])==3
    mapping['https://chuyenhay.com/articles/run/hash.json']=b'wrong'
    with pytest.raises(RuntimeError,match='asset mismatch'):
        auto.verify_live(tmp_path,hashlib.sha256(body).hexdigest(),timeout=0)
