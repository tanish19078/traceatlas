"""Official registry connector and exact-entity field extraction."""
import json
import urllib.error
import urllib.request
from pathlib import Path
from .models import BASE, VERSION, FIELDS, EXTERNAL, now, digest, valid_org, canonical, envelope
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


