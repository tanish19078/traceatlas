"""Structured postings require exact employer attribution and reproducible evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import core, registry, web
from traceatlas.audit import verify
from traceatlas.jobs import extract_jobs
from tests.test_traceatlas import ORG, fixture
from tests.test_web_research import PAGE, HOST

STAMP='2026-10-10T12:00:00+00:00'
NAME='SYNTHETIC TEST COMPANY'

def job(**changes):
    value={'@type':'JobPosting','title':'Synthetic Engineer','datePosted':'2026-10-01',
           'validThrough':'2099-12-31','hiringOrganization':{'name':NAME,'taxID':ORG}}
    value.update(changes)
    return value

def document(value):
    return web.Document(PAGE+b'<script type="application/ld+json">'+json.dumps(value).encode()+b'</script>')

def extract(value):
    return extract_jobs(document(value),ORG,NAME,'https://example.com/','key',STAMP)

class JobTests(unittest.TestCase):
    def test_exact_job_has_original_value_and_locator(self):
        value=job();claim=extract(value)[0]
        self.assertEqual(claim['value'],value)
        self.assertEqual(claim['json_ld_block'],0)
        self.assertEqual(claim['json_pointer'],'')
        self.assertEqual(claim['effective_date'],'2026-10-01')

    def test_parent_company_and_conflicting_tax_id_are_rejected(self):
        for employer in [{'name':NAME+' HOLDING'},{'name':NAME,'taxID':'974760673'}]:
            self.assertEqual(extract(job(hiringOrganization=employer)),[])

    def test_expired_future_and_unusable_dates_are_rejected(self):
        for changes in [{'validThrough':'2026-09-30'},{'datePosted':'2099-01-01'},
                        {'datePosted':'unknown'},{'datePosted':'2026-10-01T08:00:00'},
                        {'validThrough':None}]:
            with self.subTest(changes=changes):
                self.assertEqual(extract(job(**changes)),[])

    def test_graph_and_arrays_have_exact_json_pointer(self):
        value={'@graph':[{'@type':'Organization'},job()]}
        self.assertEqual(extract(value)[0]['json_pointer'],'/@graph/1')
        self.assertEqual(extract([job()])[0]['json_pointer'],'/0')

    def test_duplicate_postings_are_deduplicated(self):
        self.assertEqual(len(extract([job(),job()])),1)

    def test_conflicting_duplicate_job_identifier_is_ambiguous(self):
        self.assertEqual(extract([job(identifier='role-1'),job(identifier='role-1',title='Conflicting title')]),[])

    def test_scripts_never_provide_visible_identity_proof(self):
        doc=web.Document(b'<script type="application/ld+json">'+json.dumps(job()).encode()+b'</script>')
        self.assertIsNone(web.verify_identity(doc,ORG,NAME))

    def test_malformed_json_ld_does_not_break_identity_parser(self):
        doc=web.Document(PAGE+b'<script type="application/ld+json">bad-json</script>')
        self.assertEqual(extract_jobs(doc,ORG,NAME,'https://example.com/','key',STAMP),[])
        self.assertIsNotNone(web.verify_identity(doc,ORG,NAME))

    def test_bounded_output_for_many_postings(self):
        self.assertEqual(len(extract([job(title='Role '+str(i)) for i in range(100)])),20)

    def test_job_claim_survives_export_audit_and_tampering_fails(self):
        body=PAGE+b'<script type="application/ld+json">'+json.dumps(job()).encode()+b'</script>'
        class Session:
            def __init__(self,origin,deadline):self.requests=1
            def page(self,url):self.requests+=1;return body
        enrich=web.enrich
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture(hjemmeside=HOST)), patch.object(web,'enrich',side_effect=lambda row,domains,deadline:enrich(row,domains,deadline,Session)):
            core.run_batch([ORG],folder,allowed_domains=[HOST])
            self.assertTrue(verify(folder)['passed'])
            path=Path(folder)/'profiles.jsonl';row=json.loads(path.read_text())
            claim=next(c for c in row['claims'] if c['field']=='jobs')
            self.assertEqual(row['availability']['jobs']['state'],'available')
            claim['value']['title']='Invented role'
            path.write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])
