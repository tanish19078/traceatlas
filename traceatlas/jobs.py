"""Conservative JobPosting extraction from archived JSON-LD; no execution."""
import hashlib
import re
from datetime import date, datetime, timezone
from .models import canonical


def normalized_name(value):
    return ' '.join(re.findall(r'\w+', value.casefold())) if isinstance(value, str) else ''


def schema_nodes(value, pointer='', depth=0):
    if depth > 8:
        return
    if isinstance(value, dict):
        yield pointer, value
        graph = value.get('@graph')
        if graph is not None:
            yield from schema_nodes(graph, pointer + '/@graph', depth + 1)
    elif isinstance(value, list):
        for index, item in enumerate(value[:200]):
            yield from schema_nodes(item, pointer + '/' + str(index), depth + 1)


def parsed_date(value):
    if not isinstance(value, str):
        raise ValueError('missing_date')
    if len(value) == 10:
        return date.fromisoformat(value)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('datetime_timezone_required')
    return parsed.astimezone(timezone.utc).date()


def extract_jobs(document, number, legal_name, source_url, evidence_id, retrieved_at):
    """Publish only attributed, dated records; absence never implies zero jobs."""
    today = parsed_date(retrieved_at)
    claims, ambiguous = {}, set()
    seen = set()
    for block_index, block in enumerate(document.json_ld):
        for pointer, node in schema_nodes(block):
            types = node.get('@type')
            types = types if isinstance(types, list) else [types]
            if not any(kind in ('JobPosting', 'https://schema.org/JobPosting', 'http://schema.org/JobPosting') for kind in types):
                continue
            organization = node.get('hiringOrganization')
            if not isinstance(organization, dict) or normalized_name(organization.get('name')) != normalized_name(legal_name):
                continue
            tax_id = organization.get('taxID', organization.get('vatID'))
            if tax_id is not None and (not isinstance(tax_id, str) or re.sub(r'\D', '', tax_id) != number):
                continue
            title = node.get('title')
            if not isinstance(title, str) or not title.strip() or len(title) > 300:
                continue
            try:
                posted = parsed_date(node.get('datePosted'))
                if posted > today:
                    continue
                if 'validThrough' in node:
                    expires = parsed_date(node['validThrough'])
                    if expires < today or expires < posted:
                        continue
                value = canonical(node)
            except (ValueError, TypeError, RecursionError):
                continue
            fingerprint = hashlib.sha256(value.encode()).hexdigest()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            subject = 'jobs:' + source_url + ':' + canonical(node.get('identifier', {'title': title, 'datePosted': node['datePosted'], 'jobLocation': node.get('jobLocation')}))
            if subject in ambiguous:
                continue
            if subject in claims:
                del claims[subject]
                ambiguous.add(subject)
                continue
            claims[subject] = {'id': hashlib.sha256((number + subject + value).encode()).hexdigest(),
                'field': 'jobs', 'subject': subject, 'value': node,
                'evidence_id': evidence_id, 'json_ld_block': block_index,
                'json_pointer': pointer, 'reporting_period': None,
                'effective_date': node['datePosted'], 'extraction_method': 'json_ld_job_v1'}
    return list(claims.values())[:20]
