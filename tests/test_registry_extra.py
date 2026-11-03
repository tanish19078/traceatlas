import unittest
from traceatlas.registry_extra import extract_locations, extract_roles
from traceatlas.models import company_summary

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
        self.assertNotIn('secret', str(claims))

    def test_locations_require_exact_parent_number(self):
        data = {'_embedded': {'underenheter': [
            {'organisasjonsnummer': '111111111', 'overordnetEnhet': ORG, 'navn': 'Oslo office',
             'beliggenhetsadresse': {'kommune': 'OSLO'}},
            {'organisasjonsnummer': '222222222', 'overordnetEnhet': '000000000', 'navn': 'Other office'},
        ]}}
        claims = extract_locations(data, ORG, 'evidence')
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]['value']['organisation_number'], '111111111')

    def test_summary_compares_same_report_type_and_currency(self):
        result = {'legal_identity': {'name': 'Example AS'}, 'claims': [
            {'field': 'financials', 'value': {'period_end': '2025-12-31', 'revenue': 120,
             'currency': 'NOK', 'report_type': 'SELSKAP'}},
            {'field': 'financials', 'value': {'period_end': '2024-12-31', 'revenue': 100,
             'currency': 'NOK', 'report_type': 'SELSKAP'}},
            {'field': 'financials', 'value': {'period_end': '2025-12-31', 'revenue': 300,
             'currency': 'NOK', 'report_type': 'KONSERN'}},
        ]}
        self.assertIn('up 20.0% year over year', company_summary(result))


if __name__ == '__main__':
    unittest.main()
