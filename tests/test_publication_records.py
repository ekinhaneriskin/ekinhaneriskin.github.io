import unittest
from tools.publication_records import deduplicate, valid_doi
from tools import build
from unittest.mock import patch
from pathlib import Path
import tempfile, json, shutil

class TestPublicationRecords(unittest.TestCase):
    def test_normalized_doi_and_missing(self):
        self.assertEqual(valid_doi(' HTTPS://DX.DOI.ORG/10.1234/A%2FB '),'10.1234/a/b')
        self.assertEqual(valid_doi('DOI: 10.1234/A'),'10.1234/a')
        for d in ('',None,'10.invalid/a','10.1234/','not a doi'):
            self.assertEqual(valid_doi(d),'')
    def test_merge_fields_and_citations(self):
        a={'doi':'DOI: 10.1234/A','title':'Paper','citations':4,'scopus_as_of':'2026-01-01','scopus_link':'https://example.com/scopus','sdg':[9]}
        b={'doi':'https://doi.org/10.1234/a','title':'Paper','citations':6,'scopus_as_of':'2026-02-01','wos_link':'https://example.com/wos','wos_citations':3,'sdg':[11]}
        out=deduplicate([a,b]); self.assertEqual(len(out),1)
        p=out[0]; self.assertEqual(p['citations'],6); self.assertEqual(p['wos_citations'],3)
        self.assertIn('scopus_link',p); self.assertIn('wos_link',p); self.assertEqual(p['sdg_manual_goals'],[9,11]); self.assertEqual(a['sdg'],[9])
    def test_manual_auto_ownership_and_replace(self):
        a={'doi':'10.1234/a','sdg':[9],'sdg_manual_goals':[9],'sdg_manual':True,'sdg_mode':'add'}
        b={'doi':'10.1234/a','sdg':[11],'sdg_classification':{'applied':[11]},'sdg_source':'OpenAlex'}
        p=deduplicate([a,b])[0]; self.assertEqual(p['sdg'],[9,11]); self.assertEqual(p['sdg_manual_goals'],[9]); self.assertEqual(p['sdg_sources']['11'],'OpenAlex')
        p=deduplicate([a|{'sdg_mode':'replace'},b])[0]; self.assertEqual(p['sdg'],[9])
    def test_distinct_and_missing_retained_in_archive(self):
        records=[{'doi':d,'title':'Same'} for d in ('10.1234/a','10.1234/b','','')]
        self.assertEqual(len(deduplicate(records)),4)
    def test_build_only_unique_doi(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'tools').mkdir(); shutil.copy(build.ROOT/'tools/index.template.html',root/'tools/index.template.html')
            rows=[{'title':t,'doi':d,'year':'2020'} for t,d in [('First','10.1234/a'),('Duplicate','https://doi.org/10.1234/A'),('Other','10.1234/b'),('No DOI',''),('Invalid','10.abc/foo')]]
            (root/'publications.json').write_text(json.dumps({'publications':rows})); (root/'editorial.json').write_text(json.dumps({'papers':{},'featured':[]}))
            with patch.object(build,'ROOT',root): build.build()
            html=(root/'index.html').read_text(); self.assertEqual(html.count('<article class="pub" '),2); self.assertNotIn('>No DOI<',html); self.assertIn('>2 publications<',html)
