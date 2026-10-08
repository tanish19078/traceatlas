"""TraceAtlas: dependency-free, evidence-preserving Norwegian registry baseline."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import html
import json
import math
import os
import tempfile
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = '0.2.0'
BASE = 'https://data.brreg.no/enhetsregisteret/api/enheter/'
STATES = {'available', 'not_available', 'blocked', 'not_applicable', 'ambiguous', 'failed'}
FIELDS = {
    'legal_name': 'navn', 'legal_form': 'organisasjonsform',
    'registered_address': 'forretningsadresse', 'industry': 'naeringskode1',
    'registered_at': 'registreringsdatoEnhetsregisteret',
    'business_activity': 'aktivitet', 'bankrupt': 'konkurs',
    'in_liquidation': 'underAvvikling',
}
EXTERNAL = ['website_identity', 'leadership', 'locations', 'financials', 'jobs', 'news']


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def valid_org(number):
    if not isinstance(number, str) or len(number) != 9 or not number.isascii() or not number.isdigit():
        return False
    remainder = 11 - sum(int(n)*w for n, w in zip(number[:8], [3,2,7,6,5,4,3,2])) % 11
    return remainder != 10 and (0 if remainder == 11 else remainder) == int(number[-1])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(number, timeout=12):
    """Only a fixed public API host, no arbitrary URLs or redirects."""
    request = urllib.request.Request(BASE + number, headers={
        'User-Agent': 'TraceAtlas/0.1 (company research; https://github.com/tanish19078/traceatlas)',
        'Accept': 'application/json',
    })
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('response_size_limit')
        return body


def envelope(number, state='failed', message=None):
    return {'schema_version': '0.1', 'organisation_number': number,
            'state': state, 'legal_identity': {}, 'claims': [], 'evidence': [],
            'availability': {}, 'candidates': [], 'errors': [message] if message else [],
            'refresh': {'checked_at': now(), 'changes': []},
            'summary': 'Research unavailable.', 'source_mode': None}


def research(number, fixture_dir=None, timeout=12):
    result = envelope(number)
    if not valid_org(number):
        result['errors'] = ['invalid_organisation_number']
        return result, None
    fetched_at = now()
    try:
        if fixture_dir:
            body = (Path(fixture_dir) / (number + '.json')).read_bytes()
        else:
            body = fetch(number, timeout)
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError('expected_registry_object')
        if data.get('organisasjonsnummer') != number:
            result['state'] = 'ambiguous'
            result['errors'] = ['registry_identity_mismatch']
            return result, None
        if not isinstance(data.get('navn'), str) or not data['navn'].strip():
            raise ValueError('missing_legal_name')
        snapshot = digest(body)
        result['state'] = 'available'
        result['source_mode'] = 'fixture' if fixture_dir else 'live'
        result['legal_identity'] = {'organisation_number': number, 'name': data['navn']}
        result['errors'] = []
        evidence = {'id': snapshot, 'source_url': BASE + number,
                    'retrieved_at': fetched_at, 'content_sha256': snapshot,
                    'snapshot_path': 'snapshots/' + snapshot + '.json',
                    'source_class': 'official_registry', 'extractor_version': VERSION,
                    'synthetic': bool(fixture_dir)}
        result['evidence'].append(evidence)
        fields = dict(FIELDS)
        if data.get('harRegistrertAntallAnsatte') is True:
            fields['registered_employees'] = 'antallAnsatte'
        else:
            result['availability']['registered_employees'] = {
                'state': 'not_available', 'reason': 'registry_does_not_confirm_employee_count'}
        for field, key in fields.items():
            value = data.get(key)
            if value is None or value == '' or value == [] or value == {}:
                result['availability'][field] = {'state': 'not_available', 'reason': 'absent_in_registry_response'}
                continue
            if field == 'registered_employees' and (type(value) is not int or value < 0):
                raise ValueError('invalid_employee_count')
            result['claims'].append({
                'id': digest((number + ':' + field + ':' + canonical(value)).encode()),
                'field': field, 'value': value, 'evidence_id': snapshot,
                'json_pointer': '/' + key, 'reporting_period': None,
                'effective_date': data.get('registreringsdatoAntallAnsatteEnhetsregisteret')
                    if field == 'registered_employees' else None,
                'extraction_method': 'registry_json_pointer',
            })
            result['availability'][field] = {'state': 'available'}
        if isinstance(data.get('hjemmeside'), str) and data['hjemmeside'].strip():
            result['candidates'].append({'kind': 'website', 'value': data['hjemmeside'],
                                         'status': 'unverified', 'evidence_id': snapshot,
                                         'json_pointer': '/hjemmeside'})
        for field in EXTERNAL:
            result['availability'][field] = {'state': 'not_available',
                'reason': 'not_researched_in_registry_baseline'}
        result['summary'] = data['navn'] + ': official registry facts retrieved. External information remains unresearched.'
        return result, body
    except urllib.error.HTTPError as exc:
        result = envelope(number, 'not_available' if exc.code == 404 else
                          'blocked' if exc.code in (401,403,429) else 'failed', 'http_' + str(exc.code))
    except FileNotFoundError:
        result = envelope(number, 'not_available', 'fixture_missing')
    except Exception as exc:
        # Do not copy request URLs, credentials or arbitrary server text to output.
        result = envelope(number, 'failed', type(exc).__name__)
    result['source_mode'] = 'fixture' if fixture_dir else 'live'
    return result, None


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'snapshots').mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'history.sqlite3')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY, org TEXT, checked_at TEXT, state TEXT, envelope TEXT);
        CREATE TABLE IF NOT EXISTS latest (org TEXT PRIMARY KEY, envelope TEXT);
        ''')

    def save(self, result, body):
        org = result['organisation_number']
        prior_row = self.db.execute('SELECT envelope FROM latest WHERE org=?', (org,)).fetchone()
        prior = json.loads(prior_row[0]) if prior_row else None
        snapshots = body if isinstance(body, list) else [(body, '.json')] if body is not None else []
        for content, suffix in snapshots:
            if suffix not in ('.json', '.html'):
                raise ValueError('invalid_snapshot_type')
            key = digest(content)
            path = self.root / 'snapshots' / (key + suffix)
            if not path.exists():
                atomic_write(path, content)
            elif digest(path.read_bytes()) != key:
                raise ValueError('stored_snapshot_integrity_failure')
        changes = []
        if prior and result['state'] == 'available':
            old = {c.get('subject', c['field']): c for c in prior['claims']}
            new = {c.get('subject', c['field']): c for c in result['claims']}
            for subject in sorted(old.keys() | new.keys()):
                before, after = old.get(subject), new.get(subject)
                if before and after and before['value'] == after['value']:
                    continue
                changes.append({'field': (after or before)['field'], 'subject': subject,
                                'kind': 'added' if before is None else
                                'no_longer_reported' if after is None else 'changed',
                                'before': before, 'after': after})
        result['refresh']['changes'] = changes
        if prior:
            result['refresh']['previous_success_at'] = prior['refresh']['checked_at']
        if prior and result['state'] == 'available':
            # A successful registry refresh does not make an unsuccessful or
            # unrequested website refresh evidence of real-world disappearance.
            current = {c.get('subject', c['field']) for c in result['claims']}
            historical = prior['claims'] + prior.get('last_known', {}).get('claims', [])
            stale = {c.get('subject', c['field']): c for c in historical
                     if c['field'] in ('website_identity', 'company_page')
                     and c.get('subject', c['field']) not in current}
            if stale:
                evidence = {e['id']: e for e in prior['evidence'] + prior.get('last_known', {}).get('evidence', [])}
                result['last_known'] = {'as_of': prior['refresh']['checked_at'],
                    'claims': list(stale.values()),
                    'evidence': [evidence[key] for key in sorted({c['evidence_id'] for c in stale.values()})]}
        if prior and result['state'] != 'available':
            result['last_known'] = {'as_of': prior['refresh']['checked_at'],
                                   'claims': prior['claims'] + prior.get('last_known', {}).get('claims', []),
                                   'evidence': prior['evidence'] + prior.get('last_known', {}).get('evidence', [])}
            result['summary'] = 'Refresh unsuccessful; previous supported facts retained as last_known, not current.'
        with self.db:
            self.db.execute('INSERT INTO observations(org,checked_at,state,envelope) VALUES(?,?,?,?)',
                (org, result['refresh']['checked_at'], result['state'], canonical(result)))
            if result['state'] == 'available':
                self.db.execute('INSERT OR REPLACE INTO latest VALUES(?,?)', (org, canonical(result)))
        return result

    def close(self):
        self.db.close()


def read_inputs(path):
    numbers = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        raw = line.strip()
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                value = value.get('organisation_number', value.get('organisasjonsnummer', ''))
            raw = str(value) if value is not None else ''
        except json.JSONDecodeError:
            pass
        numbers.append(raw)
    return numbers


def atomic_write(path, content):
    """Replace an artifact only after its full contents are flushed to disk."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content if isinstance(content, bytes) else content.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_batch(numbers, output, fixture_dir=None, workers=4, budget=300, timeout=12, allowed_domains=None):
    started = time.monotonic()
    root = Path(output)
    store = Store(root)
    def task(number):
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            return envelope(number, 'failed', 'time_budget_exhausted'), None
        result, body = research(number, fixture_dir, min(timeout, max(0.1, remaining)))
        if allowed_domains and not fixture_dir and result['state'] == 'available':
            from web_research import enrich
            pages = enrich(result, allowed_domains, min(started + budget, time.monotonic() + timeout))
            body = [(body, '.json')] + pages
        return result, body
    results = [None] * len(numbers)
    try:
        # Completion journal is independent of SQLite. A worker/store error must
        # not prevent a terminal envelope for every other input.
        with (root / 'completion.jsonl').open('w', encoding='utf-8') as journal:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                pending = {pool.submit(task, number): index for index, number in enumerate(numbers)}
                for future in concurrent.futures.as_completed(pending):
                    index = pending[future]
                    try:
                        result, body = future.result()
                    except Exception as exc:
                        result, body = envelope(numbers[index], 'failed', 'worker_' + type(exc).__name__), None
                    try:
                        result = store.save(result, body)
                    except Exception as exc:
                        result = envelope(numbers[index], 'failed', 'storage_' + type(exc).__name__)
                    result['input_index'] = index
                    result['source_mode'] = 'fixture' if fixture_dir else 'live'
                    results[index] = result
                    journal.write(canonical(result) + '\n')
                    journal.flush()
                    os.fsync(journal.fileno())
        atomic_write(root / 'profiles.jsonl', ''.join(canonical(r) + '\n' for r in results))
        counts = {state: sum(r['state'] == state for r in results) for state in sorted(STATES)}
        report = {'version': VERSION, 'mode': 'fixture' if fixture_dir else 'live',
                  'input_count': len(numbers), 'output_count': len(results),
                  'states': counts, 'duration_seconds': round(time.monotonic()-started, 3),
                  'claim_count': sum(len(r['claims']) for r in results),
                  'website_requests': sum(r.get('website_research', {}).get('requests', 0) for r in results),
                  'website_pages_verified': sum(r.get('website_research', {}).get('pages_verified', 0) for r in results),
                  'external_coverage_measured': False, 'official_score': None,
                  'external_api_cost_usd': 0, 'models': [],
                  'limitations': ['Website research is opt-in and limited to reviewed registry candidate domains.',
                                  'Leadership, financial, job and news extraction not implemented.',
                                  'Soft deadline; network and thread cleanup may exceed the budget.',
                                  'Not an official evaluation or qualification result.']}
        atomic_write(root / 'report.json', json.dumps(report, indent=2) + '\n')
        render(results, root / 'index.html')
        return report
    finally:
        store.close()


def render(results, target):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for r in results:
        rows = []
        refs = {e['id']: e for e in r['evidence']}
        for claim in r['claims']:
            e = refs[claim['evidence_id']]
            url = e['source_url']
            safe_url = url.startswith(BASE)
            if e['source_class'] == 'verified_company_website':
                from web_research import normalize_url
                try:
                    safe_url = normalize_url(url) == url
                except ValueError:
                    safe_url = False
            source = '<a href="' + esc(url) + '" rel="noreferrer">Source ↗</a>' if safe_url else esc(url)
            locator = ('JSON pointer: ' + esc(claim['json_pointer'])) if 'json_pointer' in claim else ('Text span: ' + esc(claim.get('text_span', 'missing')))
            rows.append('<tr><th>' + esc(claim['field'].replace('_', ' ')) + '</th><td>' +
                        esc(canonical(claim['value'])) + '</td><td><details><summary>Evidence</summary>' +
                        source + '<p>Retrieved ' + esc(e['retrieved_at']) + '</p><p>' +
                        locator + '</p><code>SHA-256 ' + esc(e['id']) + '</code>' +
                        ('<p>SYNTHETIC FIXTURE — not a real company claim</p>' if e['synthetic'] else '') +
                        '</details></td></tr>')
        unknown = ', '.join(k.replace('_',' ') for k,v in r['availability'].items() if v['state'] != 'available')
        gaps = ''.join('<tr><th>' + esc(k.replace('_', ' ')) + '</th><td>' +
            esc(v['state']) + '</td><td>' + esc(v.get('reason', '')) + '</td></tr>'
            for k, v in r['availability'].items() if v['state'] != 'available')
        website = r.get('website_research')
        website_status = ('<p class="muted">Website research: ' + str(website['pages_verified']) +
            ' verified pages · ' + str(website['requests']) + ' requests</p>' +
            ('<p class="muted">Research notes: ' + esc(', '.join(website['errors'])) + '</p>' if website['errors'] else '')) if website else ''
        changes = r['refresh']['changes']
        cards.append('<article><div class="eyebrow">' + esc(r['organisation_number']) + ' · ' + esc(r['state']) +
                     '</div><h2>' + esc(r['legal_identity'].get('name', 'Unresolved company')) + '</h2><p>' +
                     esc(r['summary']) + '</p><div class="scroll"><table><thead><tr><th>Fact</th><th>Value</th><th>Source</th></tr></thead><tbody>' +
                     ''.join(rows) + '</tbody></table></div><p class="muted">Unknown / unresearched: ' + esc(unknown or 'none') +
                     '</p><details><summary>Refresh changes (' + str(len(changes)) + ')</summary><pre>' +
                     esc(json.dumps(changes, ensure_ascii=False, indent=2)) + '</pre></details>' +
                     ('<details><summary>Availability and gaps</summary><div class="scroll"><table><thead><tr><th>Field</th><th>State</th><th>Reason</th></tr></thead><tbody>' + gaps + '</tbody></table></div></details>' if gaps else '') +
                     website_status +
                     ('<details><summary>Last known evidence</summary><pre>' + esc(json.dumps(r['last_known'],ensure_ascii=False,indent=2)) + '</pre></details>' if 'last_known' in r else '') +
                     ('<p>Errors: ' + esc(', '.join(r['errors'])) + '</p>' if r['errors'] else '') + '</article>')
    Path(target).write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TraceAtlas · Evidence explorer</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#172839;font:16px/1.6 system-ui,sans-serif}header{background:#102d3b;color:white;padding:48px max(24px,calc((100vw - 1100px)/2))}header p{color:#bed9df}h1{font-size:42px;letter-spacing:-2px;margin:0}main{max-width:1150px;margin:30px auto;padding:0 24px}article{background:white;border:1px solid #dae3e7;border-radius:14px;padding:26px;margin:24px 0}.eyebrow{color:#176b72;font:600 13px monospace}h2{margin:8px 0;font-size:25px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:12px;text-align:left;border-bottom:1px solid #e4eaee;vertical-align:top}td{min-width:180px;overflow-wrap:anywhere}th{text-transform:capitalize}a{color:#086d82}summary{cursor:pointer;color:#086d82}code{font-size:11px;word-break:break-all}.muted{color:#536772;font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}footer{padding:24px;text-align:center;color:#536772}@media(max-width:600px){header{padding:30px 20px}h1{font-size:34px}main{padding:0 12px}article{padding:16px}}
</style><header><div class="eyebrow" style="color:#92d7d0">COMPANY INTELLIGENCE / EVIDENCE EXPLORER</div><h1>TraceAtlas</h1><p>Every fact has a source. Every unknown stays visible.</p></header><main><p>Registry baseline · ''' + str(len(results)) +
        ' company results · Verified facts and explicit gaps</p>' + ''.join(cards) + '</main><footer>TraceAtlas · No model-generated facts · No official competition score</footer></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Text or JSONL organisation numbers')
    parser.add_argument('--output', default='runs/latest')
    parser.add_argument('--fixtures', help='Offline JSON response folder; clearly labelled synthetic')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--budget-seconds', type=float, default=300)
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('--allow-domain', action='append', default=[], help='Reviewed public website hostname; enables opt-in website research (repeatable)')
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or any(not math.isfinite(value) or value <= 0 for value in (args.budget_seconds, args.timeout)):
        parser.error('workers must be 1..8; budget and timeout must be positive')
    from web_research import normalize_url
    from urllib.parse import urlsplit
    domains = []
    for domain in args.allow_domain:
        try:
            if any(c in domain for c in '/:@?#'):
                raise ValueError('hostname only')
            domains.append(urlsplit(normalize_url(domain)).hostname)
        except ValueError:
            parser.error('allow-domain must be a public HTTPS hostname')
    if args.fixtures and domains:
        parser.error('fixture mode never makes website requests')
    try:
        numbers = read_inputs(args.input)
    except (OSError, UnicodeError):
        parser.error('input file must be readable UTF-8 text')
    if not numbers:
        parser.error('input file must contain at least one organization number')
    report = run_batch(numbers, args.output, args.fixtures,
                       args.workers, args.budget_seconds, args.timeout, domains)
    print(json.dumps(report, indent=2))
    return 0 if report['states']['failed'] == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
