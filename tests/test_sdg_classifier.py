import unittest
from unittest.mock import patch
from datetime import date, timedelta
import sdg_classifier as s
from tools import build as b

class SDGTests(unittest.TestCase):
    def paper(self): return {'title':'Waste recycling in pavement','doi':'10.1234/a','citations':20}
    def models(self, text, model): return {9:.95,12:.99,11:.92} if model==s.MODELS[0] else {12:.98,9:.6}
    def test_abstract(self):
        self.assertEqual(s.abstract_from_index({'road':[1,3],'a':[0,2]}),'a road a road')
    def test_parser(self):
        self.assertEqual(s.aurora_scores({'results':[{'sdg':9,'probability':.91},{'goal':'SDG 12','probability':98.2}]}),{9:.91,12:.982})
        self.assertEqual(s.aurora_scores({'scores':{'SDG 9':.82,'12':{'score':.9}}}),{9:.82,12:.9})
        with self.assertRaises(s.SDGError): s.aurora_scores({'error':'not available'})
    def test_openalex_contract(self):
        fixture={'doi':'https://doi.org/10.1234/a','sustainable_development_goals':[{'id':'https://openalex.org/sdgs/12','score':.91}], 'abstract_inverted_index':{'reuse':[0]}}
        with patch.object(s,'request_json',return_value=fixture) as req:
            self.assertEqual(s.openalex('10.1234/a','test-key'),({12:.91},'reuse'))
            self.assertEqual(req.call_args.kwargs['params']['api_key'],'test-key')
        with patch.object(s,'request_json',return_value=fixture):
            with self.assertRaises(s.SDGError): s.openalex('10.1234/other','test-key')
    def test_consensus_and_cache(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({9:.85,12:.95,11:.5},'reuse waste')),patch.object(s,'aurora',side_effect=self.models) as aur:
            self.assertEqual(s.classify(p,'key'),'classified'); self.assertEqual(p['sdg'],[9,11,12]); self.assertEqual(p['sdg_classification']['review_candidates'],[]); self.assertEqual(p['sdg_sources']['11'],'OpenAlex'); self.assertEqual(p['citations'],20)
            self.assertEqual(s.classify(p,'key'),'cached'); self.assertEqual(aur.call_count,2)
    def test_manual_and_empty_manual(self):
        for assignment in ([5,11],[]):
            p=self.paper()|{'sdg':assignment.copy()}
            with patch.object(s,'openalex',return_value=({12:.95},'abstract')),patch.object(s,'aurora',side_effect=self.models):
                self.assertEqual(s.classify(p,'key',force=True),'manual'); self.assertEqual(p['sdg'],assignment); self.assertTrue(p['sdg_manual'])
                self.assertEqual(p['sdg_classification']['recommended'],[12])
    def test_edit_auto_assignment(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({12:.95},'abstract')),patch.object(s,'aurora',side_effect=self.models):
            s.classify(p,'key'); p['sdg']=[3]; s.classify(p,'key',force=True)
            self.assertEqual(p['sdg'],[3]); self.assertTrue(p['sdg_manual'])
    def test_openalex_only_without_abstract(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({9:.62},'')),patch.object(s,'crossref_abstract',return_value=''),patch.object(s,'aurora',side_effect=s.SDGError('unavailable')):
            self.assertEqual(s.classify(p,'key'),'classified'); self.assertEqual(p['sdg'],[9]); self.assertEqual(p['sdg_sources'],{'9':'OpenAlex'})
    def test_aurora_only_with_crossref_fallback(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({},'')),patch.object(s,'crossref_abstract',return_value='reuse waste'),patch.object(s,'aurora',side_effect=self.models) as aur:
            self.assertEqual(s.classify(p,'key'),'classified'); self.assertEqual(p['sdg'],[12]); self.assertEqual(p['sdg_sources'],{'12':'Aurora + Elsevier model'}); self.assertEqual(p['sdg_classification']['abstract_source'],'Crossref'); self.assertIn('reuse waste',aur.call_args.args[0])
    def test_title_only_does_not_assign_aurora_labels(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({},'')),patch.object(s,'crossref_abstract',return_value=''),patch.object(s,'aurora',side_effect=self.models):
            self.assertEqual(s.classify(p,'key'),'review'); self.assertNotIn('sdg',p)
    def test_crossref_abstract_contract(self):
        with patch.object(s,'request_json',return_value={'message':{'DOI':'10.1234/a','abstract':'<jats:p>Reuse &amp; recycling.</jats:p>'}}):
            self.assertEqual(s.crossref_abstract('10.1234/a'),'Reuse & recycling.')
            with self.assertRaises(s.SDGError): s.crossref_abstract('10.1234/other')
    def test_aurora_fallback_after_openalex_failure(self):
        p=self.paper()
        with patch.object(s,'openalex',side_effect=s.SDGError('not found')),patch.object(s,'crossref_abstract',return_value='abstract'),patch.object(s,'aurora',side_effect=self.models):
            self.assertEqual(s.classify(p,'key'),'classified'); self.assertEqual(p['sdg'],[12]); self.assertIn('not found',p['sdg_classification']['errors'])
    def test_openalex_and_single_aurora_error(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({9:.67},'abstract')),patch.object(s,'aurora',side_effect=[{12:.98},s.SDGError('unavailable')]):
            self.assertEqual(s.classify(p,'key'),'classified'); self.assertEqual(p['sdg'],[9]); self.assertEqual(p['sdg_classification']['review_candidates'],[12])
    def test_failure_preserves_and_retries(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({12:.95},'abstract')),patch.object(s,'aurora',side_effect=self.models): s.classify(p,'key')
        with patch.object(s,'openalex',side_effect=s.SDGError('unavailable')),patch.object(s,'crossref_abstract',return_value=''),patch.object(s,'aurora',side_effect=s.SDGError('unavailable')):
            self.assertEqual(s.classify(p,'key',force=True),'review'); self.assertEqual(p['sdg'],[12]); self.assertFalse(s.manual(p))
            self.assertEqual(s.classify(p,'key'),'cached'); self.assertEqual(s.classify(p,'key',today=date.today()+timedelta(days=1)),'review')
    def test_no_key_and_source_hover(self):
        p=self.paper(); self.assertEqual(s.classify(p,''),'missing_key'); self.assertNotIn('sdg',p)
        html=b.sdg_impact({'sdg':[12],'sdg_source':'OpenAlex + Aurora','sdg_manual':False})
        self.assertIn('OpenAlex + Aurora (automated classification)',html); self.assertIn('<img',html)

    def test_openalex_exact_doi_fallback(self):
        fixture={'doi':'https://doi.org/10.1234/a','sustainable_development_goals':[{'id':'https://openalex.org/sdgs/9','score':.45}]}
        with patch.object(s,'request_json',side_effect=[s.SDGError('HTTP 404',404),{'results':[fixture]}]) as req:
            self.assertEqual(s.openalex('10.1234/a','key'),({9:.45},''))
            self.assertEqual(req.call_args.kwargs['params']['filter'],'doi:https://doi.org/10.1234/a')
    def test_openalex_error_status(self):
        p=self.paper()
        with patch.object(s,'openalex',side_effect=s.SDGError('HTTP 401',401)),patch.object(s,'crossref_abstract',return_value=''),patch.object(s,'aurora',side_effect=s.SDGError('unavailable')):
            s.classify(p,'key'); self.assertEqual(p['sdg_classification']['openalex_status'],'authentication_error')
    def test_openalex_no_labels_status(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({},'abstract')),patch.object(s,'aurora',return_value={}):
            s.classify(p,'key'); self.assertEqual(p['sdg_classification']['openalex_status'],'no_labels')

    def test_real_openalex_un_metadata_identifiers(self):
        fixture={'doi':'https://doi.org/10.1234/a','sustainable_development_goals':[
            {'id':'https://metadata.un.org/sdg/9','score':.84,'display_name':'Industry, innovation and infrastructure'},
            {'id':'http://metadata.un.org/sdg/12','score':.71,'display_name':'Responsible consumption and production'}],
            'abstract_inverted_index':{'pavement':[0]}}
        with patch.object(s,'request_json',return_value=fixture):
            self.assertEqual(s.openalex('10.1234/a','key'),({9:.84,12:.71},'pavement'))
        self.assertIsNone(s.goal('https://metadata.un.org/sdg/9.4'))

    def test_real_aurora_jsonld_predictions(self):
        def pred(code,value,kind='Goal'):
            return {'prediction':value,'sdg':{'@type':'sdg','id':'http://metadata.un.org/sdg/'+code,'code':code,'type':kind,'label':'Goal '+code}}
        fixture={'@self':'example','text':'test','model':'aurora-sdg-multi','predictions':[pred('9',.91),pred('12',.83),pred('11',.04),pred('9.4',.99,'Target')]}
        self.assertEqual(s.aurora_scores(fixture),{9:.91,12:.83,11:.04})

    def test_doi_mismatch_falls_back_to_exact_filter(self):
        fixture={'doi':'https://doi.org/10.1234/a','sustainable_development_goals':[{'id':'https://metadata.un.org/sdg/9','score':.85}]}
        with patch.object(s,'request_json',side_effect=[dict(fixture,doi='https://doi.org/10.1234/other'),{'results':[fixture]}]):
            self.assertEqual(s.openalex('10.1234/a','key'),({9:.85},''))
