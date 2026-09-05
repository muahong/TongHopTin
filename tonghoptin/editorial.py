"""Load only editorial editions matching the exact source content and day."""
import hashlib
import json
from pathlib import Path

EDITION_ROOT=Path(__file__).resolve().parents[1]/'editorial'

def article_fingerprint(articles):
    from tonghoptin.overview import plain_text
    rows=sorted((a.url_hash,plain_text(a.title),a.content_text,a.published_date.isoformat()) for a in articles)
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def validate_edition(edition,articles):
    expected={a.url_hash for a in articles}
    if edition['fingerprint']!=article_fingerprint(articles):raise ValueError('Stale editorial source fingerprint')
    if {a.published_date.date().isoformat() for a in articles}!={edition['day']}:raise ValueError('Editorial date mismatch')
    members=[i for s in edition['stories'] for i in s['articles']]
    if len(members)!=len(expected) or set(members)!=expected:raise ValueError('Editorial article coverage mismatch')
    from tonghoptin.overview import CATEGORIES
    allowed={c[0] for c in CATEGORIES}
    seen=set()
    for story in edition['stories']:
        if story['id'] in seen:raise ValueError('Duplicate editorial story ID')
        seen.add(story['id'])
        if story['category'] not in allowed:raise ValueError('Invalid category')
        if not story['title'].strip() or not story['brief'].strip() or not story['paragraphs']:raise ValueError('Empty editorial copy')
        cited=set()
        for p in story['paragraphs']:
            if not p['text'].strip() or not p['sources'] or not set(p['sources'])<=set(story['articles']):raise ValueError('Invalid paragraph provenance')
            cited.update(p['sources'])
        if cited!=set(story['articles']):raise ValueError('Uncited source article')

def load_edition(articles):
    if not articles:return None
    fingerprint=article_fingerprint(articles)
    path=EDITION_ROOT/articles[0].published_date.date().isoformat()/(fingerprint+'.json')
    if not path.exists():return None
    edition=json.loads(path.read_text(encoding='utf-8'));validate_edition(edition,articles)
    return edition
