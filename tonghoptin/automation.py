"""Resumable local publication; scheduler success means the website was verified."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from urllib.request import Request, urlopen
from tonghoptin.archive import collection_lock

ROOT = Path(__file__).resolve().parents[1]
VN = timezone(timedelta(hours=7))


def slot_key(now, trigger):
    now = now.astimezone(VN)
    period = 'pm' if now.hour >= 21 else 'am'
    if trigger == 'evening' and now.hour < 9:
        return (now.date() - timedelta(days=1)).isoformat() + '-pm'
    return now.date().isoformat() + '-' + period


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class Pipeline:
    def __init__(self, root, state_path, state):
        self.root, self.state_path, self.state = root, state_path, state
        self.folder = state_path.parent / state_path.stem
        self.folder.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
                        GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')

    def persist(self):
        save(self.state_path, self.state)

    def command(self, name, args, timeout=1800, cwd=None, allowed=(0,)):
        log = self.folder / (name + '.log')
        started = time.monotonic()
        self.state['current_step'] = name
        self.persist()
        with log.open('ab') as stream:
            stream.write(('\n' + datetime.now(VN).isoformat() + '\n').encode())
            stream.flush()
            process = subprocess.Popen(args, cwd=cwd or self.root, env=self.env,
                                       stdout=stream, stderr=subprocess.STDOUT)
            try:
                rc = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   capture_output=True, timeout=30)
                else:
                    process.kill()
                process.wait()
                raise RuntimeError(f'{name} timed out; see {log}')
        self.state.setdefault('steps', []).append({'step': name, 'returncode': rc,
             'seconds': round(time.monotonic()-started, 2), 'log': str(log)})
        self.persist()
        if rc not in allowed:
            raise RuntimeError(f'{name} failed ({rc}); see {log}')
        return rc

    def git_publish(self, name, cwd, paths, message):
        self.command(name+'-add', ['git', 'add', '--', *paths], cwd=cwd)
        changed = self.command(name+'-diff', ['git','diff','--cached','--quiet','--',*paths],
                               cwd=cwd, allowed=(0, 1))
        if changed:
            self.command(name+'-commit', ['git','commit','--only','-m',message,'--',*paths], cwd=cwd)
        self.command(name+'-push', ['git','push'], cwd=cwd, timeout=1800)

    def backup(self):
        if not (self.root/'archive/.git').exists():
            raise RuntimeError('Private archive checkout missing')
        self.command('backup', [sys.executable,'-m','tonghoptin.cli','backup'])
        self.git_publish('archive', self.root/'archive',
                         ['packs','manifests','index','index.json','README.md'], 'Preserve crawl history')

    def run(self, collect_args=(), resume_report=None):
        try:
            if not self.state.get('report'):
                if resume_report:
                    report_path = resume_report.resolve()
                else:
                    before = set((self.root/'output/runs').glob('*.json'))
                    date_args = ['--date', self.state['slot'][:10]] if not self.state['slot'].startswith('manual-') else []
                    self.command('collect', [sys.executable,'-m','tonghoptin.cli','collect',*date_args,*collect_args])
                    reports = set((self.root/'output/runs').glob('*.json')) - before
                    if len(reports) != 1:
                        raise RuntimeError('Expected exactly one new crawl report')
                    report_path = reports.pop()
                report = json.loads(report_path.read_text(encoding='utf-8'))
                if not report['articles']:
                    raise RuntimeError('Empty crawl cannot be published')
                if not self.state['slot'].startswith('manual-'):
                    day = self.state['slot'][:10]
                    if report.get('start_date') != day or report.get('end_date') != day:
                        raise RuntimeError('Crawl dates do not match the scheduled slot')
                self.state.update(report=str(report_path), run_id=report['run_id'],
                    article_count=len(report['articles']), coverage=[{k:r[k] for k in
                    ('site_name','status','articles_count','errors_count')} for r in report['sources']])
                self.persist()
            if not self.state.get('editorial_done'):
                self.command('editorial', [sys.executable,'scripts/build_editorial.py',
                             self.state['report'],'--publish'], timeout=10800)
                self.state['editorial_done'] = True
                self.state['index_sha256'] = hashlib.sha256((self.root/'docs/index.html').read_bytes()).hexdigest()
                self.persist()
            if not self.state.get('archive_done'):
                self.backup()
                self.state['archive_done'] = True
                self.persist()
            if not self.state.get('website_pushed'):
                actual = hashlib.sha256((self.root/'docs/index.html').read_bytes()).hexdigest()
                if actual != self.state['index_sha256']:
                    self.command('restore-edition', [sys.executable,'scripts/build_editorial.py',
                                 self.state['report'],'--publish'])
                    self.state['index_sha256'] = hashlib.sha256((self.root/'docs/index.html').read_bytes()).hexdigest()
                    self.backup()
                self.git_publish('website', self.root, ['docs','editorial'], 'Update daily news reader')
                self.state['website_pushed'] = True
                self.persist()
            self.state['current_step'] = 'verify-live'
            # Git normalizes generated Windows CRLF text to LF. Verify the exact
            # bytes committed for Pages, not the checkout's newline convention.
            commit = self.state.get('website_commit') or subprocess.check_output(
                ['git','rev-parse','HEAD'], cwd=self.root, timeout=30).decode().strip()
            self.state['website_commit'] = commit
            self.state['published_sha256'] = hashlib.sha256(
                published_file(self.root, commit, 'index.html')).hexdigest()
            self.persist()
            self.state['live'] = verify_live(self.root, self.state['published_sha256'], commit=commit)
            self.state.update(status='success', completed_at=datetime.now(VN).isoformat())
            self.state.pop('error', None)
            self.persist()
        except Exception as exc:
            failed_step = self.state.get('current_step')
            self.state.update(status='failed', error=str(exc), failed_step=failed_step,
                              failed_at=datetime.now(VN).isoformat())
            self.persist()
            if not self.state.get('archive_done') and not str(failed_step).startswith(('archive','backup')):
                try:
                    self.backup()
                except Exception as backup_exc:
                    self.state['backup_error'] = str(backup_exc)
            self.state['current_step'] = failed_step
            self.persist()
            raise


def published_file(root, commit, asset):
    return subprocess.check_output(['git','show',f'{commit}:docs/{asset}'], cwd=root, timeout=30)


def verify_live(root, expected_hash, timeout=600, commit=None):
    deadline = time.monotonic() + timeout
    url = 'https://chuyenhay.com/'
    while True:
        try:
            request = Request(url+'?verify='+expected_hash[:16], headers={'Cache-Control':'no-cache'})
            with urlopen(request, timeout=30) as response:
                body = response.read()
            if hashlib.sha256(body).hexdigest() != expected_hash:
                raise ValueError('Live index does not match the generated edition yet')
            import re
            html = body.decode('utf-8')
            content = re.search(r'"content"\s*:\s*"(articles/[\w/-]+)"', html)
            if not content:
                raise ValueError('Published index has no article body sidecar')
            assets = [content.group(1)+'.json', content.group(1)+'.js']
            hero = re.search(r'images/[a-f0-9]+\.jpg', html)
            if hero:
                assets.append(hero.group())
            for asset in assets:
                with urlopen(url+asset, timeout=30) as response:
                    data = response.read()
                expected = published_file(root, commit, asset) if commit else (root/'docs'/asset).read_bytes()
                if data != expected:
                    raise ValueError('Live asset mismatch: '+asset)
            return {'url':url, 'sha256':expected_hash, 'assets_checked':assets,
                    'verified_at':datetime.now(VN).isoformat()}
        except Exception as exc:
            last = str(exc)
        if time.monotonic() >= deadline:
            raise RuntimeError('Website verification failed: '+last)
        time.sleep(15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trigger', choices=['morning','evening','startup','manual'], default='manual')
    parser.add_argument('--resume-report', type=Path)
    parser.add_argument('--check', action='store_true', help='Read slot/state only; no collection or publication')
    args, collect_args = parser.parse_known_args()
    os.chdir(ROOT)
    now = datetime.now(VN)
    key = slot_key(now, args.trigger) if args.trigger != 'manual' else now.strftime('manual-%Y%m%d-%H%M%S-%f')
    folder = ROOT/'output/automation'
    folder.mkdir(parents=True, exist_ok=True)
    state_path = folder/(key+'.json')
    if args.check:
        print(json.dumps({'slot':key,'state':json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None}))
        return 0
    try:
        with collection_lock(folder):
            state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
                'slot':key,'trigger':args.trigger,'started_at':now.isoformat(),'status':'running'}
            if state['status'] == 'success':
                print('Already verified: '+key)
                return 0
            state['status'] = 'running'
            state['attempts'] = state.get('attempts',0)+1
            pipeline = Pipeline(ROOT, state_path, state)
            pipeline.persist()
            pipeline.run(collect_args, args.resume_report)
            print('Published and verified: '+key)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
