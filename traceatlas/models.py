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
    financials = [claim['value'] for claim in result.get('claims', [])
                  if claim['field'] == 'financials' and isinstance(claim.get('value'), dict)]
    accounts = []
    for value in financials:
        if value.get('metric') == 'revenue' and isinstance(value.get('amount'), (int, float)):
            accounts.append(dict(value, revenue=value['amount']))
        elif isinstance(value.get('revenue'), (int, float)):
            accounts.append(value)
    accounts.sort(key=lambda item: str(item.get('period_end', '')), reverse=True)
    if accounts:
        latest = accounts[0]
        comparable = None
        for item in accounts[1:]:
            if (item.get('report_type') != latest.get('report_type')
                    or item.get('currency') != latest.get('currency')):
                continue
            try:
                if int(str(latest['period_end'])[:4]) - int(str(item['period_end'])[:4]) == 1:
                    comparable = item
                    break
            except (KeyError, TypeError, ValueError):
                continue
        revenue = latest['revenue']
        currency = latest.get('currency') or 'currency unreported'
        scope = 'consolidated accounts' if latest.get('report_type') == 'KONSERN' else 'company accounts'
        statement = ('Revenue was ' + format(revenue, ',.0f') + ' ' + currency + ' in '
                     + str(latest['period_end'])[:4] + ' (' + scope + ')')
        if comparable and comparable['revenue'] != 0:
            change = (revenue - comparable['revenue']) / abs(comparable['revenue']) * 100
            direction = 'up' if change > 0 else 'down' if change < 0 else 'unchanged'
            statement += ', ' + direction + ' ' + format(abs(change), '.1f') + '% year over year'
        else:
            statement += '; no comparable prior period was available'
        parts.append(statement)
        latest_metrics = {
            item.get('metric'): item.get('amount') for item in financials
            if item.get('period_end') == latest.get('period_end')
            and item.get('report_type') == latest.get('report_type')
            and item.get('currency') == latest.get('currency')
        }
        if isinstance(latest_metrics.get('annual_result'), (int, float)):
            parts.append('Annual result was ' + format(latest_metrics['annual_result'], ',.0f')
                         + ' ' + currency + ' for the same period')
        if isinstance(latest_metrics.get('total_equity'), (int, float)):
            parts.append('Total equity was ' + format(latest_metrics['total_equity'], ',.0f')
                         + ' ' + currency + ' at period end')

    availability = result.get('availability', {})
    unchecked, unavailable, incomplete = [], [], []
    for field, status in availability.items():
        if status.get('state') == 'available':
            continue
        label = field.replace('_', ' ')
        reason = status.get('reason', '')
        if reason.startswith('not_researched'):
            unchecked.append(label)
        elif status.get('state') == 'not_available':
            unavailable.append(label)
        else:
            incomplete.append(label + ' (' + status.get('state', 'unknown').replace('_', ' ') + ')')

    def short_list(values):
        shown = values[:4]
        return ', '.join(shown) + (' and ' + str(len(values) - 4) + ' more' if len(values) > 4 else '')

    if unchecked:
        parts.append('Not checked in this run: ' + short_list(unchecked))
    if unavailable:
        parts.append('Checked but not reported: ' + short_list(unavailable))
    if incomplete:
        parts.append('Research incomplete: ' + short_list(incomplete))

    changes = result.get('refresh', {}).get('changes', [])
    if changes:
        labels = []
        for change in changes[:4]:
            labels.append(change['field'].replace('_', ' ') + ' ' + change['kind'].replace('_', ' '))
        if len(changes) > 4:
            labels.append(str(len(changes) - 4) + ' more')
        parts.append('Latest refresh changes: ' + ', '.join(labels))
    return '. '.join(parts) + '.'


