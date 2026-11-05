import unittest
from traceatlas.registry_extra import (extract_locations, extract_locations_v1,
                                       extract_roles, extract_roles_v1)
from traceatlas.models import company_summary
from traceatlas.web import Document, _website_guesses, verify_site_owner

ORG = '923609016'


class RegistryDetailTests(unittest.TestCase):
    def test_roles_keep_public_name_and_title_only(self):
        data = {'rollegrupper': [{'roller': [
            {'type': {'beskrivelse': 'Daglig leder'}, 'person': {'navn': {
                'fornavn': 'Ada', 'mellomnavn': 'M', 'etternavn': 'Nord'}}},
            {'type': {'beskrivelse': 'Daglig leder'}, 'person': {'navn': {
                'fornavn': 'Ada', 'mellomnavn': 'M', 'etternavn': 'Nord'}, 'fodselsnummer': 'secret'}},
        ]}]}
        claims = extract_roles(data, ORG, 'evidence')
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]['value'], {'name': 'Ada M Nord', 'role': 'Daglig leder'})
        self.assertEqual(claims[0]['json_pointer'],'/rollegrupper/0/roller/0')
        self.assertEqual(claims[0]['extraction_method'],'brreg_roles_v2')
        self.assertNotIn('secret', str(claims))
        self.assertIsNone(extract_roles_v1(data,ORG,'evidence')[0]['json_pointer'])

    def test_locations_require_exact_parent_number(self):
        data = {'_embedded': {'underenheter': [
            {'organisasjonsnummer': '111111111', 'overordnetEnhet': ORG, 'navn': 'Oslo office',
             'beliggenhetsadresse': {'kommune': 'OSLO'}},
            {'organisasjonsnummer': '222222222', 'overordnetEnhet': '000000000', 'navn': 'Other office'},
        ]}}
        claims = extract_locations(data, ORG, 'evidence')
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]['value']['organisation_number'], '111111111')
        self.assertEqual(claims[0]['json_pointer'],'/_embedded/underenheter/0')
        self.assertEqual(claims[0]['extraction_method'],'brreg_subunits_v2')
        self.assertIsNone(extract_locations_v1(data,ORG,'evidence')[0]['json_pointer'])

    def test_summary_compares_same_report_type_and_currency(self):
        result = {'legal_identity': {'name': 'Example AS'}, 'claims': [
            {'field': 'company_description', 'value': 'We design and build energy efficient commercial properties in Oslo.'},
            {'field': 'financials', 'value': {'period_start': '2025-01-01', 'period_end': '2025-12-31', 'revenue': 120,
              'currency': 'NOK', 'report_type': 'SELSKAP'}},
            {'field': 'financials', 'value': {'period_start': '2024-01-01', 'period_end': '2024-12-31', 'revenue': 100,
              'currency': 'NOK', 'report_type': 'SELSKAP'}},
            {'field': 'financials', 'value': {'period_start': '2025-01-01', 'period_end': '2025-12-31', 'revenue': 300,
              'currency': 'NOK', 'report_type': 'KONSERN'}},
        ]}
        summary = company_summary(result)
        self.assertIn('up 20.0% year over year', summary)
        self.assertIn('Company website: We design and build energy efficient commercial properties in Oslo.', summary)

    def test_summary_distinguishes_unknown_and_incomplete_research(self):
        result = {'legal_identity': {'name': 'Example AS'}, 'claims': [], 'availability': {
            'news': {'state': 'not_available', 'reason': 'not_researched_in_registry_baseline'},
            'financials': {'state': 'not_available', 'reason': 'no_reported_financial_records'},
            'jobs': {'state': 'blocked', 'reason': 'robots_disallowed'},
        }, 'refresh': {'changes': [
            {'field': 'registered_employees', 'kind': 'changed'},
        ]}}
        summary = company_summary(result)
        self.assertIn('Not checked in this run: news', summary)
        self.assertIn('Checked but not reported: financials', summary)
        self.assertIn('Research incomplete: jobs (blocked)', summary)
        self.assertIn('Latest refresh changes: registered employees changed', summary)

    def test_site_can_match_exact_legal_name_without_a_registry_number(self):
        document = Document(b'<html><h1>Example AS</h1><p>Local services in Oslo.</p></html>')
        self.assertIsNotNone(verify_site_owner(document, ORG, 'Example AS'))

    def test_site_can_match_exact_legal_name_in_visible_body_copy(self):
        document = Document(b'<html><h1>Electrician in Sandnes</h1><p>Sandnes Elektriske AS</p></html>')
        self.assertIsNotNone(verify_site_owner(document, ORG, 'Sandnes Elektriske AS'))

    def test_website_guesses_use_registered_name_and_town(self):
        result = {'legal_identity': {'name': 'Example AS'}, 'claims': [
            {'field': 'registered_address', 'value': {'poststed': 'Oslo'}}]}
        self.assertEqual(
            _website_guesses(result),
            ['www.example.no', 'example.no', 'example-oslo.no'],
        )


if __name__ == '__main__':
    unittest.main()
