import copy
import json
from datetime import datetime
import pytest
from tonghoptin.models import Article
from tonghoptin.editorial import article_fingerprint,validate_edition,load_edition
from tonghoptin.overview import build_overview


def fixture():
    articles=[Article(url='https://example.vn/'+str(i),title='Tin '+str(i),source_site='example.vn',source_category='Kinh tế',published_date=datetime(2026,9,5),content_text='Dữ kiện '+str(i),content_html='<p>Dữ kiện</p>') for i in range(2)]
    ids=[a.url_hash for a in articles]
    edition={'day':'2026-09-05','fingerprint':article_fingerprint(articles),'created_at':'2026-09-05','method':'codex-cli-chatgpt','group_model':'gpt-5.5','rewrite_model':'gpt-5.4-mini','source_count':2,'stories':[{'id':'edition-test','category':'economy','title':'Bản tổng hợp','brief':'Hai nguồn, một sự kiện.','articles':ids,'paragraphs':[{'text':'Thông tin đã biên tập.','sources':ids}]}]}
    return articles,edition


def test_edition_covers_sources_and_citations():
    articles,edition=fixture();validate_edition(edition,articles)
    for mutate in ('missing','duplicate','foreign_citation','uncited','empty','wrong_day','stale'):
        bad=copy.deepcopy(edition)
        if mutate=='missing':bad['stories'][0]['articles'].pop()
        if mutate=='duplicate':bad['stories'][0]['articles'].append(articles[0].url_hash)
        if mutate=='foreign_citation':bad['stories'][0]['paragraphs'][0]['sources'].append('unknown')
        if mutate=='uncited':bad['stories'][0]['paragraphs'][0]['sources'].pop()
        if mutate=='empty':bad['stories'][0]['brief']=''
        if mutate=='wrong_day':bad['day']='2026-09-04'
        if mutate=='stale':bad['fingerprint']='stale'
        with pytest.raises(ValueError):validate_edition(bad,articles)


def test_overview_loads_only_matching_edition(tmp_path,monkeypatch):
    import tonghoptin.editorial as module
    monkeypatch.setattr(module,'EDITION_ROOT',tmp_path)
    articles,edition=fixture();path=tmp_path/edition['day']/(edition['fingerprint']+'.json');path.parent.mkdir();path.write_text(json.dumps(edition),encoding='utf-8')
    result=build_overview(articles)
    assert result['days']['2026-09-05']['economy'][0]['title']=='Bản tổng hợp'
    assert result['editorial']['2026-09-05']['method']=='codex-cli-chatgpt'
    articles[0].content_text+=' Changed'
    assert load_edition(articles) is None
    assert not build_overview(articles)['editorial']


def test_fingerprint_order_independent_and_entity_normalized():
    articles,_=fixture();articles[0].title='Tin &amp; bài'
    fingerprint=article_fingerprint(articles)
    articles[0].title='Tin & bài'
    assert article_fingerprint(list(reversed(articles)))==fingerprint

def test_cli_uses_chatgpt_without_api_environment(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import scripts.build_editorial as builder
    monkeypatch.setenv('OPENAI_API_KEY','must-not-be-used')
    monkeypatch.setenv('OPENAI_BASE_URL','https://example.invalid')
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        assert '--ignore-user-config' in command
        assert 'forced_login_method="chatgpt"' in command
        assert 'OPENAI_API_KEY' not in kwargs['env']
        assert 'OPENAI_BASE_URL' not in kwargs['env']
        output=command[command.index('--output-last-message')+1]
        from pathlib import Path
        Path(output).write_text('{"groups":[]}',encoding='utf-8')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(builder.subprocess,'run',run)
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    builder.infer(tmp_path,'batch','gpt-5.5',builder.GROUP_SCHEMA,'input')
    builder.infer(tmp_path,'batch','gpt-5.5',builder.GROUP_SCHEMA,'input')
    assert len(calls)==1

def test_publish_retries_transient_index_lock(tmp_path,monkeypatch):
    from pathlib import Path
    from tonghoptin.cli import _publish_to_docs
    monkeypatch.chdir(tmp_path)
    root=tmp_path/'output';root.mkdir();html=root/'digest.html';html.write_text('new')
    docs=tmp_path/'docs';docs.mkdir();(docs/'index.html').write_text('old')
    real_replace=Path.replace;calls=[]
    def transient(path,target):
        calls.append(target)
        if len(calls)==1:
            assert (docs/'index.html').read_text()=='old'
            raise PermissionError('temporary reader lock')
        return real_replace(path,target)
    monkeypatch.setattr(Path,'replace',transient)
    monkeypatch.setattr('time.sleep',lambda _:None)
    _publish_to_docs(html,root,[])
    assert len(calls)==2
    assert (docs/'index.html').read_text()=='new'
