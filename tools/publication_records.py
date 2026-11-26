"""Shared DOI identity and conservative duplicate consolidation."""
import re
from copy import deepcopy
from urllib.parse import urlsplit, unquote


def normalize_doi(value):
    text = str(value or '').strip()
    if re.match(r'^https?://(?:dx\.)?doi\.org/', text, re.I):
        text = unquote(urlsplit(text).path.lstrip('/'))
    else:
        text = re.sub(r'^doi:\s*', '', text, flags=re.I)
    return text.strip().lower()


def valid_doi(value):
    d = normalize_doi(value)
    return d if re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f\x7f]+', d) else ''


def goals(values):
    return {int(v) for v in (values or []) if str(v).isdigit() and 1 <= int(v) <= 17}


def manual_goals(p):
    if 'sdg_manual_goals' in p:
        return goals(p['sdg_manual_goals']), True
    c = p.get('sdg_classification') or {}
    manual = (p.get('sdg_manual') is True or p.get('sdg_mode') == 'replace' or
              ('sdg' in p and ('applied' not in c or goals(p['sdg']) != goals(c['applied']))))
    return (goals(p.get('sdg')) if manual else set()), manual


def combine(a, b):
    """Merge identical DOI records; never add citation counts together."""
    am, al = manual_goals(a); bm, bl = manual_goals(b)
    manual = am | bm
    replace = any(p.get('sdg_mode') == 'replace' or (locked and not mg and p.get('sdg_mode') != 'add')
                  for p, mg, locked in ((a,am,al),(b,bm,bl)))
    displayed = manual if replace else goals(a.get('sdg')) | goals(b.get('sdg')) | manual
    sources = {**(b.get('sdg_sources') or {}), **(a.get('sdg_sources') or {})}
    for p in (a,b):
        for n in goals(p.get('sdg')):
            if str(n) not in sources and p.get('sdg_source') in ('OpenAlex','OpenAlex + Aurora','Aurora + Elsevier model','OpenAlex / Aurora'):
                sources[str(n)] = p['sdg_source']
    for count, stamp, fields in (('citations','scopus_as_of',('scopus_link','first_author')),('wos_citations','wos_as_of',('wos_link','wos_uid','wos_source'))):
        if str(b.get(stamp) or '') > str(a.get(stamp) or ''):
            for k in (count,stamp,*fields):
                if b.get(k) is not None and b.get(k) != '': a[k] = deepcopy(b[k])
    if b.get('wos_source') == 'WoS Starter API' and a.get('wos_source') != 'WoS Starter API':
        for k in ('wos_link','wos_uid','wos_source'):
            if b.get(k): a[k] = b[k]
    if b.get('author') and str(a.get('author','')).endswith('(author list incomplete)') and not str(b['author']).endswith('(author list incomplete)'):
        a['author'] = b['author']
    for k,v in b.items():
        if k.startswith('sdg'): continue
        if k not in a or a[k] is None or a[k] == '' or a[k] == [] or a[k] == {}:
            a[k] = deepcopy(v)
    if any('sdg' in p or 'sdg_classification' in p for p in (a,b)) or al or bl:
        a['sdg'] = sorted(displayed)
        a['sdg_manual'] = al or bl
        if al or bl:
            a['sdg_manual_goals'] = sorted(manual)
            a['sdg_mode'] = 'replace' if replace else 'add'
        a['sdg_sources'] = {str(n): 'Manual / existing assignment' if n in manual else sources.get(str(n),'OpenAlex / Aurora') for n in displayed}
        a['sdg_source'] = 'Manual / existing assignment' if replace else 'Manual + automatic' if al or bl else 'OpenAlex / Aurora'
        # Keep prior ownership, but invalidate cache so a future refresh rechecks the merged record.
        a['sdg_classification'] = {'applied':sorted(displayed),'policy':{'manual_goals':sorted(manual)},'identity':''}
    return a


def deduplicate(records):
    result=[]; by_doi={}
    for record in records:
        p=deepcopy(record); d=valid_doi(p.get('doi'))
        if not d:
            result.append(p); continue
        p['doi']=d
        if d in by_doi:
            combine(by_doi[d],p)
        else:
            by_doi[d]=p; result.append(p)
    return result
