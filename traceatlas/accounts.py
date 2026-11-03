"""Auditable revenue facts from the official Norwegian accounts register."""
import json
import math
import urllib.error
import urllib.request
from .models import digest, canonical, now

BASE = 'https://data.brreg.no/regnskapsregisteret/regnskap/'


def fetch(number, timeout=12):
    url = BASE + number
    request = urllib.request.Request(url, headers={'User-Agent': 'TraceAtlas/0.5 (company research)', 'Accept': 'application/json'})
    from .network import take_request, rate_limited
    take_request(url)
    try:
        response = urllib.request.build_opener().open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            rate_limited(url, exc.headers.get('Retry-After') if exc.headers else None)
        raise
    with response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('accounts_response_size_limit')
        return body


def records(data):
    """Find account records without assuming the API's collection wrapper."""
    found = []
    stack = [data]
    seen = 0
    while stack and seen < 1000:
        item = stack.pop()
        seen += 1
        if isinstance(item, dict):
            if isinstance(item.get('regnskapsperiode'), dict) and isinstance(item.get('virksomhet'), dict):
                found.append(item)
            else:
                stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    unique = {}
    for item in found:
        period = item.get('regnskapsperiode', {})
        end = period.get('tilDato')
        org = item.get('virksomhet', {}).get('organisasjonsnummer')
        result = item.get('resultatregnskapResultat', {}).get('driftsresultat', {}).get('driftsinntekter', {})
        revenue = result.get('sumDriftsinntekter')
        if isinstance(end, str) and isinstance(org, str) and isinstance(revenue, (int, float)) and not isinstance(revenue, bool) and math.isfinite(revenue):
            key = (end, item.get('regnskapstype', 'SELSKAP'))
            unique[key] = {'period_start': period.get('fraDato'), 'period_end': end,
                           'revenue': revenue, 'currency': item.get('valuta'),
                           'report_type': item.get('regnskapstype', 'SELSKAP'),
                           'organisation_number': org}
    return sorted(unique.values(), key=lambda row: (row['period_end'], row['report_type']), reverse=True)


def extract(data, number, evidence_id):
    claims = []
    for value in records(data):
        if value['organisation_number'] != number:
            continue
        subject = 'financials:' + value['report_type'] + ':' + value['period_end']
        claims.append({'id': digest((number + subject + canonical(value)).encode()),
                       'field': 'financials', 'subject': subject, 'value': value,
                       'evidence_id': evidence_id, 'json_pointer': None,
                       'reporting_period': value['period_end'], 'effective_date': value['period_end'],
                       'extraction_method': 'official_accounts_v1'})
    return claims


def enrich(result, timeout=12, body=None):
    number = result['organisation_number']
    try:
        body = body if body is not None else fetch(number, timeout)
        data = json.loads(body)
        key = digest(body)
        claims = extract(data, number, key)
        result['availability']['financials'] = {'state': 'available' if claims else 'not_available',
            **({} if claims else {'reason': 'no_reported_revenue_records'})}
        result['claims'].extend(claims)
        result['evidence'].append({'id': key, 'source_url': BASE + number, 'retrieved_at': now(),
            'content_sha256': key, 'snapshot_path': 'snapshots/' + key + '.json',
            'source_class': 'official_accounts', 'extractor_version': 'official_accounts_v1',
            'organisation_number': number, 'synthetic': False})
        return body
    except urllib.error.HTTPError as exc:
        result['availability']['financials'] = {'state': 'not_available' if exc.code == 404 else 'blocked' if exc.code in (401,403,429) else 'failed', 'reason': 'http_' + str(exc.code)}
    except (OSError, ValueError, TypeError, KeyError):
        result['availability']['financials'] = {'state': 'failed', 'reason': 'accounts_response_unavailable'}
    return None
