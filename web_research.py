"""Opt-in public website research with exact-entity publication gates."""
from __future__ import annotations
import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = 'TraceAtlas'
MAX_BYTES = 1_000_000
ORG_PATTERN = re.compile(r'\b(?:organisasjonsnummer|organisasjonsnr|org\.?\s*(?:nr|nummer)\.?)\s*[:.]?\s*(\d{3}[ .]?\d{3}[ .]?\d{3})(?!\d)', re.I)
PRIORITIES = ('kontakt', 'contact', 'om-oss', 'about', 'karriere', 'careers', 'jobs', 'nyheter', 'news')
_HOSTS = {}
_HOSTS_LOCK = threading.Lock()


class AccessError(ValueError):
    pass


def normalize_url(value):
    if not isinstance(value, str) or not value.strip():
        raise AccessError('missing_url')
    value = value.strip()
    if '://' not in value:
        value = 'https://' + value
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise AccessError('https_public_urls_only')
    host = (parsed.hostname or '').encode('idna').decode('ascii').lower().rstrip('.')
    if not host or any(ord(c) < 33 for c in value) or '%' in host or '\\' in value:
        raise AccessError('invalid_url')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise AccessError('ip_literals_not_allowed')
    if '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.invalid')):
        raise AccessError('non_public_hostname')
    return urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))


def public_addresses(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise AccessError('non_public_address')
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connect to the checked DNS answer while preserving TLS hostname checks."""
    def connect(self):
        addresses = public_addresses(self.host)
        family, kind, protocol, _, address = addresses[0]
        raw = socket.socket(family, kind, protocol)
        try:
            raw.settimeout(self.timeout)
            raw.connect(address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def get_page(url, deadline):
    url = normalize_url(url)
    parsed = urlsplit(url)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AccessError('deadline_exhausted')
    context = ssl.create_default_context()
    context.set_alpn_protocols(['http/1.1'])
    conn = PinnedHTTPS(parsed.hostname, timeout=min(8, remaining), context=context)
    try:
        path = parsed.path + ('?' + parsed.query if parsed.query else '')
        conn.request('GET', path, headers={'User-Agent': USER_AGENT + '/0.2 (+https://github.com/tanish19078/traceatlas)', 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        content = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AccessError('deadline_exhausted')
            if conn.sock:
                conn.sock.settimeout(min(8, remaining))
            chunk = response.read1(min(65536, MAX_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise AccessError('response_size_limit')
        return response.status, response.getheader('Content-Type', ''), bytes(content)
    finally:
        conn.close()


class Document(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden = [], [], 0
        self.feed(body.decode('utf-8', errors='replace'))
        self.text = ' '.join(' '.join(self.parts).split())

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'template'):
            self.hidden += 1
        if tag == 'a' and not self.hidden:
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'template'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def normalize_name(value):
    return ' '.join(re.findall(r'\w+', value.casefold()))


def verify_identity(document, number, legal_name):
    matches = list(ORG_PATTERN.finditer(document.text))
    numbers = {re.sub(r'\D', '', match.group(1)) for match in matches}
    if numbers != {number}:
        return None
    for match in matches:
        neighborhood = document.text[max(0, match.start()-400):match.end()+400]
        # Exact legal-name token sequence is required in the same local context.
        name = normalize_name(legal_name)
        if not name or not re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', normalize_name(neighborhood)):
            continue
        return [match.start(), match.end()]
    return None


class SiteSession:
    def __init__(self, origin, deadline, request_limit=5, transport=get_page):
        self.origin, self.deadline, self.limit, self.transport = origin, deadline, request_limit, transport
        self.requests, self.last_request = 0, 0.0
        host = urlsplit(origin).hostname
        with _HOSTS_LOCK:
            self.gate = _HOSTS.setdefault(host, [threading.Lock(), 0.0, 1.0])
        self.parser = RobotFileParser()
        self.delay = 1.0
        status, _, body = self._get(urljoin(origin, '/robots.txt'))
        if status == 404:
            self.parser.parse(['User-agent: *', 'Disallow:'])
        elif status == 200:
            self.parser.parse(body.decode('utf-8', errors='replace').splitlines())
        else:
            error = AccessError('robots_unavailable')
            error.requests = self.requests
            raise error
        self.delay = max(1.0, float(self.parser.crawl_delay(USER_AGENT) or 0))
        rate = self.parser.request_rate(USER_AGENT)
        if rate and rate.requests > 0:
            self.delay = max(self.delay, rate.seconds / rate.requests)

    def _get(self, url):
        if self.requests >= self.limit:
            raise AccessError('request_budget_exhausted')
        # Serialize all requests to one host across batch workers. The strictest
        # observed robots delay remains in effect for the process lifetime.
        with self.gate[0]:
            self.gate[2] = max(self.gate[2], self.delay)
            wait = max(0, self.gate[2] - (time.monotonic() - self.gate[1]))
            if time.monotonic() + wait >= self.deadline:
                raise AccessError('deadline_exhausted')
            if wait:
                time.sleep(wait)
            self.requests += 1
            self.last_request = self.gate[1] = time.monotonic()
            try:
                return self.transport(url, self.deadline)
            except Exception as exc:
                exc.requests = self.requests
                raise

    def page(self, url):
        url = normalize_url(url)
        if urlsplit(url).netloc != urlsplit(self.origin).netloc:
            raise AccessError('cross_domain_url')
        if not self.parser.can_fetch(USER_AGENT, url):
            raise AccessError('robots_disallowed')
        status, mime, body = self._get(url)
        if status in (301,302,303,307,308):
            raise AccessError('redirect_requires_new_candidate')
        if status in (401,403,429):
            raise AccessError('source_blocked')
        if status != 200 or 'text/html' not in mime:
            raise AccessError('html_unavailable')
        return body


def enrich(result, allowed_domains, deadline, session_factory=SiteSession):
    """Research registry website candidates only on explicitly reviewed domains."""
    blobs = []
    result['website_research'] = {'requests': 0, 'pages_verified': 0, 'errors': []}
    number = result['organisation_number']
    legal_name = result['legal_identity']['name']
    session = None
    try:
        candidates = [candidate for candidate in result['candidates'] if candidate['kind'] == 'website']
        if not candidates:
            return blobs
        url = normalize_url(candidates[0]['value'])
        host = urlsplit(url).hostname
        if host not in allowed_domains:
            result['website_research']['errors'].append('domain_not_in_reviewed_allowlist')
            return blobs
        session = session_factory(url, deadline)
        body = session.page(url)
        document = Document(body)
        proof = verify_identity(document, number, legal_name)
        if not proof:
            result['availability']['website_identity'] = {'state': 'ambiguous', 'reason': 'exact_entity_proof_not_found'}
            return blobs
        candidates[0]['status'] = 'verified'
        pages = [(url, body, document, proof)]
        seen = {url}
        for href in document.links:
            if len(seen) >= 5:
                break
            if len(pages) >= 3:
                break
            if not any(keyword in href.casefold() for keyword in PRIORITIES):
                continue
            try:
                candidate = normalize_url(urljoin(url, href))
                if candidate in seen or urlsplit(candidate).netloc != host:
                    continue
                seen.add(candidate)
                page_body = session.page(candidate)
                page_doc = Document(page_body)
                page_proof = verify_identity(page_doc, number, legal_name)
                if page_proof:
                    pages.append((candidate, page_body, page_doc, page_proof))
            except (AccessError, OSError, ValueError, http.client.HTTPException) as exc:
                result['website_research']['errors'].append(str(exc) if isinstance(exc, AccessError) else type(exc).__name__)
        evidence_ids = {item['id'] for item in result['evidence']}
        for page_url, page_body, page_doc, page_proof in pages:
            key = hashlib.sha256(page_body).hexdigest()
            if key in evidence_ids:
                continue
            evidence_ids.add(key)
            evidence = {'id': key, 'source_url': page_url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                        'content_sha256': key, 'snapshot_path': 'snapshots/' + key + '.html',
                        'source_class': 'verified_company_website', 'extractor_version': 'visible_text_v1',
                        'identity_span': page_proof, 'synthetic': False,
                        'access_policy': 'reviewed_domain_allowlist_and_robots'}
            result['evidence'].append(evidence)
            blobs.append((page_body, '.html'))
            # Publish a directly inspectable identity passage, not inferred job or
            # financial values. Specialized structured extractors come later.
            start, end = max(0, page_proof[0]-150), min(len(page_doc.text), page_proof[1]+150)
            value = page_doc.text[start:end]
            field = 'website_identity' if page_url == url else 'company_page'
            result['claims'].append({'id': hashlib.sha256((number+field+page_url+value).encode()).hexdigest(),
                'field': field, 'subject': field + ':' + page_url, 'value': value, 'evidence_id': key,
                'text_span': [start, end], 'reporting_period': None, 'effective_date': None,
                'extraction_method': 'visible_text_v1'})
            result['availability'][field] = {'state': 'available'}
            result['website_research']['pages_verified'] += 1
        result['summary'] = legal_name + ': registry identity and company website verified. Inspect the linked passages for support.'
    except (AccessError, OSError, ValueError, http.client.HTTPException) as exc:
        reason = str(exc) if isinstance(exc, AccessError) else type(exc).__name__
        blocked = {'robots_disallowed', 'robots_unavailable', 'source_blocked', 'cross_domain_url', 'non_public_address', 'redirect_requires_new_candidate'}
        state = 'blocked' if reason in blocked else 'not_available' if reason == 'html_unavailable' else 'failed'
        result['availability']['website_identity'] = {'state': state, 'reason': reason}
        result['website_research']['errors'].append(type(exc).__name__)
        result['website_research']['requests'] = getattr(exc, 'requests', 0)
    finally:
        if session:
            result['website_research']['requests'] = session.requests
    return blobs
