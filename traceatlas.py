"""TraceAtlas: dependency-free, evidence-preserving Norwegian registry baseline."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import html
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = '0.1.0'
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
        if body is not None:
            key = digest(body)
            path = self.root / 'snapshots' / (key + '.json')
            if not path.exists():
                path.write_bytes(body)
            elif digest(path.read_bytes()) != key:
                raise ValueError('stored_snapshot_integrity_failure')
        changes = []
        if prior and result['state'] == 'available':
            old = {c['field']: c for c in prior['claims']}
            new = {c['field']: c for c in result['claims']}
            for field in sorted(old.keys() | new.keys()):
                before, after = old.get(field), new.get(field)
                if before and after and before['value'] == after['value']:
                    continue
                changes.append({'field': field, 'kind': 'added' if before is None else
                                'no_longer_reported' if after is None else 'changed',
                                'before': before, 'after': after})
        result['refresh']['changes'] = changes
        if prior:
            result['refresh']['previous_success_at'] = prior['refresh']['checked_at']
        if prior and result['state'] != 'available':
            result['last_known'] = {'as_of': prior['refresh']['checked_at'],
                                   'claims': prior['claims'], 'evidence': prior['evidence']}
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


def run_batch(numbers, output, fixture_dir=None, workers=4, budget=300, timeout=12):
    started = time.monotonic()
    root = Path(output)
    store = Store(root)
    # All tasks check a shared deadline before starting. Individual requests have
    # bounded timeouts. An envelope is emitted even when work cannot begin.
    def task(number):
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            return envelope(number, 'failed', 'time_budget_exhausted'), None
        return research(number, fixture_dir, min(timeout, max(0.1, remaining)))
    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for result, body in pool.map(task, numbers):
                results.append(store.save(result, body))
        output_file = root / 'profiles.jsonl'
        temp = root / 'profiles.jsonl.tmp'
        temp.write_text(''.join(canonical(r) + '\n' for r in results))
        temp.replace(output_file)
        counts = {state: sum(r['state'] == state for r in results) for state in sorted(STATES)}
        report = {'version': VERSION, 'mode': 'fixture' if fixture_dir else 'live',
                  'input_count': len(numbers), 'output_count': len(results),
                  'states': counts, 'duration_seconds': round(time.monotonic()-started, 3),
                  'claim_count': sum(len(r['claims']) for r in results),
                  'external_coverage_measured': False, 'official_score': None,
                  'external_api_cost_usd': 0, 'models': [],
                  'limitations': ['Registry baseline only; external discovery not implemented.',
                                  'Not an official evaluation or qualification result.']}
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
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
            # Only our fixed registry prefix is made clickable.
            url = e['source_url']
            source = '<a href="' + esc(url) + '" rel="noreferrer">Registry source ↗</a>' if url.startswith(BASE) else esc(url)
            rows.append('<tr><th>' + esc(claim['field'].replace('_', ' ')) + '</th><td>' +
                        esc(canonical(claim['value'])) + '</td><td><details><summary>Evidence</summary>' +
                        source + '<p>Retrieved ' + esc(e['retrieved_at']) + '</p><p>JSON pointer: ' +
                        esc(claim['json_pointer']) + '</p><code>SHA-256 ' + esc(e['id']) + '</code>' +
                        ('<p>SYNTHETIC FIXTURE — not a real company claim</p>' if e['synthetic'] else '') +
                        '</details></td></tr>')
        unknown = ', '.join(k.replace('_',' ') for k,v in r['availability'].items() if v['state'] != 'available')
        changes = r['refresh']['changes']
        cards.append('<article><div class="eyebrow">' + esc(r['organisation_number']) + ' · ' + esc(r['state']) +
                     '</div><h2>' + esc(r['legal_identity'].get('name', 'Unresolved company')) + '</h2><p>' +
                     esc(r['summary']) + '</p><div class="scroll"><table><thead><tr><th>Fact</th><th>Value</th><th>Source</th></tr></thead><tbody>' +
                     ''.join(rows) + '</tbody></table></div><p class="muted">Unknown / unresearched: ' + esc(unknown or 'none') +
                     '</p><details><summary>Refresh changes (' + str(len(changes)) + ')</summary><pre>' +
                     esc(json.dumps(changes, ensure_ascii=False, indent=2)) + '</pre></details>' +
                     ('<details><summary>Last known evidence</summary><pre>' + esc(json.dumps(r['last_known'],ensure_ascii=False,indent=2)) + '</pre></details>' if 'last_known' in r else '') +
                     ('<p>Errors: ' + esc(', '.join(r['errors'])) + '</p>' if r['errors'] else '') + '</article>')
    Path(target).write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TraceAtlas · Evidence explorer</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#172839;font:16px/1.6 system-ui,sans-serif}header{background:#102d3b;color:white;padding:48px max(24px,calc((100vw - 1100px)/2))}header p{color:#bed9df}h1{font-size:42px;letter-spacing:-2px;margin:0}main{max-width:1150px;margin:30px auto;padding:0 24px}article{background:white;border:1px solid #dae3e7;border-radius:14px;padding:26px;margin:24px 0}.eyebrow{color:#176b72;font:600 13px monospace}h2{margin:8px 0;font-size:25px}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:12px;text-align:left;border-bottom:1px solid #e4eaee;vertical-align:top}td{min-width:180px;overflow-wrap:anywhere}th{text-transform:capitalize}a{color:#086d82}summary{cursor:pointer;color:#086d82}code{font-size:11px;word-break:break-all}.muted{color:#536772;font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}footer{padding:24px;text-align:center;color:#536772}@media(max-width:600px){header{padding:30px 20px}h1{font-size:34px}main{padding:0 12px}article{padding:16px}}
</style><header><div class="eyebrow" style="color:#92d7d0">COMPANY INTELLIGENCE / EVIDENCE EXPLORER</div><h1>TraceAtlas</h1><p>Every fact has a source. Every unknown stays visible.</p></header><main><p>Registry baseline · ''' + str(len(results)) +
        ' company results · External discovery pending</p>' + ''.join(cards) + '</main><footer>TraceAtlas · No model-generated facts · No official competition score</footer></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Text or JSONL organisation numbers')
    parser.add_argument('--output', default='runs/latest')
    parser.add_argument('--fixtures', help='Offline JSON response folder; clearly labelled synthetic')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--budget-seconds', type=float, default=300)
    parser.add_argument('--timeout', type=float, default=12)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or args.budget_seconds <= 0 or args.timeout <= 0:
        parser.error('workers must be 1..8; budget and timeout must be positive')
    report = run_batch(read_inputs(args.input), args.output, args.fixtures,
                       args.workers, args.budget_seconds, args.timeout)
    print(json.dumps(report, indent=2))
    return 0 if report['states']['failed'] == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
