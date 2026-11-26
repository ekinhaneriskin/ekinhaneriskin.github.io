#!/usr/bin/env python3
"""Refresh a public-only repository snapshot for static site builds."""
import json
import re
import time
from pathlib import Path
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'ekinhaneriskin'
DEFAULT_EXCLUDED = {f'{OWNER}.github.io', OWNER}
CACHE = 'repositories.json'


def excluded_names(editorial):
    extra = editorial.get('exclude_repositories', [])
    return DEFAULT_EXCLUDED | {str(n).strip().casefold() for n in extra if isinstance(n, str)}


def valid_name(name):
    return isinstance(name, str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name)) and name not in ('.', '..')


def fetch_public_repositories(session=requests):
    """Fetch all pages; reject malformed or incomplete responses before saving."""
    endpoint = f'https://api.github.com/users/{OWNER}/repos'
    result = {}
    for page in range(1, 101):
        for attempt in range(3):
            try:
                response = session.get(endpoint, params={'type':'owner','per_page':100,'page':page,'sort':'full_name','direction':'asc'},
                                       headers={'Accept':'application/vnd.github+json','User-Agent':'academic-website-repository-sync'}, timeout=(10,45))
                response.raise_for_status()
                break
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                status=getattr(getattr(exc,'response',None),'status_code',None)
                retryable=isinstance(exc,(requests.Timeout,requests.ConnectionError)) or status in (429,500,502,503,504)
                if not retryable or attempt==2: raise
                time.sleep(2**attempt)
        records = response.json()
        if not isinstance(records, list):
            raise ValueError('GitHub response is not a repository list')
        for record in records:
            if not isinstance(record, dict) or not valid_name(record.get('name')) or not isinstance(record.get('private'), bool) or not isinstance(record.get('fork'), bool) or not isinstance(record.get('owner'), dict):
                raise ValueError('Invalid GitHub repository record')
            if record['private'] or record.get('visibility','public') != 'public' or record['fork'] or str(record['owner'].get('login','')).casefold() != OWNER:
                continue
            name = record['name']
            if name.casefold() in DEFAULT_EXCLUDED:
                continue
            result[name.casefold()] = {'name': name, 'description': str(record.get('description') or ''),
                                     'language': str(record.get('language') or ''), 'archived': bool(record.get('archived',False))}
        if len(records) < 100 and 'next' not in response.links:
            return sorted(result.values(), key=lambda r:r['name'].casefold())
    raise ValueError('GitHub pagination safety limit reached; snapshot not replaced')


def refresh(root=ROOT, session=requests):
    try:
        repos = fetch_public_repositories(session)
        target = root / CACHE
        payload = json.dumps({'owner':OWNER, 'repositories':repos}, ensure_ascii=False, indent=2) + '\n'
        if not target.exists() or target.read_text(encoding='utf-8') != payload:
            temp = target.with_suffix('.tmp')
            temp.write_text(payload, encoding='utf-8')
            temp.replace(target)
        print(f'GitHub sync: {len(repos)} public owned non-fork repositories (before custom exclusions).')
        return True
    except (requests.RequestException, ValueError, TypeError, OSError) as exc:
        print(f'::warning::GitHub repository sync failed; previous repository list retained ({type(exc).__name__}).')
        return False


def repositories_for_site(editorial, root=ROOT):
    """Use the successful public snapshot; fall back to prior curated list only before first sync."""
    curated = {r['name'].casefold():r for r in editorial.get('repositories',[]) if isinstance(r,dict) and valid_name(r.get('name'))}
    excluded = excluded_names(editorial)
    try:
        snapshot = json.loads((root/CACHE).read_text(encoding='utf-8'))
        if snapshot.get('owner') != OWNER or not isinstance(snapshot.get('repositories'),list):
            raise ValueError('invalid repository snapshot')
        records = snapshot['repositories']
    except (OSError, ValueError, TypeError, AttributeError):
        records = list(curated.values())
    result = {}
    for r in records:
        if not isinstance(r,dict) or not valid_name(r.get('name')): continue
        name = r['name']; key = name.casefold()
        if key in excluded: continue
        override = curated.get(key,{})
        result[key] = {'name':name, 'title':override.get('title') or name.replace('-',' ').replace('_',' '),
                       'description':override.get('description') or r.get('description') or '',
                       'language':r.get('language') or '', 'archived':bool(r.get('archived',False)),
                       'url':f'https://github.com/{OWNER}/{quote(name,safe="")}'}
    # Retain curated research ordering; append newly discovered repositories alphabetically.
    order = {k:i for i,k in enumerate(curated)}
    return sorted(result.values(), key=lambda r:(order.get(r['name'].casefold(),len(order)),r['name'].casefold()))


if __name__ == '__main__':
    # Non-fatal: publication refresh and deployment can continue on GitHub API failure.
    refresh()
