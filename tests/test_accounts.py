"""Official account facts keep exact identities, values and JSON pointers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from traceatlas import core, registry, registry_extra
from traceatlas.accounts import METRICS, extract, extract_v1, enrich
from traceatlas.audit import verify
from traceatlas.models import company_summary, digest
from tests.test_traceatlas import fixture


ORG = '923609016'


def account(**changes):
    value = {
        'virksomhet': {'organisasjonsnummer': ORG},
        'regnskapsperiode': {'fraDato': '2024-01-01', 'tilDato': '2024-12-31'},
        'regnskapstype': 'SELSKAP',
        'valuta': 'NOK',
        'resultatregnskapResultat': {
            'driftsresultat': {
                'driftsinntekter': {
                    'sumDriftsinntekter': 1200,
                    'salgsinntekter': 1100,
                },
                'driftsresultat': 200,
            },
            'aarsresultat': 150,
        },
        'eiendeler': {'sumEiendeler': 3000},
        'egenkapitalGjeld': {
            'egenkapital': {'sumEgenkapital': 1000},
            'gjeldOversikt': {'sumGjeld': 2000},
        },
    }
    value.update(changes)
    return value


class AccountTests(unittest.TestCase):
    def test_extracts_supported_metrics_with_exact_pointers(self):
        claims = extract([account()], ORG, 'evidence')
        self.assertEqual({claim['value']['metric'] for claim in claims}, set(METRICS))
        revenue = next(claim for claim in claims if claim['value']['metric'] == 'revenue')
        self.assertEqual(revenue['value']['amount'], 1200)
        self.assertEqual(
            revenue['json_pointer'],
            '/0/resultatregnskapResultat/driftsresultat/driftsinntekter/sumDriftsinntekter',
        )
        self.assertEqual(revenue['reporting_period'], '2024-01-01/2024-12-31')
        self.assertEqual(revenue['extraction_method'], 'official_accounts_v2')

    def test_missing_values_are_not_coerced_to_zero(self):
        value = account()
        del value['egenkapitalGjeld']['gjeldOversikt']['sumGjeld']
        value['eiendeler']['sumEiendeler'] = None
        metrics = {claim['value']['metric'] for claim in extract([value], ORG, 'evidence')}
        self.assertNotIn('total_assets', metrics)
        self.assertNotIn('total_liabilities', metrics)

    def test_wrong_identity_and_conflicting_duplicate_are_rejected(self):
        wrong = account(virksomhet={'organisasjonsnummer': '974760673'})
        self.assertEqual(extract([wrong], ORG, 'evidence'), [])
        conflicting = account()
        conflicting['resultatregnskapResultat']['driftsresultat']['driftsinntekter']['sumDriftsinntekter'] = 9999
        self.assertEqual(extract([account(), conflicting], ORG, 'evidence'), [])

    def test_legacy_extractor_remains_available_for_saved_runs(self):
        claim = extract_v1([account()], ORG, 'evidence')[0]
        self.assertEqual(claim['value']['revenue'], 1200)
        self.assertEqual(claim['extraction_method'], 'official_accounts_v1')

    def test_summary_uses_new_financial_metrics(self):
        claims = extract([account()], ORG, 'evidence')
        older = account(regnskapsperiode={'fraDato': '2023-01-01', 'tilDato': '2023-12-31'})
        older['resultatregnskapResultat']['driftsresultat']['driftsinntekter']['sumDriftsinntekter'] = 1000
        claims.extend(extract([older], ORG, 'older'))
        summary = company_summary({'legal_identity': {'name': 'Example AS'}, 'claims': claims})
        self.assertIn('up 20.0% year over year', summary)
        self.assertIn('Annual result was 150 NOK', summary)
        self.assertIn('Total equity was 1,000 NOK', summary)

    def test_summary_does_not_call_nonadjacent_periods_year_over_year(self):
        latest = extract([account()], ORG, 'latest')
        older = account(regnskapsperiode={'fraDato': '2022-01-01', 'tilDato': '2022-12-31'})
        claims = latest + extract([older], ORG, 'older')
        summary = company_summary({'legal_identity': {'name': 'Example AS'}, 'claims': claims})
        self.assertIn('no comparable prior period was available', summary)
        self.assertNotIn('year over year', summary)

    def test_summary_does_not_compare_different_period_lengths(self):
        latest = extract([account()], ORG, 'latest')
        short = account(regnskapsperiode={'fraDato': '2023-07-01', 'tilDato': '2023-12-31'})
        short['resultatregnskapResultat']['driftsresultat']['driftsinntekter']['sumDriftsinntekter'] = 1000
        claims = latest + extract([short], ORG, 'short')
        summary = company_summary({'legal_identity': {'name': 'Example AS'}, 'claims': claims})
        self.assertIn('no comparable prior period was available', summary)
        self.assertNotIn('year over year', summary)

    def test_financial_claims_survive_export_audit_and_tampering_fails(self):
        body = json.dumps([account()]).encode()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(registry,'fetch',return_value=fixture()), \
                patch('traceatlas.accounts.fetch',return_value=body), \
                patch.object(registry_extra,'enrich',return_value=[]):
            core.run_batch([ORG],folder)
            self.assertTrue(verify(folder)['passed'])
            contract=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            evidence=next(item for item in contract['evidence']
                          if item['native_source_class']=='official_accounts')
            self.assertIn('150',evidence['claim_span'])
            page=(Path(folder)/'index.html').read_text()
            self.assertIn('<strong>Annual Result</strong>',page)
            self.assertIn('/resultatregnskapResultat/aarsresultat',page)
            path=Path(folder)/'profiles.jsonl';row=json.loads(path.read_text())
            claim=next(item for item in row['claims']
                       if item['field']=='financials' and item['value']['metric']=='annual_result')
            claim['value']['amount']=999999
            path.write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])

    def test_v1_revenue_upgrades_without_a_false_removal(self):
        registry_body=fixture()
        account_body=json.dumps([account()]).encode()
        evidence_id=digest(account_body)
        with tempfile.TemporaryDirectory() as folder:
            store=core.Store(folder)
            try:
                with patch.object(registry,'fetch',return_value=registry_body):
                    first,_=core.research(ORG)
                    second,_=core.research(ORG)
                first['claims'].extend(extract_v1([account()],ORG,evidence_id))
                first['availability']['financials']={'state':'available'}
                first['evidence'].append({
                    'id':evidence_id,'source_url':'https://data.brreg.no/regnskapsregisteret/regnskap/'+ORG,
                    'retrieved_at':'2026-11-01T00:00:00+00:00','content_sha256':evidence_id,
                    'snapshot_path':'snapshots/'+evidence_id+'.json','source_class':'official_accounts',
                    'extractor_version':'official_accounts_v1','organisation_number':ORG,
                    'synthetic':False,
                })
                store.save(first,[(registry_body,'.json'),(account_body,'.json')])
                enrich(second,body=account_body)
                saved=store.save(second,[(registry_body,'.json'),(account_body,'.json')])
                financial_changes=[change for change in saved['refresh']['changes']
                                   if change['field']=='financials']
                self.assertTrue(financial_changes)
                self.assertTrue(all(change['kind']=='added' for change in financial_changes))
                self.assertNotIn('revenue',{
                    change['after']['value']['metric'] for change in financial_changes})
                self.assertFalse(any(claim['field']=='financials'
                                     for claim in saved.get('last_known',{}).get('claims',[])))
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
