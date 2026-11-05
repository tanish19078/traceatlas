"""Single, dated, exact-company NewsArticle records on verified owned pages."""
import re
from urllib.parse import urlsplit, parse_qs
from .models import canonical, digest
from .jobs import schema_nodes, parsed_date, normalized_name
from .web import normalize_url, verify_site_owner, Document, ORG_PATTERN, NEWS_INDEXES


def extract_news(document, number, legal_name, source_url, evidence_id, retrieved_at):
    if verify_site_owner(document, number, legal_name) is None or len(document.article_texts) != 1:
        return []
    parsed = urlsplit(source_url)
    if (not parsed.path.strip('/')
            or parsed.path.rstrip('/').rsplit('/', 1)[-1].casefold() in NEWS_INDEXES | {'products', 'search'}
            or any(k in parse_qs(parsed.query) for k in ('q','search','query'))):
        return []
    nodes = [(block_index, pointer, node) for block_index, block in enumerate(document.json_ld)
             for pointer, node in schema_nodes(block)
             if any(kind in ('NewsArticle','https://schema.org/NewsArticle','http://schema.org/NewsArticle') for kind in (node.get('@type') if isinstance(node.get('@type'),list) else [node.get('@type')]))]
    unique = {}
    for block, pointer, node in nodes:
        unique.setdefault(canonical(node), (block, pointer, node))
    if not unique:
        return _extract_visible_article(document, number, legal_name, source_url, evidence_id, retrieved_at)
    if len(unique) != 1:
        return []
    block, pointer, node = next(iter(unique.values()))
    fallback = lambda: _extract_visible_article(
        document, number, legal_name, source_url, evidence_id, retrieved_at)
    target = node.get('url', node.get('@id'))
    if target is None or node.get('datePublished') is None:
        return fallback()
    try:
        if normalize_url(target) != normalize_url(source_url):
            return []
        posted = parsed_date(node.get('datePublished'))
        if posted > parsed_date(retrieved_at):
            return []
        if any(parsed_date(value) != posted for value in document.publication_dates):
            return []
    except (ValueError, TypeError):
        return []
    headline = node.get('headline')
    article = document.article_texts[0]
    if not isinstance(headline,str) or not 15 <= len(headline.strip()) <= 300 or normalized_name(headline) not in normalized_name(article) or len(article) < 80:
        return fallback()
    about = node.get('about')
    if about is None:
        return fallback()
    if not isinstance(about,dict) or normalized_name(about.get('legalName', about.get('name'))) != normalized_name(legal_name):
        return []
    tax_id = about.get('taxID',about.get('vatID'))
    if tax_id is not None and (not isinstance(tax_id,str) or re.sub(r'\D','',tax_id) != number):
        return []
    # Metadata alone cannot make an unrelated article about this company.
    if not re.search(r'(?<!\w)' + re.escape(normalized_name(legal_name)) + r'(?!\w)', normalized_name(article)):
        return []
    body = node.get('articleBody')
    if body is not None and (not isinstance(body,str) or normalized_name(Document(body.encode()).text) not in normalized_name(article)):
        return []
    value = canonical(node)
    subject = 'news:' + source_url
    return [{'id':digest((number + subject + value).encode()),'field':'news','subject':subject,
             'value':node,'evidence_id':evidence_id,'json_ld_block':block,'json_pointer':pointer,
             'reporting_period':None,'effective_date':node['datePublished'],
             'extraction_method':'json_ld_news_v1'}]


def _extract_visible_article(document, number, legal_name, source_url, evidence_id, retrieved_at):
    """Accept one dated, visibly attributed article when no NewsArticle schema exists."""
    if len(document.article_texts) != 1 or len(document.article_headings) != 1:
        return []
    article = document.article_texts[0]
    headline = document.article_headings[0]
    if not 15 <= len(headline) <= 300 or normalized_name(headline) not in normalized_name(article) or len(article) < 80:
        return []
    normalized_article = normalized_name(article)
    normalized_legal_name = normalized_name(legal_name)
    names_article = re.search(r'(?<!\w)' + re.escape(normalized_legal_name) + r'(?!\w)', normalized_article)
    numbers_article = any(re.sub(r'\D', '', match.group(1)) == number for match in ORG_PATTERN.finditer(article))
    if not (names_article or numbers_article):
        return []
    if len(document.article_publication_dates) > 1:
        return []
    try:
        dates = [parsed_date(value) for value in document.publication_dates + document.article_publication_dates]
        if not dates or len(set(dates)) != 1:
            return []
        posted = dates[0]
        if posted > parsed_date(retrieved_at):
            return []
    except (ValueError, TypeError):
        return []
    value = {'headline': headline, 'datePublished': posted.isoformat(), 'articleBody': article}
    subject = 'news:' + source_url
    return [{'id': digest((number + subject + canonical(value)).encode()), 'field': 'news', 'subject': subject,
             'value': value, 'evidence_id': evidence_id, 'reporting_period': None,
             'effective_date': posted.isoformat(), 'extraction_method': 'visible_html_news_v1'}]
