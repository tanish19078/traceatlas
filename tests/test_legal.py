"""Legal reporting must remain dated, entity-specific, attributed and auditable."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import core, registry, legal, web
from traceatlas.audit import verify
from tests.test_traceatlas import ORG, fixture

NAME = 'SYNTHETIC TEST COMPANY'
URL = 'https://news.example.com/report'
STAMP = '2026-10-17T00:00:00+00:00'
ENTRY = {'url': URL, 'kind': 'news', 'access_reviewed': True}

def page(text=None, date='2026-10-01'):
    text = text or f'{NAME} org.nr {ORG} reports a lawsuit, case no. ABC-123. Allegations are disputed.'
    return (f'<meta property="article:published_time" content="{date}"><p>{text}</p>').encode()

def extract(body=None, kind='news'):
    return legal.extract_report(web.Document(body or page()), ORG, NAME, URL, 'hash', STAMP, kind)

class Session:
    calls = 0
    body = page()
    def __init__(self, origin, deadline):
        Session.calls += 1
        self.requests = 1
    def page(self, url):
        self.requests += 1
        return self.body

class LegalTests(unittest.TestCase):
    def test_news_is_report_not_court_determination(self):
        claim = extract()
        self.assertEqual(claim['value']['case_reference'], 'ABC-123')
        self.assertEqual(claim['value']['interpretation'], 'source_report_only')
        self.assertIsNone(claim['value']['court_outcome'])
        self.assertEqual(claim['effective_date'], '2026-10-01')
        start,end = claim['text_span']
        self.assertEqual(web.Document(page()).text[start:end],claim['value']['reported_text'])

    def test_filing_keeps_distinct_source_kind(self):
        self.assertEqual(extract(kind='filing')['value']['source_kind'],'filing')

    def test_unrelated_parent_and_multiple_orgs_rejected(self):
        for text in [f'{NAME} HOLDING org.nr 974760673 lawsuit',
                     f'{NAME} org.nr {ORG} lawsuit; org.nr 974760673',
                     f'OTHER COMPANY org.nr {ORG} lawsuit', 'Name only lawsuit']:
            self.assertIsNone(extract(page(text)))

    def test_missing_malformed_future_or_conflicting_dates_rejected(self):
        for body in [page(date='unknown'),page(date='2099-01-01'),page(date='2026-10-01T09:00:00'),
                     page()+b'<meta property="article:published_time" content="2026-10-02">',
                     f'<p>{NAME} org.nr {ORG} lawsuit</p>'.encode()]:
            self.assertIsNone(extract(body))

    def test_json_ld_article_date_supported_without_script_identity(self):
        body=f'<p>{NAME} org.nr {ORG} lawsuit</p><script type="application/ld+json">'.encode()+json.dumps({'@graph':[{'@type':'NewsArticle','datePublished':'2026-10-01'}]}).encode()+b'</script>'
        self.assertIsNotNone(extract(body))
        self.assertIsNone(extract(b'<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle','datePublished':'2026-10-01','text':f'{NAME} org.nr {ORG} lawsuit'}).encode()+b'</script>'))

    def test_legal_term_must_be_near_identity(self):
        self.assertIsNone(extract(page(f'A lawsuit about someone else. '+('x '*600)+f'{NAME} org.nr {ORG}')))
        self.assertIsNone(extract(page(f'{NAME} org.nr {ORG} sells furniture.')))

    def test_empty_html_attributes_do_not_break_parsing(self):
        self.assertIsNotNone(extract(b'<meta property><script type></script>'+page()))

    def test_non_string_manifest_kind_has_a_clear_validation_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sources.json'
            path.write_text(json.dumps({ORG:[dict(ENTRY,kind=[])]}))
            with self.assertRaises(ValueError):legal.load_sources(path)

    def test_source_manifest_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sources.json'
            path.write_text(json.dumps({ORG:[ENTRY]}))
            self.assertEqual(legal.load_sources(path),{ORG:[ENTRY]})
            for entries in [[dict(ENTRY,access_reviewed=False)],[dict(ENTRY,url='http://localhost/x')],[ENTRY,ENTRY],[dict(ENTRY,kind='court_verdict')]]:
                path.write_text(json.dumps({ORG:entries}))
                with self.assertRaises(ValueError):legal.load_sources(path)

    def test_unallowlisted_sources_do_not_fetch(self):
        row,_=({'organisation_number':ORG,'legal_identity':{'name':NAME},'claims':[],'evidence':[],'availability':{}},None)
        with patch.object(legal,'SiteSession') as session:
            self.assertEqual(legal.enrich_legal(row,[ENTRY],[],1),[])
            session.assert_not_called()
        self.assertEqual(row['availability']['legal_cases']['state'],'blocked')

    def test_export_audit_refresh_resume_and_tamper(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()), patch.object(legal,'SiteSession',Session):
            sources={ORG:[ENTRY]}
            core.run_batch([ORG],folder,allowed_domains=['news.example.com'],legal_sources=sources)
            self.assertTrue(verify(folder)['passed'])
            path=Path(folder)/'profiles.jsonl'; row=json.loads(path.read_text())
            self.assertEqual(len([c for c in row['claims'] if c['field']=='legal_cases']),1)
            self.assertEqual(row['legal_research']['requests'],2)
            self.assertEqual(core.run_batch([ORG],folder,allowed_domains=['news.example.com'],legal_sources=sources,resume=True)['resumed_count'],1)
            with self.assertRaisesRegex(ValueError,'configuration_changed'):
                core.run_batch([ORG],folder,allowed_domains=['news.example.com'],legal_sources={},resume=True)
            claim=next(c for c in row['claims'] if c['field']=='legal_cases');claim['value']['court_outcome']='guilty';path.write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])
            core.run_batch([ORG],folder)
            row=json.loads(path.read_text());self.assertTrue(any(c['field']=='legal_cases' for c in row['last_known']['claims']))
            self.assertTrue(verify(folder)['passed'])

    def test_fixture_mode_refuses_network_legal_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'fixture mode'):
                core.run_batch([ORG],folder,fixture_dir=folder,legal_sources={ORG:[ENTRY]})

    def test_blocked_and_failed_sources_remain_explicit(self):
        row={'organisation_number':ORG,'legal_identity':{'name':NAME},'claims':[],'evidence':[],'availability':{}}
        with patch.object(legal,'SiteSession',side_effect=web.AccessError('robots_disallowed')):
            legal.enrich_legal(row,[ENTRY],['news.example.com'],1)
        self.assertEqual(row['availability']['legal_cases']['state'],'blocked')
        self.assertNotIn('no cases',row['availability']['legal_cases']['reason'])
