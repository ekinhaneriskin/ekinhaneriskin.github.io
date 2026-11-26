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
            self.assertEqual(req.call_args.kwargs['headers']['Authorization'],'Bearer test-key')
        with patch.object(s,'request_json',return_value=fixture):
            with self.assertRaises(s.SDGError): s.openalex('10.1234/other','test-key')
    def test_consensus_and_cache(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({9:.85,12:.95,11:.5},'reuse waste')),patch.object(s,'aurora',side_effect=self.models) as aur:
            self.assertEqual(s.classify(p,'key'),'classified'); self.assertEqual(p['sdg'],[9,12]); self.assertEqual(p['sdg_classification']['review_candidates'],[11]); self.assertEqual(p['citations'],20)
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
    def test_missing_abstract_and_disagreement(self):
        for oa,abstract in [({12:.95},''),({},'abstract'),({4:.95},'abstract')]:
            p=self.paper()
            with patch.object(s,'openalex',return_value=(oa,abstract)),patch.object(s,'aurora',side_effect=self.models):
                self.assertEqual(s.classify(p,'key'),'review'); self.assertNotIn('sdg',p)
    def test_failure_preserves_and_retries(self):
        p=self.paper()
        with patch.object(s,'openalex',return_value=({12:.95},'abstract')),patch.object(s,'aurora',side_effect=self.models): s.classify(p,'key')
        with patch.object(s,'openalex',side_effect=s.SDGError('unavailable')),patch.object(s,'aurora',side_effect=self.models):
            self.assertEqual(s.classify(p,'key',force=True),'review'); self.assertEqual(p['sdg'],[12]); self.assertFalse(s.manual(p))
            self.assertEqual(s.classify(p,'key'),'cached'); self.assertEqual(s.classify(p,'key',today=date.today()+timedelta(days=1)),'review')
    def test_no_key_and_source_hover(self):
        p=self.paper(); self.assertEqual(s.classify(p,''),'missing_key'); self.assertNotIn('sdg',p)
        html=b.sdg_impact({'sdg':[12],'sdg_source':'OpenAlex + Aurora','sdg_manual':False})
        self.assertIn('OpenAlex + Aurora (automated classification)',html); self.assertIn('<img',html)
