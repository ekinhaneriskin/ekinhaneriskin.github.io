import unittest
from unittest.mock import patch
import updater as u
from tools import build as b
class TestUpdater(unittest.TestCase):
    def test_merge_preserves_manual_fields_and_doi_match(self):
        p={'title':'Example title','doi':'https://doi.org/10.1234/AB','author':'All Authors','year':'2026','sdg':[11],'wos_link':'https://example.org/wos','citations':'3','index':'sci'}
        u.merge([p],[{'title':'Example title','doi':'10.1234/ab','citations':5,'scopus_link':'https://example.org/scopus','index':'scopus'}])
        self.assertEqual(p['citations'],5); self.assertEqual(p['sdg'],[11]); self.assertEqual(p['author'],'All Authors'); self.assertEqual(p['index'],'sci')
    def test_missing_doi_title_match_and_conflict(self):
        p={'title':'Title: case!','year':'2026','doi':''}; records=[p]
        u.merge(records,[{'title':'Title case','year':'2026','doi':'10.1234/a'}]); self.assertEqual(len(records),1); self.assertEqual(p['doi'],'10.1234/a')
        u.merge(records,[{'title':'Title case','year':'2026','doi':'10.1234/b'}]); self.assertEqual(len(records),2)
    def test_metrics_root_and_failure(self):
        with patch.object(u,'scopus',return_value={'author-retrieval-response':[{'h-index':'7','coredata':{'citation-count':'204','document-count':'28'}}]}):
            self.assertEqual(u.fetch_metrics()['h_index'],7)
        with patch.object(u,'scopus',return_value={'author-retrieval-response':[{'coredata':{'citation-count':'0'}}]}):
            with self.assertRaises(u.FetchError): u.fetch_metrics()
    def test_author_metrics_only_when_permitted_and_complete(self):
        valid={'source':'Scopus API','as_of':u.TODAY,'h_index':7,'citation_count':204,'document_count':28}
        with patch.dict('os.environ',{'SHOW_SCOPUS_METRICS':'true'}):
            html=b.author_metrics_html(valid)
            self.assertIn('Scopus-indexed documents',html)
            self.assertIn('204',html)
            self.assertNotIn('Listed publications',html)
            self.assertEqual(b.author_metrics_html(valid|{'source':'Scopus (author-reported)'}),'')
            self.assertEqual(b.author_metrics_html(valid|{'document_count':None}),'')
            self.assertEqual(b.author_metrics_html(valid|{'document_count':0}),'')
            self.assertEqual(b.author_metrics_html(valid|{'as_of':'invalid'}),'')
        with patch.dict('os.environ',{'SHOW_SCOPUS_METRICS':'false'}):
            self.assertEqual(b.author_metrics_html(valid),'')
    def test_metrics_failure_hides_and_preserves_publications(self):
        data={'metrics':{'source':'Scopus (author-reported)'},'publications':[{'sdg':[11]}]}
        with patch.object(u,'fetch_metrics',side_effect=u.FetchError('unavailable')):
            with self.assertRaises(u.FetchError): u.refresh_author_metrics(data)
        self.assertNotIn('metrics',data)
        self.assertEqual(data['publications'],[{'sdg':[11]}])
    def test_metrics_fallback_and_no_public_storage(self):
        good={'author-retrieval-response':[{'h-index':'7','coredata':{'citation-count':'204','document-count':'28'}}]}
        with patch.object(u,'scopus',side_effect=[u.FetchError('403'),good]) as mocked:
            result=u.fetch_metrics()
            self.assertEqual(result['h_index'],7)
            self.assertEqual(mocked.call_args.args[1]['view'],'ENHANCED')
        data={'metrics':{'source':'Scopus (author-reported)'}}
        with patch.dict('os.environ',{'SHOW_SCOPUS_METRICS':'false'}),patch.object(u,'fetch_metrics',return_value=result):
            u.refresh_author_metrics(data)
        self.assertNotIn('metrics',data)
    def test_pagination(self):
        def entry(n): return {'eid':f'2-s2.0-{n}','dc:title':f'Paper {n}','prism:coverDate':'2026-01-01'}
        def page(a): return {'search-results':{'opensearch:totalResults':'26','entry':a}}
        with patch.object(u,'scopus',side_effect=[page([entry(n) for n in range(25)]),page([entry(25)])]) as m:
            self.assertEqual(len(u.fetch_publications()),26); self.assertEqual(m.call_args.args[1]['start'],25)
        with patch.object(u,'scopus',side_effect=[page([entry(n) for n in range(25)]),page([])]):
            with self.assertRaises(u.FetchError): u.fetch_publications()
    def test_access_requires_explicit_release(self):
        self.assertIsNone(b.paper_access({'access':{'kind':'approved_file','approved':True,'release_on':'2099-01-01','path':'papers/a.pdf','version':'accepted manuscript','license':'test','policy':'https://example.org','notice':'test'}}))
        self.assertIsNone(b.paper_access({'access':{'kind':'approved_file','path':'papers/a.pdf'}}))
        self.assertIsNotNone(b.paper_access({'access':{'kind':'publisher_oa','url':'https://example.org','license':'CC BY 4.0','policy':'https://example.org'}}))
    def test_wos_pagination_and_separate_citations(self):
        def doc(n):
            return {'uid':f'WOS:A{n:05d}','title':f'Paper {n}','source':{'publishYear':2026,'sourceTitle':'Journal'},'identifiers':{'doi':f'10.1234/{n}'},'names':{'authors':[{'displayName':'Author, E'}]},'citations':[{'db':'WOS','count':n},{'db':'MEDLINE','count':99}]}
        def page(hits): return {'metadata':{'total':51},'hits':hits}
        with patch.object(u,'WOS_KEY','test'),patch.object(u,'get',side_effect=[page([doc(n) for n in range(50)]),page([doc(50)])]) as get:
            found=u.fetch_wos_publications()
            self.assertEqual(len(found),51)
            self.assertEqual(get.call_args.args[1]['page'],2)
            self.assertIn(u.RESEARCHER_ID,get.call_args.args[1]['q'])
        old={'title':'Paper 50','doi':'10.1234/50','citations':12,'scopus_link':'https://example.org/s','author':'Full author names'}
        records=[old]; u.merge(records,[found[-1]])
        self.assertEqual(len(records),1); self.assertEqual(old['citations'],12); self.assertEqual(old['wos_citations'],50); self.assertEqual(old['author'],'Full author names')
        self.assertEqual(u.record_wos_uid(old),'WOS:A00050')
        with patch.object(u,'WOS_KEY','test'),patch.object(u,'get',side_effect=[page([doc(n) for n in range(50)]),page([])]):
            with self.assertRaises(u.FetchError): u.fetch_wos_publications()
    def test_wos_only_discovery_and_orcid_fallback(self):
        old={'title':'Existing','doi':'10.1234/old','citations':4}; records=[old]
        u.merge_orcid(records,[{'title':'Existing','doi':'10.1234/old','wos_uid':'WOS:12345','wos_link':'https://www.webofscience.com/wos/woscc/full-record/WOS:12345'}, {'title':'New WoS paper','doi':'10.1234/new','wos_uid':'WOS:A987','wos_link':'https://www.webofscience.com/wos/woscc/full-record/WOS:A987'}, {'title':'Unindexed work','doi':'10.1234/other'}])
        self.assertEqual(len(records),2); self.assertEqual(old['citations'],4); self.assertEqual(u.record_wos_uid(old),'WOS:12345')
        self.assertIsNone(u.match({'title':'Conflict','doi':'10.1234/wrong','wos_uid':'WOS:12345'},records))
    def test_wos_doi_backfill_only_updates_known_dois(self):
        records=[{'title':'Known','doi':'10.1234/known'}]
        with patch.object(u,'fetch_wos_query',return_value=[{'title':'Known','doi':'10.1234/known','wos_uid':'WOS:ABC'}, {'title':'Unrelated','doi':'10.1234/else','wos_uid':'WOS:DEF'}]):
            u.wos_backfill(records)
        self.assertEqual(len(records),1); self.assertEqual(records[0]['wos_uid'],'WOS:ABC')
    def test_orcid_wos_alphanumeric_id(self):
        data={'group':[{'work-summary':[{'title':{'title':{'value':'Paper'}}}], 'external-ids':{'external-id':[{'external-id-type':'wosuid','external-id-value':'WOS:A1234','external-id-relationship':'self'},{'external-id-type':'doi','external-id-value':'10.1234/a','external-id-relationship':'self'}]}}]}
        with patch.object(u,'get',return_value=data):
            p=u.orcid_records()[0]
        self.assertEqual(p['wos_uid'],'WOS:A1234'); self.assertEqual(p['wos_source'],'ORCID (record identifier)')
    def test_orcid_summary_ids_without_wos_key(self):
        summary={'title':{'title':{'value':'Paper'}},'external-ids':{'external-id':[{'external-id-type':'wosuid','external-id-value':'123456','external-id-relationship':'self'}]}}
        group={'work-summary':[summary],'external-ids':{'external-id':[{'external-id-type':'doi','external-id-value':'10.1234/a','external-id-relationship':'self'}]}}
        with patch.object(u,'WOS_KEY',None),patch.object(u,'get',return_value={'group':[group]}):
            records=[]; u.merge_orcid(records,u.orcid_records())
        self.assertEqual(len(records),1); self.assertEqual(records[0]['wos_uid'],'WOS:123456')
        self.assertNotIn('wos_citations',records[0])
    def test_orcid_conflicting_or_nonself_ids(self):
        def group(ids): return {'work-summary':[{'title':{'title':{'value':'Paper'}}}], 'external-ids':{'external-id':ids}}
        def id_(typ,val,rel='self'): return {'external-id-type':typ,'external-id-value':val,'external-id-relationship':rel}
        with patch.object(u,'get',return_value={'group':[group([id_('wosuid','123'),id_('wosuid','456')]),group([id_('wosuid','789','part-of')])]}):
            records=[]; u.merge_orcid(records,u.orcid_records())
        self.assertEqual(records,[])
if __name__=='__main__': unittest.main()
