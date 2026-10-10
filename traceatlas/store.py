"""Immutable snapshots and transactional observation history."""
import json
import sqlite3
from pathlib import Path
from .models import atomic_write, digest, canonical
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
            historical = prior.get('last_known', {}).get('claims', []) + prior['claims']
            stale = {c.get('subject', c['field']): c for c in historical
                     if c['field'] in ('website_identity', 'company_page', 'jobs')
                     and c.get('subject', c['field']) not in current}
            if stale:
                evidence = {e['id']: e for e in prior['evidence'] + prior.get('last_known', {}).get('evidence', [])}
                result['last_known'] = {'as_of': prior['refresh']['checked_at'], 'legal_identity': prior['legal_identity'],
                    'claims': list(stale.values()),
                    'evidence': [evidence[key] for key in sorted({c['evidence_id'] for c in stale.values()})]}
        if prior and result['state'] != 'available':
            result['last_known'] = {'as_of': prior['refresh']['checked_at'], 'legal_identity': prior['legal_identity'],
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


