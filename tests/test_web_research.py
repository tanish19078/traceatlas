"""Offline adversarial tests; no website requests or real-company claims."""
import socket
import time
import unittest
from unittest.mock import patch, MagicMock
import traceatlas.core as t
import traceatlas.registry as registry
import traceatlas.web as w
from tests.test_traceatlas import ORG, fixture

HOST = 'example.com'
URL = 'https://example.com/'
PAGE = b'<html><body>SYNTHETIC TEST COMPANY Org. nr. 923 609 016 <a href="/contact">Contact</a></body></html>'


def result():
    with patch.object(registry, 'fetch', return_value=fixture(hjemmeside=HOST)):
        return t.research(ORG)[0]


class FakeSession:
    def __init__(self, origin, deadline):
        self.requests = 1
    def page(self, url):
        self.requests += 1
        return PAGE if url == URL else PAGE.replace(b'Contact', b'Contact office')


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        w._HOSTS.clear()
        self.sleeper = patch.object(w.time, 'sleep')
        self.sleeper.start()
        self.addCleanup(self.sleeper.stop)

    def test_normalization_rejects_unsafe_targets(self):
        for url in ['http://example.com', 'https://localhost', 'https://127.0.0.1',
                    'https://[::1]', 'https://foo.local', 'https://user:pass@example.com',
                    'https://example.com:8080', 'https://example.com\\@localhost',
                    'https://exam\nple.com']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                w.normalize_url(url)
        self.assertEqual(w.normalize_url('EXAMPLE.COM/#fragment'), URL)

    def test_private_or_mixed_dns_answers_rejected(self):
        for addresses in [[('127.0.0.1',443)], [('93.184.216.34',443),('10.1.1.1',443)]]:
            answers = [(socket.AF_INET,socket.SOCK_STREAM,6,'',a) for a in addresses]
            with patch.object(socket,'getaddrinfo',return_value=answers), self.assertRaises(w.AccessError):
                w.public_addresses(HOST)

    def test_checked_ip_is_pinned_with_original_tls_name(self):
        address = ('93.184.216.34',443)
        context, raw = MagicMock(), MagicMock()
        conn = w.PinnedHTTPS(HOST, timeout=2, context=context)
        with patch.object(w,'public_addresses',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',address)]), patch.object(socket,'socket',return_value=raw):
            conn.connect()
        raw.connect.assert_called_once_with(address)
        context.wrap_socket.assert_called_once_with(raw, server_hostname=HOST)

    def test_identity_requires_exact_number_and_legal_name(self):
        self.assertIsNotNone(w.verify_identity(w.Document(PAGE),ORG,'SYNTHETIC TEST COMPANY'))
        for page in [PAGE.replace(b'923 609 016',b'974 760 673'),
                     PAGE.replace(b'SYNTHETIC TEST COMPANY',b'UNRELATED COMPANY'),
                     b'<script>SYNTHETIC TEST COMPANY Org nr 923609016</script>',
                     PAGE + b' Other Company Org nr 974760673']:
            self.assertIsNone(w.verify_identity(w.Document(page),ORG,'SYNTHETIC TEST COMPANY'))

    def test_name_boundary_rejects_partial_word(self):
        self.assertIsNone(w.verify_identity(w.Document(PAGE), ORG, 'TEST COMP'))

    def test_robots_disallow_prevents_page_request(self):
        transport = MagicMock(return_value=(200,'text/plain',b'User-agent: *\nDisallow: /'))
        session = w.SiteSession(URL,time.monotonic()+10,transport=transport)
        with self.assertRaisesRegex(w.AccessError,'robots_disallowed'):
            session.page(URL)
        self.assertEqual(transport.call_count,1)

    def test_cross_domain_and_redirect_are_not_followed(self):
        transport = MagicMock(side_effect=[(404,'text/plain',b''),(302,'text/html',b'')])
        session = w.SiteSession(URL,time.monotonic()+10,transport=transport)
        session.last_request = 0
        with self.assertRaisesRegex(w.AccessError,'cross_domain'):
            session.page('https://other.example.com/')
        with self.assertRaisesRegex(w.AccessError,'redirect'):
            session.page(URL)
        self.assertEqual(transport.call_count,2)

    def test_request_and_time_budgets_stop_requests(self):
        transport = MagicMock(return_value=(404,'text/plain',b''))
        session = w.SiteSession(URL,time.monotonic()+10,request_limit=1,transport=transport)
        session.last_request = 0
        with self.assertRaisesRegex(w.AccessError,'request_budget'):
            session.page(URL)
        session.limit = 2
        session.deadline = time.monotonic()-1
        with self.assertRaisesRegex(w.AccessError,'deadline'):
            session.page(URL)
        self.assertEqual(transport.call_count,1)

    def test_site_session_allows_robots_plus_five_verified_pages(self):
        def transport(url,deadline):
            return (404,'text/plain',b'') if url.endswith('/robots.txt') else (200,'text/html',PAGE)
        session=w.SiteSession(URL,time.monotonic()+30,transport=transport)
        for _ in range(5):
            session.page(URL)
        self.assertEqual(session.requests,6)
        with self.assertRaisesRegex(w.AccessError,'request_budget'):
            session.page(URL)

    def test_workers_share_host_pacing_gate(self):
        transport = MagicMock(return_value=(404,'text/plain',b''))
        one = w.SiteSession(URL,time.monotonic()+10,transport=transport)
        two = w.SiteSession(URL,time.monotonic()+10,transport=transport)
        self.assertIs(one.gate,two.gate)
        self.assertTrue(w.time.sleep.called)

    def test_allowlist_blocks_before_creating_session(self):
        row = result()
        factory = MagicMock()
        self.assertEqual(w.enrich(row,[],time.monotonic()+10,factory),[])
        factory.assert_not_called()
        self.assertEqual(row['candidates'][0]['status'],'unverified')

    def test_verified_pages_have_exact_supporting_spans(self):
        row = result()
        blobs = w.enrich(row,[HOST],time.monotonic()+10,FakeSession)
        self.assertEqual(row['website_research']['pages_verified'],2)
        self.assertEqual(row['candidates'][0]['status'],'verified')
        sources = {t.digest(body):w.Document(body).text for body,_ in blobs}
        for claim in row['claims']:
            if 'text_span' in claim:
                start,end = claim['text_span']
                self.assertEqual(claim['value'],sources[claim['evidence_id']][start:end])
        self.assertEqual(row['availability']['jobs']['state'],'not_available')

    def test_unverified_page_publishes_no_website_claims(self):
        class Wrong(FakeSession):
            def page(self,url):
                return b'SYNTHETIC TEST COMPANY Org nr 974760673'
        row = result()
        self.assertEqual(w.enrich(row,[HOST],time.monotonic()+10,Wrong),[])
        self.assertEqual(row['availability']['website_identity']['state'],'ambiguous')
        self.assertEqual(len(row['evidence']),1)

    def test_opt_in_name_domain_probe_requires_exact_identity(self):
        class Discovered(FakeSession):
            def page(self, url):
                return b'<h1>SYNTHETIC TEST COMPANY</h1><p>Org nr 923609016. Local company details.</p>'
        with patch.object(registry, 'fetch', return_value=fixture(hjemmeside='')):
            row = t.research(ORG)[0]
        blobs = w.enrich(row, [], time.monotonic()+10, Discovered, discover=True)
        self.assertEqual(len(blobs), 1)
        self.assertEqual(row['candidates'][0]['value'], 'www.synthetictestcompany.no')
        self.assertEqual(row['candidates'][0]['status'], 'verified')
        self.assertEqual(row['availability']['website_identity']['state'], 'available')

    def test_search_discovered_customer_mention_is_not_site_ownership(self):
        class Mention(FakeSession):
            def page(self,url):
                return b'<h1>Vendor directory</h1><p>Our customer SYNTHETIC TEST COMPANY uses this service.</p>'
        with patch.object(registry,'fetch',return_value=fixture(hjemmeside='')):
            row=t.research(ORG)[0]
        row['candidates'].append({'kind':'website','value':URL,'status':'discovered',
                                  'discovery_source':'web_search'})
        self.assertEqual(w.enrich(row,[],time.monotonic()+10,Mention,discover=True),[])
        self.assertEqual(row['candidates'][0]['status'],'rejected')
        self.assertFalse(any(claim['field']=='website_identity' for claim in row['claims']))

    def test_search_discovered_social_page_is_checked_without_a_website(self):
        class Discovered(FakeSession):
            def page(self, url):
                return PAGE if 'facebook.com' in url else b'Unrelated company details'
        with patch.object(registry, 'fetch', return_value=fixture(hjemmeside='')):
            row = t.research(ORG)[0]
        row['candidates'].append({'kind': 'social_page', 'value': 'https://www.facebook.com/example', 'status': 'discovered'})
        blobs = w.enrich(row, [], time.monotonic()+10, Discovered, discover=True)
        self.assertEqual(len(blobs), 1)
        self.assertEqual(row['candidates'][0]['status'], 'verified')
        self.assertEqual(row['availability']['social_pages']['state'], 'available')

    def test_social_identity_rejects_conflicting_company_numbers(self):
        exact_heading=b'<h1>SYNTHETIC TEST COMPANY</h1>'
        self.assertIsNotNone(w.verify_social_identity(w.Document(exact_heading),ORG,'SYNTHETIC TEST COMPANY'))
        for page in [
            PAGE+b' Other Company Org nr 974760673',
            exact_heading+b' Other Company Org nr 974760673',
        ]:
            self.assertIsNone(w.verify_social_identity(w.Document(page),ORG,'SYNTHETIC TEST COMPANY'))

    def test_unverified_child_does_not_inherit_root_identity(self):
        class Child(FakeSession):
            def page(self,url):
                return PAGE if url == URL else b'Unrelated holding company careers'
        row = result()
        self.assertEqual(len(w.enrich(row,[HOST],time.monotonic()+10,Child)),1)
        self.assertEqual(row['website_research']['pages_verified'],1)

    def test_news_index_cannot_starve_careers_detail(self):
        news='https://example.com/news'
        careers='https://example.com/careers'
        job='https://example.com/jobs/synthetic-engineer'
        story='https://example.com/news/story-0'
        root=PAGE.replace(
            b'<a href="/contact">Contact</a>',
            b'<a href="/news">News</a><a href="/careers">Careers</a>',
        )
        news_links=b''.join(
            b'<a href="/news/story-'+str(index).encode()+b'">Story</a>'
            for index in range(30)
        )
        calls=[]
        class Balanced(FakeSession):
            def page(self,url):
                self.requests+=1;calls.append(url)
                if url == URL:return root
                if url == news:return PAGE+news_links
                if url == careers:return PAGE.replace(b'/contact',b'/jobs/synthetic-engineer')
                return PAGE
        row=result()
        w.enrich(row,[HOST],time.monotonic()+10,Balanced)
        self.assertEqual(calls[:3],[URL,news,careers])
        self.assertIn(story,calls)
        self.assertIn(job,calls)
        self.assertEqual(len(calls),5)

    def test_unverified_careers_index_is_not_expanded(self):
        calls=[]
        class WrongCareers(FakeSession):
            def page(self,url):
                self.requests+=1;calls.append(url)
                if url == URL:return PAGE.replace(b'/contact',b'/careers')
                if url.endswith('/careers'):
                    return b'<h1>UNRELATED COMPANY</h1><a href="/jobs/synthetic-engineer">Role</a>'
                return PAGE
        row=result()
        w.enrich(row,[HOST],time.monotonic()+10,WrongCareers)
        self.assertEqual(calls,[URL,'https://example.com/careers'])


class WebsiteIntegrationTests(unittest.TestCase):
    def test_company_site_description_flows_to_summary_and_audit(self):
        import tempfile
        import json
        from pathlib import Path
        from traceatlas.audit import verify
        class Described(FakeSession):
            def page(self,url):
                if url == URL:
                    return f'<h1>SYNTHETIC TEST COMPANY</h1><p>Org nr {ORG}</p><meta name="description" content="We provide commercial plumbing and heating services across western Norway for homes and businesses."><a href="/contact">Contact</a>'.encode()
                return PAGE
        enrich=w.enrich
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture(hjemmeside=HOST)), patch.object(w,'enrich',side_effect=lambda row,domains,deadline: enrich(row,domains,deadline,Described)):
            t.run_batch([ORG],folder,allowed_domains=[HOST])
            row=json.loads((Path(folder)/'profiles.jsonl').read_text())
            self.assertIn('Company website: We provide commercial plumbing',row['summary'])
            self.assertIn('HTML meta description',(Path(folder)/'index.html').read_text())
            self.assertTrue(verify(folder)['passed'])
            claim=next(item for item in row['claims'] if item['field']=='company_description')
            claim['value']='Fabricated company activity.'
            (Path(folder)/'profiles.jsonl').write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])

    def test_batch_saves_and_audits_html_and_rejects_tampering(self):
        import tempfile
        from pathlib import Path
        from traceatlas.audit import verify
        enrich = w.enrich
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture(hjemmeside=HOST)), patch.object(w,'enrich',side_effect=lambda row,domains,deadline: enrich(row,domains,deadline,FakeSession)):
            report = t.run_batch([ORG],folder,allowed_domains=[HOST])
            self.assertEqual(report['website_pages_verified'],2)
            self.assertTrue(verify(folder)['passed'])
            self.assertEqual(len(list((Path(folder)/'snapshots').glob('*.html'))),2)
            self.assertIn('Text span:',(Path(folder)/'index.html').read_text())
            path = Path(folder)/'profiles.jsonl'
            row = __import__('json').loads(path.read_text())
            row['claims'][-1]['value'] = 'Invented website claim'
            path.write_text(__import__('json').dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])

    def test_partial_refresh_preserves_prior_website_evidence_as_stale(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            store = t.Store(folder)
            try:
                first = result()
                pages = w.enrich(first,[HOST],time.monotonic()+10,FakeSession)
                store.save(first,[(fixture(hjemmeside=HOST),'.json')]+pages)
                second = store.save(result(),fixture(hjemmeside=HOST))
                self.assertEqual(len(second['last_known']['claims']),2)
                self.assertFalse(any('text_span' in c for c in second['claims']))
                self.assertEqual(second['refresh']['changes'],[])
                third = store.save(result(),fixture(hjemmeside=HOST))
                self.assertEqual(third['last_known']['claims'],second['last_known']['claims'])
            finally:
                store.close()

    def test_fixture_mode_cannot_make_external_requests(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder, patch.object(w,'enrich') as enrich:
            (Path(folder)/(ORG+'.json')).write_bytes(fixture(hjemmeside=HOST))
            t.run_batch([ORG],Path(folder)/'out',fixture_dir=folder,allowed_domains=[HOST])
        enrich.assert_not_called()

if __name__ == '__main__':
    unittest.main()
