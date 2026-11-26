import unittest
from datetime import date,timedelta
from unittest.mock import patch
from html import escape
from tools import publication_metadata as m, citation_display as c, build as b
from sdg_classifier import SDGError

D='10.1234/example'
CR={'DOI':D,'type':'journal-article','author':[{'given':'Aylin','family':'Test'},{'given':'Ekinhan','family':'Erişkin','ORCID':'https://orcid.org/0000-0002-0087-0933'}],'volume':'15','issue':'4','page':'100-110','publisher':'Example'}
OA={'doi':'https://doi.org/'+D,'type':'article','primary_location':{'source':{'type':'journal'}},'open_access':{'is_oa':True,'oa_status':'gold'},'topics':[{'display_name':'Asphalt pavement materials'},{'display_name':'Machine learning methods'}],'primary_topic':{'display_name':'Asphalt pavement materials','subfield':{'display_name':'Civil Engineering'}},'fwci':2.7,'citation_normalized_percentile':{'value':.96,'is_in_top_10_percent':True,'is_in_top_1_percent':False},'cited_by_count':25,'publication_year':2020}
class PublicationMetadataTests(unittest.TestCase):
    def data(self):
        p={'doi':D,'title':'Pavement & traffic','author':'Test, A., & Eriskin, E.','journal':'Example journal','year':'2020','sdg':[9]}
        with patch.object(m,'request_json',side_effect=[{'message':CR},OA]): m.enrich([p],key='key',today=date(2026,11,26))
        return p
    def test_verified_source_fields(self):
        p=self.data(); v=m.metadata(p); self.assertEqual(v['type'],'Journal article'); self.assertEqual(v['volume'],'15'); self.assertEqual(v['openalex']['fwci'],2.7); self.assertEqual(v['topics'][0],'Asphalt pavement materials'); self.assertEqual(m.top_label(p,v,date(2026,11,26)),'Top 10% cited'); self.assertEqual(len(m.topic_groups(v)),2); self.assertEqual(p['sdg'],[9])
    def test_crossref_order_and_original_authors(self):
        p=self.data(); v=m.metadata(p); html=c.author_html(p,v,b.h); self.assertEqual(html,'Test, A., &amp; <strong>Eriskin, E.</strong>'); p.pop('author'); self.assertEqual(c.author_html(p,v,b.h),'Aylin Test, <strong>Ekinhan Erişkin</strong>')
    def test_exports_and_escape(self):
        p=self.data(); v=m.metadata(p); ex=c.exports(p,v); self.assertIn('Test, Aylin and Erişkin, Ekinhan',ex['BibTeX']); self.assertIn(r'Pavement \& traffic',ex['BibTeX']); self.assertIn('AU  - Erişkin, Ekinhan',ex['RIS']); self.assertIn('https://doi.org/'+D,c.citation(p,v)); self.assertIn('Open Access',b.publication_info(p,{},v,'',[]))
    def test_citation_window_and_null(self):
        p=self.data(); v=m.metadata(p); self.assertEqual(m.top_label(p,v,date(2023,12,31)),''); self.assertEqual(m.top_label(p,v,date(2024,1,1)),'Top 10% cited'); v['openalex']['percentile']=None; self.assertEqual(m.top_label(p,v,date(2026,1,1)),'')
    def test_cache_and_failure_preserve(self):
        p=self.data(); old=p['publication_metadata'].copy()
        with patch.object(m,'request_json') as req: m.enrich([p],key='key',today=date(2026,11,27)); req.assert_not_called()
        with patch.object(m,'request_json',side_effect=SDGError('timeout')): m.enrich([p],key='key',today=date(2027,3,1))
        self.assertEqual(p['publication_metadata'],old)
    def test_exact_doi_and_unknown_types(self):
        with patch.object(m,'request_json',side_effect=[dict(OA,doi='https://doi.org/10.1234/other'),{'results':[OA]}]): self.assertEqual(m.openalex(D,'key')['type'],'Journal article')
        with patch.object(m,'request_json',return_value={'message':dict(CR,DOI='10.1234/other')}):
            with self.assertRaises(SDGError): m.crossref(D)
        with patch.object(m,'request_json',return_value=dict(OA,primary_location=None)):
            self.assertEqual(m.openalex(D,'key')['type'],'')
    def test_missing_metadata_and_false_oa(self):
        p={'title':'Title','doi':D,'author':'Eriskin, E.'}; v=m.metadata(p); self.assertEqual(c.exports(p,v),{}); self.assertNotIn('Open Access',b.publication_info(p,{},v,'',[])); self.assertIn('BibTeX (Crossref)',b.cite_controls(p,v)); self.assertEqual(m.top_label(p,v),'')
    def test_metadata_doi_mismatch_not_rendered(self):
        p=self.data(); p['doi']='10.1234/other'; self.assertFalse(m.metadata(p)['openalex']); self.assertFalse(m.metadata(p)['crossref'])
if __name__=='__main__': unittest.main()
