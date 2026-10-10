"""Shared envelopes, field definitions and durable file primitives."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
VERSION = '0.3.0'
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
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def valid_org(number):
    if not isinstance(number, str) or len(number) != 9 or not number.isascii() or not number.isdigit():
        return False
    remainder = 11 - sum(int(n)*w for n, w in zip(number[:8], [3,2,7,6,5,4,3,2])) % 11
    return remainder != 10 and (0 if remainder == 11 else remainder) == int(number[-1])


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



def envelope(number, state='failed', message=None):
    return {'schema_version': '0.1', 'organisation_number': number,
            'state': state, 'legal_identity': {}, 'claims': [], 'evidence': [],
            'availability': {}, 'candidates': [], 'errors': [message] if message else [],
            'refresh': {'checked_at': now(), 'changes': []},
            'summary': 'Research unavailable.', 'source_mode': None}


