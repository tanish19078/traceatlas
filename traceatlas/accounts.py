"""Auditable financial facts from the official Norwegian accounts register."""
import json
import math
import urllib.error
import urllib.request
from datetime import date
from .models import digest, canonical, now

BASE = 'https://data.brreg.no/regnskapsregisteret/regnskap/'
METRICS = {
    'revenue': ('resultatregnskapResultat', 'driftsresultat', 'driftsinntekter', 'sumDriftsinntekter'),
    'sales_revenue': ('resultatregnskapResultat', 'driftsresultat', 'driftsinntekter', 'salgsinntekter'),
    'operating_result': ('resultatregnskapResultat', 'driftsresultat', 'driftsresultat'),
    'annual_result': ('resultatregnskapResultat', 'aarsresultat'),
    'total_assets': ('eiendeler', 'sumEiendeler'),
    'total_equity': ('egenkapitalGjeld', 'egenkapital', 'sumEgenkapital'),
    'total_liabilities': ('egenkapitalGjeld', 'gjeldOversikt', 'sumGjeld'),
}


def fetch(number, timeout=12):
    url = BASE + number
    request = urllib.request.Request(url, headers={'User-Agent': 'TraceAtlas/0.5 (company research)', 'Accept': 'application/json'})
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
            raise ValueError('accounts_response_size_limit')
        return body


def legacy_records(data):
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


def extract_v1(data, number, evidence_id):
    claims = []
    for value in legacy_records(data):
        if value['organisation_number'] != number:
            continue
        subject = 'financials:' + value['report_type'] + ':' + value['period_end']
        claims.append({'id': digest((number + subject + canonical(value)).encode()),
                       'field': 'financials', 'subject': subject, 'value': value,
                       'evidence_id': evidence_id, 'json_pointer': None,
                       'reporting_period': value['period_end'], 'effective_date': value['period_end'],
                       'extraction_method': 'official_accounts_v1'})
    return claims


def _pointer_token(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def _account_records(data):
    stack = [(data, '')]
    seen = 0
    while stack and seen < 1000:
        item, pointer = stack.pop()
        seen += 1
        if isinstance(item, dict):
            if isinstance(item.get('regnskapsperiode'), dict) and isinstance(item.get('virksomhet'), dict):
                yield item, pointer
                continue
            for key, value in reversed(list(item.items())):
                stack.append((value, pointer + '/' + _pointer_token(key)))
        elif isinstance(item, list):
            for index in range(len(item) - 1, -1, -1):
                stack.append((item[index], pointer + '/' + str(index)))


def _at(record, path):
    value = record
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def records(data):
    unique = {}
    ambiguous = set()
    for item, pointer in _account_records(data):
        period = item.get('regnskapsperiode', {})
        start, end = period.get('fraDato'), period.get('tilDato')
        org = item.get('virksomhet', {}).get('organisasjonsnummer')
        report_type = item.get('regnskapstype')
        currency = item.get('valuta')
        try:
            start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        except (TypeError, ValueError):
            continue
        if (start_date > end_date or not isinstance(org, str)
                or report_type not in {'SELSKAP', 'KONSERN'}
                or not isinstance(currency, str) or not currency.strip() or len(currency) > 10):
            continue
        metrics = {name: _at(item, path) for name, path in METRICS.items()}
        metrics = {name: value for name, value in metrics.items() if _number(value)}
        if not metrics:
            continue
        key = (org, report_type, end)
        value = {
            'period_start': start, 'period_end': end, 'currency': currency.strip(),
            'report_type': report_type, 'organisation_number': org, 'metrics': metrics,
            'pointer': pointer,
        }
        fingerprint = canonical({name: value[name] for name in value if name != 'pointer'})
        if key in unique and unique[key][0] != fingerprint:
            ambiguous.add(key)
        else:
            unique[key] = (fingerprint, value)
    return [unique[key][1] for key in sorted(unique, key=lambda item: (item[2], item[1]), reverse=True)
            if key not in ambiguous]


def extract(data, number, evidence_id):
    claims = []
    for record in records(data):
        if record['organisation_number'] != number:
            continue
        for metric, amount in record['metrics'].items():
            value = {
                'metric': metric, 'amount': amount,
                'period_start': record['period_start'], 'period_end': record['period_end'],
                'currency': record['currency'], 'report_type': record['report_type'],
                'organisation_number': record['organisation_number'],
            }
            subject = 'financials:' + record['report_type'] + ':' + record['period_end'] + ':' + metric
            pointer = record['pointer'] + ''.join('/' + _pointer_token(part) for part in METRICS[metric])
            claims.append({'id': digest((number + subject + canonical(value)).encode()),
                           'field': 'financials', 'subject': subject, 'value': value,
                           'evidence_id': evidence_id, 'json_pointer': pointer,
                           'reporting_period': record['period_start'] + '/' + record['period_end'],
                           'effective_date': record['period_end'],
                           'extraction_method': 'official_accounts_v2'})
    return claims


def enrich(result, timeout=12, body=None):
    number = result['organisation_number']
    try:
        body = body if body is not None else fetch(number, timeout)
        data = json.loads(body)
        key = digest(body)
        claims = extract(data, number, key)
        result['availability']['financials'] = {'state': 'available' if claims else 'not_available',
            **({} if claims else {'reason': 'no_reported_financial_records'})}
        result['claims'].extend(claims)
        result['evidence'].append({'id': key, 'source_url': BASE + number, 'retrieved_at': now(),
            'content_sha256': key, 'snapshot_path': 'snapshots/' + key + '.json',
            'source_class': 'official_accounts', 'extractor_version': 'official_accounts_v2',
            'organisation_number': number, 'synthetic': False})
        return body
    except urllib.error.HTTPError as exc:
        result['availability']['financials'] = {'state': 'not_available' if exc.code == 404 else 'blocked' if exc.code in (401,403,429) else 'failed', 'reason': 'http_' + str(exc.code)}
    except (OSError, ValueError, TypeError, KeyError):
        result['availability']['financials'] = {'state': 'failed', 'reason': 'accounts_response_unavailable'}
    return None
