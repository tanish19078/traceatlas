"""Search API candidates stay untrusted until a source page proves identity."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from traceatlas import core
from traceatlas.search import discover_candidates
import traceatlas.registry as registry
import traceatlas.web as web
from tests.test_traceatlas import ORG, fixture
from tests.test_web_research import FakeSession


class SearchTests(unittest.TestCase):
    def make_result(self):
        return {
            'organisation_number': '923609016',
            'legal_identity': {'name': 'Example AS'},
            'claims': [{'field': 'registered_address', 'value': {'poststed': 'Oslo'}}],
            'candidates': [],
        }

    def test_search_queries_name_and_town_and_keeps_candidate_urls_only(self):
        result = self.make_result()
        payload = {'web': {'results': [
            {'title': 'Company website', 'url': 'https://www.example.no/'},
            {'title': 'Company social', 'url': 'https://www.facebook.com/example-company'},
            {'title': 'Duplicate host page', 'url': 'https://www.example.no/about'},
            {'title': 'Unsafe target', 'url': 'http://127.0.0.1/admin'},
        ]}}
        calls = []

        def transport(url, key, timeout):
            calls.append((url, key, timeout))
            return 200, {}, json.dumps(payload).encode()

        with patch('traceatlas.search.take_request') as take_request:
            candidates = discover_candidates(result, 'secret-token', 4, transport)

        query = parse_qs(urlsplit(calls[0][0]).query)
        self.assertEqual(query['q'], ['"Example AS" Oslo'])
        self.assertEqual(query['country'], ['NO'])
        self.assertEqual(query['search_lang'], ['no'])
        self.assertEqual(calls[0][1], 'secret-token')
        take_request.assert_called_once()
        self.assertEqual([(item['kind'], item['value']) for item in candidates], [
            ('website', 'https://www.example.no/'),
            ('social_page', 'https://www.facebook.com/example-company'),
        ])
        self.assertNotIn('Company website', json.dumps(result))
        self.assertEqual(result['search_research']['successful_queries'], 1)

    def test_search_errors_do_not_copy_server_details_or_api_key(self):
        result = self.make_result()

        def fail(*_):
            raise ValueError('search_http_401 secret-token')

        discover_candidates(result, 'secret-token', transport=fail)
        self.assertEqual(result['search_research']['errors'], ['ValueError'])
        self.assertNotIn('secret-token', json.dumps(result))
        self.assertEqual(result['candidates'], [])

    def test_social_search_runs_only_when_general_results_have_no_social_page(self):
        result = self.make_result()
        responses = [
            {'web': {'results': [{'url': 'https://example.no/'}]}},
            {'web': {'results': [{'url': 'https://www.linkedin.com/company/example'}]}},
        ]
        queries = []

        def transport(url, _key, _timeout):
            queries.append(parse_qs(urlsplit(url).query)['q'][0])
            return 200, {}, json.dumps(responses.pop(0)).encode()

        discover_candidates(result, 'secret-token', transport=transport)
        self.assertEqual(len(queries), 2)
        self.assertIn('Facebook Instagram LinkedIn', queries[1])
        self.assertEqual(result['search_research']['successful_queries'], 2)
        self.assertEqual([candidate['kind'] for candidate in result['candidates']], ['website', 'social_page'])

    def test_rate_budget_failure_is_visible_without_a_claim(self):
        result = self.make_result()

        def fail(*_):
            from traceatlas.network import BudgetError
            raise BudgetError('global_request_budget_exhausted')

        with patch('traceatlas.search.take_request', side_effect=fail):
            discover_candidates(result, 'secret-token')
        self.assertEqual(result['search_research']['queries'], 0)
        self.assertEqual(result['search_research']['errors'], ['global_request_budget_exhausted'])
        self.assertEqual(result['search_research']['successful_queries'], 0)
        self.assertEqual(result['candidates'], [])

    def test_search_requires_key_before_creating_run_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'run'
            with patch.dict(os.environ, {'BRAVE_SEARCH_API_KEY': ''}):
                with self.assertRaisesRegex(ValueError, 'BRAVE_SEARCH_API_KEY'):
                    core.run_batch(['923609016'], output, search_websites=True)
            self.assertFalse(output.exists())

    def test_batch_audits_search_candidates_and_reports_list_price(self):
        from traceatlas.audit import verify

        def search_result(row, *_args):
            row['search_research'] = {
                'provider': 'brave', 'queries': 1, 'successful_queries': 1,
                'candidates': 1, 'errors': [],
            }
            row['candidates'].append({
                'kind': 'social_page', 'value': 'https://www.facebook.com/example', 'status': 'discovered',
                'discovery_source': 'web_search',
            })
            return row['candidates']

        real_enrich = web.enrich

        def fake_enrich(row, domains, deadline, discover=False):
            return real_enrich(row, domains, deadline, FakeSession, discover)

        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {'BRAVE_SEARCH_API_KEY': 'test-key'}), \
                patch.object(registry, 'fetch', return_value=fixture(hjemmeside='example.com')), \
                patch('traceatlas.accounts.enrich', return_value=None), \
                patch('traceatlas.registry_extra.enrich', return_value=[]), \
                patch('traceatlas.search.discover_candidates', side_effect=search_result), \
                patch('traceatlas.web.enrich', side_effect=fake_enrich):
            report = core.run_batch([ORG], folder, workers=1, search_websites=True)

            self.assertEqual(report['search_queries'], 1)
            self.assertEqual(report['external_api_cost_usd'], 0.005)
            self.assertIn('listed rate', report['external_api_cost_basis'])
            self.assertTrue(verify(folder)['passed'])

    def test_social_evidence_round_trips_through_json_audit(self):
        from traceatlas.audit import verify
        unique_social = b'<h1>SYNTHETIC TEST COMPANY</h1><p>Official social profile.</p>'
        class SocialSession(FakeSession):
            def page(self,url):
                self.requests+=1
                return unique_social if 'facebook.com' in url else super().page(url)
        def search_result(row,*_args):
            row['search_research']={'provider':'brave','queries':1,'successful_queries':1,
                                    'candidates':1,'errors':[]}
            row['candidates'].append({'kind':'social_page',
                'value':'https://www.facebook.com/example','status':'discovered',
                'discovery_source':'web_search'})
            return row['candidates']
        real_enrich=web.enrich
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ,{'BRAVE_SEARCH_API_KEY':'test-key'}), \
                patch.object(registry,'fetch',return_value=fixture(hjemmeside='example.com')), \
                patch('traceatlas.accounts.enrich',return_value=None), \
                patch('traceatlas.registry_extra.enrich',return_value=[]), \
                patch('traceatlas.search.discover_candidates',side_effect=search_result), \
                patch('traceatlas.web.enrich',side_effect=lambda row,domains,deadline,discover=False:
                      real_enrich(row,domains,deadline,SocialSession,discover)):
            core.run_batch([ORG],folder,workers=1,search_websites=True)
            row=json.loads((Path(folder)/'profiles.jsonl').read_text())
            self.assertTrue(any(claim['field']=='social_pages' for claim in row['claims']))
            self.assertTrue(verify(folder)['passed'])


if __name__ == '__main__':
    unittest.main()
