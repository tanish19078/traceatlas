"""A group website and its vacancies cannot become a subsidiary's facts."""
import json
import unittest
from traceatlas.web import Document, verify_site_owner
from traceatlas.jobs import extract_jobs
from tests.test_jobs import ORG,NAME,STAMP,DETAIL,DESCRIPTION,job,document,extract

class AttributionTests(unittest.TestCase):
    def owner_doc(self, owner):
        return Document(f'<h1>Holding group</h1><footer>{NAME} Org nr {ORG}</footer><script type="application/ld+json">'.encode()+json.dumps(owner).encode()+b'</script>')
    def test_group_publisher_overrides_subsidiary_footer(self):
        owner={'@type':'WebSite','publisher':{'name':'PARENT HOLDING AS','taxID':'974760673'}}
        self.assertIsNone(verify_site_owner(self.owner_doc(owner),ORG,NAME))
    def test_group_heading_without_owner_is_ambiguous(self):
        self.assertIsNone(verify_site_owner(self.owner_doc({}),ORG,NAME))
    def test_exact_owner_can_resolve_a_brand_heading(self):
        owner={'@type':'Organization','name':NAME,'taxID':ORG}
        self.assertIsNotNone(verify_site_owner(self.owner_doc(owner),ORG,NAME))
    def test_conflicting_organization_taxid_rejected(self):
        self.assertIsNone(verify_site_owner(self.owner_doc({'@type':'Organization','name':NAME,'taxID':'974760673'}),ORG,NAME))
    def test_job_listing_homepage_and_search_are_not_single_ads(self):
        for url in ['https://example.com/','https://example.com/careers','https://example.com/jobs?q=engineer']:
            self.assertEqual(extract_jobs(document(job(url=url)),ORG,NAME,url,'key',STAMP),[])
    def test_job_requires_same_page_url_and_visible_description(self):
        for value in [job(url='https://parent.example.com/jobs/1'),job(description='Apply now'),job(description='A hidden description that does not appear in visible page content at all.')]:
            self.assertEqual(extract(value),[])
    def test_parent_hiring_organization_rejected_even_on_verified_site(self):
        self.assertEqual(extract(job(hiringOrganization={'name':'PARENT HOLDING AS'})),[])

    def test_explicit_legal_name_and_schema_url_cannot_hide_parent_ownership(self):
        for owner in [{'@type':'https://schema.org/Corporation','name':'PARENT HOLDING AS'},
                      {'@type':'Organization','name':NAME,'legalName':'PARENT HOLDING AS'}]:
            body=f'<h1>{NAME}</h1>{NAME} Org nr {ORG}<script type="application/ld+json">'.encode()+json.dumps(owner).encode()+b'</script>'
            self.assertIsNone(verify_site_owner(Document(body),ORG,NAME))
        self.assertEqual(extract(job(hiringOrganization={'name':NAME,'legalName':'PARENT HOLDING AS','taxID':ORG})),[])
