import copy
import json
from pathlib import Path
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
    monkeypatch.setitem(builder.BACKENDS,'codex',True)
    builder.infer(tmp_path,'batch',builder.GROUP_SCHEMA,'input')
    builder.infer(tmp_path,'batch',builder.GROUP_SCHEMA,'input')
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


def news(count):
    return [Article(url='https://example.vn/'+str(i),title='Tin '+str(i),source_site='example.vn',
                    source_category='Kinh tế',published_date=datetime(2026,9,5),
                    content_text='Dữ kiện '+str(i)+' '+'x'*500,content_html='<p>x</p>') for i in range(count)]


def sloppy_model(name,prompt):
    """The answers that broke production: a third of the IDs duplicated into an
    extra group and the first article dropped entirely."""
    payload=json.loads(prompt[prompt.index('{"categories"'):])
    ids=[a['id'] for a in payload['articles']]
    if name.endswith('-repair'):
        return {'assignments':[{'article':i,'group':0,'category':'economy','topic':'Sửa'} for i in sorted(ids)]}
    groups=[{'category':'economy','topic':'Chủ đề '+str(i),'articles':[i]} for i in ids[1:]]
    groups.append({'category':'economy','topic':'Lặp','articles':ids[::3]})
    return {'groups':groups}


def test_grouping_batches_are_bounded_and_still_cover_every_article(tmp_path,monkeypatch):
    """A whole Vietnam day used to leave as one prompt; it overflowed the model
    context, came back with duplicated and missing IDs, and the repair prompt was
    then larger than the answer it repaired."""
    import scripts.build_editorial as builder
    articles=news(900)
    titles=[a.title for a in articles]
    index=[{'id':i,'title':a.title,'source':a.source_site,'lead':a.content_text[:300]} for i,a in enumerate(articles)]
    batches=builder.pack(index,builder.GROUP_BATCH_CHARS,builder.GROUP_BATCH_ARTICLES)
    assert len(batches)>1
    sizes=[]
    def fake(folder,name,schema,prompt,tier=None,check=None):
        sizes.append(len(prompt))
        value=sloppy_model(name,prompt)
        if check:check(value)
        return value
    monkeypatch.setattr(builder,'infer',fake)
    covered=[]
    for n,batch in enumerate(batches):
        covered.extend(i for g in builder.group_batch(tmp_path,f'groups-{n:03}',[],batch,titles) for i in g['articles'])
    assert sorted(covered)==list(range(len(articles)))
    # Every prompt, repairs included, stays a small multiple of one batch.
    assert max(sizes)<3*builder.GROUP_BATCH_CHARS


def test_merge_only_unions_named_groups_and_respects_the_size_cap(tmp_path,monkeypatch):
    import scripts.build_editorial as builder
    groups=[{'category':'economy','topic':'A','articles':[0,1]},
            {'category':'economy','topic':'A lặp','articles':[2]},
            {'category':'economy','topic':'B','articles':[3]},
            {'category':'economy','topic':'C','articles':list(range(4,4+builder.GROUP_LIMIT))}]
    monkeypatch.setattr(builder,'infer',lambda *a,**k:{'merges':[{'groups':[0,1]},{'groups':[0,3]},{'groups':[99]}]})
    merged=builder.merge_groups(tmp_path,'merge-economy',groups,['Tin '+str(i) for i in range(40)])
    assert sorted(sorted(g['articles']) for g in merged)==[[0,1,2],[3],list(range(4,4+builder.GROUP_LIMIT))]


def test_codex_failure_reports_the_cli_reason(tmp_path,monkeypatch):
    """A refusal must reach the automation state, not just a log path."""
    import scripts.build_editorial as builder
    from types import SimpleNamespace
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    monkeypatch.setitem(builder.BACKENDS,'codex',True)
    monkeypatch.setattr(builder.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,
        stdout='long transcript',stderr='ERROR: Codex ran out of room in the context window.'))
    with pytest.raises(RuntimeError,match='out of room'):
        builder.infer(tmp_path,'groups-000',builder.GROUP_SCHEMA,'prompt')


def test_spent_codex_quota_falls_back_to_the_anthropic_subscription(tmp_path,monkeypatch):
    """A spent ChatGPT plan blocked the whole day's edition for hours."""
    import scripts.build_editorial as builder
    from types import SimpleNamespace
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    monkeypatch.setattr(builder,'claude_executable',lambda:'claude')
    monkeypatch.setitem(builder.BACKENDS,'codex',True)
    monkeypatch.setitem(builder.BACKENDS,'claude',True)
    monkeypatch.setenv('ANTHROPIC_API_KEY','must-not-be-used')
    monkeypatch.setenv('ANTHROPIC_BASE_URL','https://example.invalid')
    seen=[]
    def run(command,**kwargs):
        seen.append(command)
        if command[0]=='codex':
            return SimpleNamespace(returncode=1,stdout='',
                stderr="ERROR: You've hit your usage limit. Try again at 9:21 PM.")
        assert '--tools' in command and command[command.index('--tools')+1]==''
        assert '--strict-mcp-config' in command
        assert 'ANTHROPIC_API_KEY' not in kwargs['env']
        assert 'ANTHROPIC_BASE_URL' not in kwargs['env']
        assert 'usage limit' not in kwargs['input']
        return SimpleNamespace(returncode=0,stderr='',stdout=json.dumps(
            {'is_error':False,'result':'Here you go:\n```json\n{"groups":[{"category":"economy",'
                                       '"topic":"Vàng","articles":[0]}]}\n```'}))
    monkeypatch.setattr(builder.subprocess,'run',run)
    value=builder.infer(tmp_path,'groups-000',builder.GROUP_SCHEMA,'prompt')
    assert value['groups'][0]['articles']==[0]
    assert [c[0] for c in seen]==['codex','claude']
    assert json.loads((tmp_path/'groups-000.json').read_text(encoding='utf-8'))==value


def test_spent_quota_without_a_second_plan_says_how_to_sign_in(tmp_path,monkeypatch):
    import scripts.build_editorial as builder
    from types import SimpleNamespace
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    monkeypatch.setitem(builder.BACKENDS,'codex',True)
    monkeypatch.setitem(builder.BACKENDS,'claude',False)
    monkeypatch.setattr(builder.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,
        stdout='',stderr="ERROR: You've hit your usage limit. Try again at 9:21 PM."))
    with pytest.raises(RuntimeError,match='claude setup-token'):
        builder.infer(tmp_path,'groups-000',builder.GROUP_SCHEMA,'prompt')
    assert not (tmp_path/'groups-000.json').exists()


def test_default_tier_is_the_cheapest_and_prose_gets_more():
    import scripts.build_editorial as builder
    import inspect
    assert inspect.signature(builder.infer).parameters['tier'].default==builder.FAST
    assert builder.FAST==('gpt-5.4-mini','low','haiku')
    assert builder.POLISH[0]=='gpt-5.5' and builder.POLISH[1]=='medium'
    source=inspect.getsource(builder)
    # Grouping, repair and merging must not name a model at the call site.
    assert "GROUP_SCHEMA,RULES+GROUP_RULES" in source and "'gpt-5.5',GROUP_SCHEMA" not in source


def test_unauthenticated_claude_cli_is_not_a_backend(tmp_path,monkeypatch):
    import scripts.build_editorial as builder
    from types import SimpleNamespace
    monkeypatch.setattr(builder,'claude_executable',lambda:'claude')
    monkeypatch.setattr(builder.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,
        stdout='{"loggedIn": false, "authMethod": "none"}',stderr=''))
    assert builder.claude_signed_in() is False
    monkeypatch.setattr(builder.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,
        stdout='{"loggedIn": true, "authMethod": "subscription"}',stderr=''))
    assert builder.claude_signed_in() is True


def test_oversized_group_is_split_before_it_reaches_the_rewriting_prompt():
    import scripts.build_editorial as builder
    groups=[{'category':'economy','topic':'To','articles':list(range(40))},
            {'category':'world','topic':'Vừa','articles':[40,41]}]
    capped=builder.enforce_group_limit(groups)
    assert [len(g['articles']) for g in capped]==[16,16,8,2]
    assert sorted(i for g in capped for i in g['articles'])==list(range(42))
    assert [g['category'] for g in capped]==['economy']*3+['world']


def test_stray_ids_are_dropped_instead_of_losing_the_edition(tmp_path,monkeypatch):
    """haiku cited nine articles from outside the batch and aborted the whole day."""
    import scripts.build_editorial as builder
    batch=[{'id':i,'title':'Tin '+str(i),'source':'example.vn','lead':'x'} for i in range(10)]
    titles=['Tin '+str(i) for i in range(40)]
    def fake(folder,name,schema,prompt,tier=None,check=None):
        if name.endswith('-repair'):
            payload=json.loads(prompt[prompt.index('{"categories"'):])
            value={'assignments':[{'article':a['id'],'group':0,'category':'economy','topic':'Sửa'}
                                  for a in payload['articles']]}
        else:
            value={'groups':[{'category':'economy','topic':'A','articles':[0,1,999]},
                             {'category':'economy','topic':'B','articles':[2,3,1234]}]}
        if check:check(value)
        return value
    monkeypatch.setattr(builder,'infer',fake)
    grouped=builder.group_batch(tmp_path,'groups-003',[],batch,titles)
    covered=sorted(i for g in grouped for i in g['articles'])
    assert covered==list(range(10))
    assert 999 not in covered and 1234 not in covered


def test_unusable_cached_answer_is_discarded_not_replayed(tmp_path,monkeypatch):
    """The bad answer was schema-valid, so it cached and failed identically for hours."""
    import scripts.build_editorial as builder
    from types import SimpleNamespace
    cached=tmp_path/'groups-003.json';cached.write_text('{"groups":[{"articles":[999]}]}',encoding='utf-8')
    def reject(value):
        if value['groups'][0]['articles']!=[0]:raise ValueError('Unknown source IDs')
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    monkeypatch.setitem(builder.BACKENDS,'codex',True)
    def run(command,**kwargs):
        Path(command[command.index('--output-last-message')+1]).write_text(
            '{"groups":[{"articles":[0]}]}',encoding='utf-8')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(builder.subprocess,'run',run)
    value=builder.infer(tmp_path,'groups-003',builder.GROUP_SCHEMA,'prompt',check=reject)
    assert value['groups'][0]['articles']==[0]
    assert json.loads(cached.read_text(encoding='utf-8'))==value


def test_answer_failing_validation_is_never_cached(tmp_path,monkeypatch):
    import scripts.build_editorial as builder
    from types import SimpleNamespace
    monkeypatch.setattr(builder,'codex_executable',lambda:'codex')
    monkeypatch.setitem(builder.BACKENDS,'codex',True)
    def run(command,**kwargs):
        Path(command[command.index('--output-last-message')+1]).write_text(
            '{"groups":[{"articles":[999]}]}',encoding='utf-8')
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(builder.subprocess,'run',run)
    def reject(value):raise ValueError('Invalid repaired coverage')
    with pytest.raises(ValueError):
        builder.infer(tmp_path,'groups-004',builder.GROUP_SCHEMA,'prompt',check=reject)
    assert not (tmp_path/'groups-004.json').exists()


def test_partial_repair_still_covers_the_batch(tmp_path,monkeypatch):
    """Demanding an exact repair lost a 2,277-article day to one skipped ID."""
    import scripts.build_editorial as builder
    batch=[{'id':i,'title':'Tin '+str(i),'source':'example.vn','lead':'x'} for i in range(10)]
    titles=['Tin '+str(i) for i in range(10)]
    def fake(folder,name,schema,prompt,tier=None,check=None):
        if name.endswith('-repair'):
            # Places 4 of the 6 ambiguous articles, invents a category, skips two.
            value={'assignments':[{'article':4,'group':0,'category':'economy','topic':'A'},
                                  {'article':5,'group':-1,'category':'nonsense','topic':'B'},
                                  {'article':6,'group':99,'category':'world','topic':'C'},
                                  {'article':7,'group':0,'category':'economy','topic':'D'},
                                  {'article':4,'group':1,'category':'economy','topic':'dup'},
                                  {'article':555,'group':0,'category':'economy','topic':'alien'}]}
        else:
            value={'groups':[{'category':'economy','topic':'A','articles':[0,1]},
                             {'category':'economy','topic':'B','articles':[2,3]}]}
        if check:check(value)
        return value
    monkeypatch.setattr(builder,'infer',fake)
    grouped=builder.group_batch(tmp_path,'groups-006',[{'id':'economy','name':'Kinh tế'},
                                {'id':'world','name':'Thế giới'}],batch,titles,'society')
    assert sorted(i for g in grouped for i in g['articles'])==list(range(10))
    assert all(g['category'] in {'economy','world','society'} for g in grouped)
    # The two the repair skipped survive as their own stories, not as a failure.
    solo={tuple(g['articles']):g for g in grouped if len(g['articles'])==1}
    assert (8,) in solo and (9,) in solo
    assert solo[(8,)]['category']=='society'


def test_a_useless_repair_is_rejected_rather_than_cached(tmp_path,monkeypatch):
    import scripts.build_editorial as builder
    batch=[{'id':i,'title':'Tin '+str(i),'source':'example.vn','lead':'x'} for i in range(10)]
    titles=['Tin '+str(i) for i in range(10)]
    def fake(folder,name,schema,prompt,tier=None,check=None):
        value={'assignments':[]} if name.endswith('-repair') else {'groups':[
            {'category':'economy','topic':'A','articles':[0,1]}]}
        if check:check(value)
        return value
    monkeypatch.setattr(builder,'infer',fake)
    with pytest.raises(ValueError,match='too little'):
        builder.group_batch(tmp_path,'groups-006',[],batch,titles,'society')
