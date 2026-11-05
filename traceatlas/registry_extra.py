"""Public roles and operating locations from the Norwegian entity register."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode
from .models import digest, canonical, now

BASE = 'https://data.brreg.no/enhetsregisteret/api/'


def fetch(url, timeout):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'TraceAtlas/0.5 (company research; https://github.com/tanish19078/traceatlas)',
        'Accept': 'application/json',
    })
    from .network import take_request, rate_limited
    take_request(url)
    try:
        from .registry import NoRedirect
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            rate_limited(url, exc.headers.get('Retry-After') if exc.headers else None)
        raise
    with response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('registry_response_size_limit')
        return body


def _walk(value):
    stack = [value]
    visited = 0
    while stack and visited < 20_000:
        current = stack.pop()
        visited += 1
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def extract_roles(data, number, evidence_id):
    claims = []
    seen = set()
    for item in _walk(data):
        person = item.get('person')
        role = item.get('type')
        if not isinstance(person, dict) or not isinstance(role, dict):
            continue
        name = person.get('navn')
        if not isinstance(name, dict):
            continue
        full_name = ' '.join(part.strip() for part in (name.get('fornavn'), name.get('mellomnavn'), name.get('etternavn')) if isinstance(part, str) and part.strip())
        title = role.get('beskrivelse')
        if not full_name or not isinstance(title, str) or not title.strip():
            continue
        value = {'name': full_name, 'role': title.strip()}
        key = canonical(value)
        if key in seen:
            continue
        seen.add(key)
        subject = 'leadership:' + key
        claims.append({'id': digest((number + subject).encode()), 'field': 'leadership',
            'subject': subject, 'value': value, 'evidence_id': evidence_id,
            'json_pointer': None, 'reporting_period': None, 'effective_date': None,
            'extraction_method': 'brreg_roles_v1'})
    return claims


def extract_locations(data, number, evidence_id):
    claims = []
    seen = set()
    for item in _walk(data):
        if item.get('overordnetEnhet') != number or not isinstance(item.get('organisasjonsnummer'), str):
            continue
        address = item.get('beliggenhetsadresse') or item.get('forretningsadresse') or {}
        if not isinstance(address, dict):
            address = {}
        value = {'name': item.get('navn'), 'organisation_number': item['organisasjonsnummer'],
                 'address': address, 'employees': item.get('antallAnsatte')}
        if not isinstance(value['name'], str) or not value['name'].strip():
            continue
        key = canonical(value)
        if key in seen:
            continue
        seen.add(key)
        subject = 'location:' + item['organisasjonsnummer']
        claims.append({'id': digest((number + subject + key).encode()), 'field': 'locations',
            'subject': subject, 'value': value, 'evidence_id': evidence_id,
            'json_pointer': None, 'reporting_period': None, 'effective_date': None,
            'extraction_method': 'brreg_subunits_v1'})
    return claims


def _enrich_field(result, field, url, timeout, extractor, source_class, version):
    try:
        body = fetch(url, timeout)
        data = json.loads(body)
        key = digest(body)
        claims = extractor(data, result['organisation_number'], key)
        result['claims'].extend(claims)
        result['availability'][field] = {'state': 'available' if claims else 'not_available', **({} if claims else {'reason': 'no_registered_records'})}
        result['evidence'].append({'id': key, 'source_url': url, 'retrieved_at': now(),
            'content_sha256': key, 'snapshot_path': 'snapshots/' + key + '.json',
            'source_class': source_class, 'extractor_version': version,
            'organisation_number': result['organisation_number'], 'synthetic': False})
        return body
    except urllib.error.HTTPError as exc:
        result['availability'][field] = {'state': 'not_available' if exc.code == 404 else 'blocked' if exc.code in (401, 403, 429) else 'failed', 'reason': 'http_' + str(exc.code)}
    except (OSError, ValueError, TypeError):
        result['availability'][field] = {'state': 'failed', 'reason': 'registry_lookup_unavailable'}
    return None


def enrich(result, timeout=12):
    number = result['organisation_number']
    roles_url = BASE + 'enheter/' + number + '/roller'
    locations_url = BASE + 'underenheter?' + urlencode({'overordnetEnhet': number, 'size': 100})
    bodies = []
    for args in ((result, 'leadership', roles_url, timeout, extract_roles, 'official_registry_roles', 'brreg_roles_v1'),
                 (result, 'locations', locations_url, timeout, extract_locations, 'official_registry_locations', 'brreg_subunits_v1')):
        body = _enrich_field(*args)
        if body is not None:
            bodies.append((body, '.json'))
    return bodies
