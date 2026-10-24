"""Navigation, product pages, feeds and parent activity are not company news."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import web, core, registry
from traceatlas.audit import verify
from traceatlas.news import extract_news
from tests.test_traceatlas import ORG, fixture
from tests.test_jobs import NAME, STAMP

URL='https://example.com/news/new-office'
HEADLINE='Synthetic company opens a new office'
BODY=NAME+' has opened a synthetic office for this test. The following account is a synthetic company announcement.'

def article(**updates):
    node={'@type':'NewsArticle','url':URL,'headline':HEADLINE,'datePublished':'2026-10-01',
          'about':{'@type':'Organization','name':NAME,'taxID':ORG},'articleBody':BODY}
    node.update(updates);return node

def page(node=None,visible=None):
    value=article() if node is None else node
    content=visible if visible is not None else f'<article><h1>{HEADLINE}</h1><p>{BODY}</p></article>'
    owner={'@type':'Organization','name':NAME,'taxID':ORG}
    return (f'<header>{NAME} Org nr {ORG}</header>'+content+'<script type="application/ld+json">'+json.dumps({'@graph':[owner,value]})+'</script>').encode()

def extract(body=None,url=URL):
    return extract_news(web.Document(body or page()),ORG,NAME,url,'hash',STAMP)

class NewsTests(unittest.TestCase):
    def test_real_dated_post_preserves_original_record_and_pointer(self):
        claim=extract()[0];self.assertEqual(claim['value'],article());self.assertEqual(claim['json_pointer'],'/@graph/1')
    def test_updated_feed_date_cannot_replace_publication(self):
        node=article();del node['datePublished'];node['dateModified']='2026-10-01'
        self.assertEqual(extract(page(node)),[])
    def test_menu_label_or_product_page_is_not_a_post(self):
        for body in [page(visible='<nav>News</nav>'),page(article(**{'@type':'Product'}))]:self.assertEqual(extract(body),[])
    def test_news_index_and_wrong_canonical_url_are_rejected(self):
        self.assertEqual(extract(url='https://example.com/news'),[])
        self.assertEqual(extract(page(article(url='https://example.com/news/another'))),[])
    def test_parent_news_and_group_article_cannot_be_subsidiary_activity(self):
        self.assertEqual(extract(page(article(about={'name':'PARENT HOLDING AS'}))),[])
        self.assertEqual(extract(page(visible=f'<article><h1>{HEADLINE}</h1><p>Parent Holding AS opened an office. '+('parent text '*20)+'</p></article>')),[])
    def test_future_invalid_and_conflicting_publication_dates_fail_closed(self):
        for value in ['2099-01-01','unknown','2026-10-01T12:00:00']:
            self.assertEqual(extract(page(article(datePublished=value))),[])
        self.assertEqual(extract(page()+b'<meta property="article:published_time" content="2026-10-02">'),[])
    def test_multiple_articles_are_a_listing(self):
        body=page().replace(b'</article>',b'</article><article>Another article</article>')
        self.assertEqual(extract(body),[])
    def test_news_export_is_auditable_and_tamper_detected(self):
        class Session:
            def __init__(self,origin,deadline):self.requests=1
            def page(self,url):
                self.requests+=1
                return f'{NAME} Org nr {ORG} <a href="/news/new-office">Story</a>'.encode() if url=='https://example.com/' else page()
        enrich=web.enrich
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=fixture(hjemmeside='example.com')),patch.object(web,'enrich',side_effect=lambda row,hosts,deadline:enrich(row,hosts,deadline,Session)):
            core.run_batch([ORG],folder,allowed_domains=['example.com'])
            self.assertTrue(verify(folder)['passed'])
            path=Path(folder)/'profiles.jsonl';row=json.loads(path.read_text())
            claim=next(c for c in row['claims'] if c['field']=='news');claim['value']['headline']='Fabricated headline'
            path.write_text(json.dumps(row)+'\n');self.assertFalse(verify(folder)['passed'])
