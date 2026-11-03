"""Opt-in Brave Search candidate discovery; results are never company facts."""
from __future__ import annotations
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .network import rate_limited, take_request

ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'
MAX_RESPONSE_BYTES = 1_000_000
LIST_PRICE_USD_PER_QUERY = 0.005
SOCIAL_HOSTS = {'facebook.com', 'instagram.com', 'linkedin.com', 'x.com', 'twitter.com', 'youtube.com'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(query, api_key, timeout, transport=None, on_request=None, on_success=None):
    url = ENDPOINT + '?' + urllib.parse.urlencode({
        'q': query, 'country': 'NO', 'search_lang': 'no', 'count': 10,
        'safesearch': 'moderate',
    })
    take_request(url)
    if on_request:
        on_request()
    if transport is not None:
        status, headers, body = transport(url, api_key, timeout)
    else:
        request = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            'User-Agent': 'TraceAtlas/0.6 (+https://github.com/tanish19078/traceatlas)',
            'X-Subscription-Token': api_key,
        })
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                rate_limited(url, exc.headers.get('Retry-After') if exc.headers else None)
            raise
        with response:
            status = response.status
            headers = response.headers
            body = response.read(MAX_RESPONSE_BYTES + 1)
    if status == 429:
        rate_limited(url, headers.get('Retry-After') if headers else None)
        raise ValueError('search_rate_limited')
    if status != 200:
        raise ValueError('search_http_' + str(status))
    if on_success:
        on_success()
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError('search_response_size_limit')
    return json.loads(body)


def discover_candidates(result, api_key, timeout=8, transport=None):
    """Search a company and town, returning URLs only for identity-gated fetching."""
    result['search_research'] = {
        'provider': 'brave', 'queries': 0, 'successful_queries': 0,
        'candidates': 0, 'errors': [],
    }
    address = next((claim.get('value') for claim in result.get('claims', [])
                    if claim.get('field') == 'registered_address'), {})
    town = ''
    if isinstance(address, dict):
        town = address.get('poststed') or address.get('kommune') or ''
    query = '"' + result['legal_identity']['name'].strip() + '"'
    if town:
        query += ' ' + str(town).strip()

    from .web import normalize_url
    from urllib.parse import urlsplit
    seen = {(item.get('kind'), item.get('value')) for item in result.get('candidates', [])
            if isinstance(item, dict)}
    seen_hosts = set()
    for candidate in result.get('candidates', []):
        if not isinstance(candidate, dict) or candidate.get('kind') != 'website' or not isinstance(candidate.get('value'), str):
            continue
        try:
            seen_hosts.add(urlsplit(normalize_url(candidate['value'])).hostname)
        except ValueError:
            continue

    queries = [query]
    social_found = any(kind == 'social_page' for kind, _ in seen)
    social_query_added = False
    while queries:
        current = queries.pop(0)

        def mark_request():
            result['search_research']['queries'] += 1

        def mark_success():
            result['search_research']['successful_queries'] += 1

        try:
            data = _fetch(current, api_key, timeout, transport, mark_request, mark_success)
            web = data.get('web', {}) if isinstance(data, dict) else {}
            search_results = web.get('results', []) if isinstance(web, dict) else []
            if not isinstance(search_results, list):
                raise ValueError('invalid_search_response')
            for item in search_results:
                if not isinstance(item, dict) or not isinstance(item.get('url'), str):
                    continue
                try:
                    url = normalize_url(item['url'])
                except ValueError:
                    continue
                host = urlsplit(url).hostname
                root_host = host[4:] if host.startswith('www.') else host
                kind = 'social_page' if root_host in SOCIAL_HOSTS else 'website'
                if kind == 'website' and host in seen_hosts:
                    continue
                key = (kind, url)
                if key in seen:
                    continue
                seen.add(key)
                if kind == 'website':
                    seen_hosts.add(host)
                else:
                    social_found = True
                result.setdefault('candidates', []).append({
                    'kind': kind, 'value': url, 'status': 'discovered',
                    'discovery_source': 'web_search',
                })
                result['search_research']['candidates'] += 1
        except urllib.error.HTTPError as exc:
            result['search_research']['errors'].append('search_http_' + str(exc.code))
        except (OSError, ValueError, TypeError) as exc:
            message = str(exc)
            known = re.fullmatch(r'search_(?:http_\d{3}|rate_limited|response_size_limit|invalid_search_response)', message)
            budget_error = message in {'deadline_exhausted', 'global_request_budget_exhausted', 'host_rate_limited'}
            result['search_research']['errors'].append(message if known or budget_error else type(exc).__name__)
        if not queries and not social_found and result['search_research']['successful_queries'] and not social_query_added:
            social_query_added = True
            queries.append(query + ' Facebook Instagram LinkedIn')
    return result.get('candidates', [])
