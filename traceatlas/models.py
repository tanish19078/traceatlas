"""Shared envelopes, field definitions and durable file primitives."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
VERSION = '0.6.0'
BASE = 'https://data.brreg.no/enhetsregisteret/api/enheter/'
STATES = {'available', 'not_available', 'blocked', 'not_applicable', 'ambiguous', 'failed'}
FIELDS = {
    'legal_name': 'navn', 'legal_form': 'organisasjonsform',
    'registered_address': 'forretningsadresse', 'industry': 'naeringskode1',
    'registered_at': 'registreringsdatoEnhetsregisteret',
    'business_activity': 'aktivitet', 'bankrupt': 'konkurs',
    'in_liquidation': 'underAvvikling',
}
EXTERNAL = ['website_identity', 'company_description', 'leadership', 'locations', 'financials', 'jobs', 'news', 'legal_cases']


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


def company_summary(result):
    """Build a short summary from supported claims already attached to a result."""
    identity = result.get('legal_identity', {}).get('name') or 'Company'
    claims = {claim['field']: claim['value'] for claim in result.get('claims', [])}
    parts = [identity]
    activity = claims.get('business_activity')
    if isinstance(activity, list):
        activity = '; '.join(item for item in activity if isinstance(item, str))
    if isinstance(activity, str) and activity.strip():
        parts.append(activity.strip())
    website_description = claims.get('company_description')
    if isinstance(website_description, str) and website_description.strip():
        parts.append('Company website: ' + website_description.strip())
    industry = claims.get('industry')
    if isinstance(industry, dict):
        industry = industry.get('beskrivelse') or industry.get('kode')
    if isinstance(industry, str) and industry.strip() and industry.casefold() not in ' '.join(parts).casefold():
        parts.append('Industry: ' + industry.strip())
    leaders = [claim['value'] for claim in result.get('claims', []) if claim['field'] == 'leadership' and isinstance(claim.get('value'), dict)]
    if leaders:
        parts.append('Registered leadership: ' + '; '.join(item['name'] + ' (' + item['role'] + ')' for item in leaders[:3]))
    locations = [claim['value'] for claim in result.get('claims', []) if claim['field'] == 'locations' and isinstance(claim.get('value'), dict)]
    if locations:
        parts.append(str(len(locations)) + ' registered operating ' + ('location' if len(locations) == 1 else 'locations'))
    news = [claim['value'] for claim in result.get('claims', []) if claim['field'] == 'news' and isinstance(claim.get('value'), dict)]
    dated_news = sorted(news, key=lambda item: str(item.get('datePublished', '')), reverse=True)
    if dated_news:
        story = dated_news[0]
        parts.append('Latest company news (' + str(story.get('datePublished')) + '): ' + str(story.get('headline')))
    accounts = [claim['value'] for claim in result.get('claims', []) if claim['field'] == 'financials' and isinstance(claim.get('value'), dict)]
    accounts.sort(key=lambda item: str(item.get('period_end', '')), reverse=True)
    if accounts:
        latest = accounts[0]
        comparable = next((item for item in accounts[1:] if item.get('report_type') == latest.get('report_type') and item.get('currency') == latest.get('currency')), None)
        revenue = latest['revenue']
        currency = latest.get('currency') or 'currency unreported'
        statement = 'Revenue was ' + format(revenue, ',.0f') + ' ' + currency + ' in ' + str(latest['period_end'])[:4]
        if comparable and comparable['revenue'] != 0:
            change = (revenue - comparable['revenue']) / abs(comparable['revenue']) * 100
            direction = 'up' if change > 0 else 'down' if change < 0 else 'unchanged'
            statement += ', ' + direction + ' ' + format(abs(change), '.1f') + '% year over year'
        else:
            statement += '; no comparable prior period was available'
        parts.append(statement)
    return '. '.join(parts) + '.'


