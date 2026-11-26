import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import requests
from tools import github_repos as g


def record(name, **overrides):
    return {'name':name,'owner':{'login':g.OWNER},'private':False,'fork':False,'visibility':'public','language':'Python','description':'Description',**overrides}


def response(records, next_page=False):
    r=Mock(); r.json.return_value=records; r.links={'next':{}} if next_page else {}; return r


class GithubRepositoriesTests(unittest.TestCase):
    def test_public_discovery_pagination_and_exclusions(self):
        session=Mock(); session.get.side_effect=[response([record('research'),record(g.OWNER+'.github.io'),record(g.OWNER),record('private',private=True),record('fork',fork=True)],True),response([record('new-study'),record('foreign',owner={'login':'other'}),record('archive',archived=True)])]
        found=g.fetch_public_repositories(session)
        self.assertEqual([r['name'] for r in found],['archive','new-study','research'])
        self.assertTrue(found[0]['archived']); self.assertEqual(session.get.call_count,2)
    def test_cached_list_respects_editorial_and_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/g.CACHE).write_text(json.dumps({'owner':g.OWNER,'repositories':[{'name':'Research','description':'api'},{'name':'new-paper','description':'new','language':'R'},{'name':'hide-me'},{'name':g.OWNER+'.github.io'}]}))
            ed={'repositories':[{'name':'research','title':'Custom title','description':'Curated'},{'name':'gone','title':'Gone'}],'exclude_repositories':['HIDE-ME']}
            found=g.repositories_for_site(ed,root)
            self.assertEqual([r['name'] for r in found],['Research','new-paper']); self.assertEqual(found[0]['description'],'Curated'); self.assertEqual(found[1]['language'],'R')
    def test_failure_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); target=root/g.CACHE; target.write_text('old snapshot'); session=Mock(); session.get.side_effect=requests.Timeout
            self.assertFalse(g.refresh(root,session)); self.assertEqual(target.read_text(),'old snapshot')
    def test_fallback_excludes_website(self):
        with tempfile.TemporaryDirectory() as tmp:
            ed={'repositories':[{'name':g.OWNER+'.github.io'},{'name':'study'}]}
            self.assertEqual([r['name'] for r in g.repositories_for_site(ed,Path(tmp))],['study'])
    def test_success_empty_replaces_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); session=Mock(); session.get.return_value=response([])
            self.assertTrue(g.refresh(root,session)); self.assertEqual(g.repositories_for_site({'repositories':[{'name':'study'}]},root),[])
