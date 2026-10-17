"""Fetch reviewed news/filing URLs and preserve attributed legal reporting.

A detected mention is a report by its source, never a liability determination.
Discovery is deliberately separate: search snippets cannot become case evidence.
"""
import json
import re
import http.client
from pathlib import Path
from urllib.parse import urlsplit
from .models import canonical, digest, now, valid_org
from .web import Document, SiteSession, AccessError, normalize_url, verify_identity
from .jobs import parsed_date, schema_nodes

KINDS = {'news': 'legal_news_report', 'filing': 'legal_filing_report'}
LEGAL = re.compile(r'\b(?:lawsuit|litigation|sued|court proceedings|court case|legal proceedings|søksmål|rettssak|saksnummer)\b', re.I)
CASE = re.compile(r'\b(?:case\s+(?:no\.?|number)|saksnummer)\s*[:#]?\s*([A-Z0-9][A-Z0-9./-]{2,79})', re.I)


def load_sources(path):
    """Require an explicit access review, exact company number and bounded URLs."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or len(data) > 10000:
        raise ValueError('legal_sources_must_be_company_map')
    result = {}
    for number, entries in data.items():
        if not valid_org(number) or not isinstance(entries, list) or len(entries) > 5:
            raise ValueError('invalid_legal_source_company_or_limit')
        seen, accepted = set(), []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get('kind') not in KINDS or entry.get('access_reviewed') is not True:
                raise ValueError('legal_source_requires_kind_and_access_review')
            url = normalize_url(entry.get('url'))
            if url in seen:
                raise ValueError('duplicate_legal_source_url')
            seen.add(url)
            accepted.append({'url': url, 'kind': entry['kind'], 'access_reviewed': True})
        result[number] = accepted
    return result


def publication_date(document, retrieved_at):
    """Conflicting or future publication dates fail closed; no inferred dates."""
    values = list(document.publication_dates)
    for block in document.json_ld:
        for _, node in schema_nodes(block):
            kinds = node.get('@type', [])
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(kind in ('Article', 'NewsArticle', 'Report', 'https://schema.org/NewsArticle', 'https://schema.org/Article') for kind in kinds) and 'datePublished' in node:
                values.append(node['datePublished'])
    try:
        dates = [parsed_date(value) for value in values]
        cutoff = parsed_date(retrieved_at)
    except (ValueError, TypeError):
        return None
    if not dates or any(value is None for value in dates) or len(set(dates)) != 1 or cutoff is None or dates[0] > cutoff:
        return None
    return dates[0].isoformat()


def extract_report(document, number, legal_name, url, evidence_id, retrieved_at, kind):
    proof = verify_identity(document, number, legal_name)
    published = publication_date(document, retrieved_at)
    if kind not in KINDS or proof is None or published is None:
        return None
    # A distant footer identity cannot attribute an unrelated litigation story.
    start, end = max(0, proof[0]-450), min(len(document.text), proof[1]+450)
    passage = document.text[start:end]
    if not LEGAL.search(passage):
        return None
    reference = CASE.search(passage)
    value = {'reported_text': passage, 'case_reference': reference.group(1).rstrip('.-/') if reference else None,
             'source_kind': kind, 'published_at': published, 'interpretation': 'source_report_only',
             'court_outcome': None}
    subject = 'legal_cases:' + url
    return {'id': digest((number + subject + canonical(value)).encode()), 'field': 'legal_cases',
            'subject': subject, 'value': value, 'evidence_id': evidence_id, 'text_span': [start, end],
            'reporting_period': None, 'effective_date': published, 'extraction_method': 'legal_report_v1'}


def enrich_legal(result, entries, allowed_domains, deadline, session_factory=None):
    """Only reviewed, allowlisted HTML; shared DNS, TLS, robots and rate guards."""
    factory = session_factory or SiteSession
    blobs, claims, evidence, states = [], [], [], []
    number = result['organisation_number']
    name = result['legal_identity']['name']
    details = {'requests': 0, 'sources_checked': 0, 'reports_found': 0, 'errors': []}
    sessions = {}
    for entry in entries:
        host = None
        try:
            url = normalize_url(entry['url'])
            host = urlsplit(url).hostname
            if entry.get('access_reviewed') is not True or entry['kind'] not in KINDS or host not in allowed_domains:
                raise AccessError('legal_source_not_reviewed_or_allowlisted')
            if host not in sessions:
                sessions[host] = factory('https://' + host + '/', deadline)
            body = sessions[host].page(url)
            details['sources_checked'] += 1
            doc = Document(body)
            key, stamp = digest(body), now()
            claim = extract_report(doc, number, name, url, key, stamp, entry['kind'])
            if claim is None:
                states.append('ambiguous' if verify_identity(doc, number, name) is None else 'not_available')
                continue
            # A content-addressed source ID has a single URL. Preserve the first
            # attribution instead of silently overwriting aliases of one body.
            if key in {e['id'] for e in result['evidence'] + evidence}:
                details['errors'].append('duplicate_snapshot_source_skipped')
                continue
            evidence.append({'id': key, 'source_url': url, 'retrieved_at': stamp,
                'content_sha256': key, 'snapshot_path': 'snapshots/' + key + '.html',
                'source_class': KINDS[entry['kind']], 'extractor_version': 'legal_report_v1',
                'identity_span': verify_identity(doc, number, name), 'legal_name': name,
                'organisation_number': number, 'synthetic': False,
                'access_policy': 'reviewed_domain_allowlist_and_robots'})
            claims.append(claim); blobs.append((body, '.html')); states.append('available')
        except (AccessError, OSError, ValueError, http.client.HTTPException) as exc:
            # Never publish arbitrary remote error text or credentials.
            states.append('blocked' if isinstance(exc, AccessError) and str(exc) in (
                'robots_disallowed', 'robots_unavailable', 'source_blocked',
                'legal_source_not_reviewed_or_allowlisted') else 'failed')
            details['errors'].append(str(exc) if isinstance(exc, AccessError) else type(exc).__name__)
            details['requests'] += getattr(exc, 'requests', 0) if host not in sessions else 0
    details['requests'] += sum(session.requests for session in sessions.values())
    details['reports_found'] = len(claims)
    result['claims'].extend(claims); result['evidence'].extend(evidence)
    # Missing reports never mean no litigation; list partial source failures.
    state = next((s for s in ('available', 'failed', 'blocked', 'ambiguous', 'not_available') if s in states), 'not_available')
    result['availability']['legal_cases'] = {'state': state, 'reason': 'attributed_source_reports_only; no inference of liability or absence of cases'}
    result['legal_research'] = details
    return blobs
