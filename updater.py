#!/usr/bin/env python3
"""Non-destructive Scopus and optional Web of Science synchronization."""
import json, os, re, sys, unicodedata, tempfile
from datetime import date
from pathlib import Path
from urllib.parse import quote
import requests
import sdg_classifier
from tools.publication_records import normalize_doi, deduplicate
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'publications.json'
AUTHOR='57039193000'; ORCID='0000-0002-0087-0933'
KEY=os.getenv('SCOPUS_API_KEY'); TOKEN=os.getenv('SCOPUS_INST_TOKEN')
WOS_KEY=os.getenv('WOS_API_KEY'); RESEARCHER_ID='N-1821-2016'
WOS_URL='https://api.clarivate.com/apis/wos-starter/v1/documents'
S=requests.Session(); S.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=1,status_forcelist=[429,500,502,503,504],respect_retry_after_header=False)))
TODAY=date.today().isoformat()
class FetchError(Exception): pass
def get(url,params=None,headers=None):
    try:
        r=S.get(url,params=params,headers=headers,timeout=(10,35)); r.raise_for_status(); return r.json()
    except (requests.RequestException,ValueError) as e:
        # Never print the exception URL; query strings could contain secrets.
        status=getattr(getattr(e,'response',None),'status_code',None)
        raise FetchError(f'{url.split("/")[2]} request failed ({status or type(e).__name__})') from None
def scopus(url,params=None):
    if not KEY: raise FetchError('SCOPUS_API_KEY missing')
    headers={'Accept':'application/json','X-ELS-APIKey':KEY}
    if TOKEN: headers['X-ELS-Insttoken']=TOKEN
    return get(url,params,headers)
def clean_doi(x): return normalize_doi(x)
def norm(x): return ''.join(c for c in unicodedata.normalize('NFKC',str(x or '')).casefold() if c.isalnum())
def number(x):
    if isinstance(x,dict): x=x.get('$')
    return int(x) if str(x).isdigit() else None
def wos_uid(value):
    value=str(value or '').strip().upper()
    return value if re.fullmatch(r'WOS:[A-Z0-9]+',value) else ''
def record_wos_uid(p):
    return wos_uid(p.get('wos_uid')) or wos_uid(str(p.get('wos_link') or '').rsplit('/',1)[-1])
def compatible(a,b):
    d1,d2=clean_doi(a.get('doi')),clean_doi(b.get('doi'))
    return not(d1 and d2 and d1!=d2)
def match(p,records):
    d=clean_doi(p.get('doi')); eid=p.get('scopus_link'); uid=record_wos_uid(p); title=norm(p.get('title'))
    if d:
        exact=[r for r in records if clean_doi(r.get('doi'))==d]
        if exact: return exact[0]
    for value,extract in [(eid,lambda r:r.get('scopus_link')),(uid,record_wos_uid)]:
        if value:
            exact=[r for r in records if extract(r)==value and compatible(p,r)]
            if len(exact)==1: return exact[0]
    if title:
        def same_year(r):
            a,b=str(p.get('year','')),str(r.get('year',''))
            return not(a.isdigit() and b.isdigit() and abs(int(a)-int(b))>1)
        exact=[r for r in records if norm(r.get('title'))==title and compatible(p,r) and same_year(r)]
        if len(exact)==1: return exact[0]
    return None
def fetch_metrics():
    url=f'https://api.elsevier.com/content/author/author_id/{AUTHOR}'
    # Views may have different entitlements; never infer missing author metrics.
    for view in ('METRICS','ENHANCED','STANDARD'):
        try:
            obj=scopus(url,{'view':view}).get('author-retrieval-response',[])
            r=obj[0] if isinstance(obj,list) and obj else obj if isinstance(obj,dict) else {}
            c=r.get('coredata') or {}
            m={k:number(v) for k,v in [('h_index',r.get('h-index',c.get('h-index'))),('citation_count',c.get('citation-count')),('document_count',c.get('document-count'))]}
            if all(v is not None for v in m.values()) and m['document_count']>0 and m['h_index']<=m['document_count'] and m['h_index']**2<=m['citation_count']:
                return m|{'source':'Scopus API','as_of':TODAY}
        except FetchError as e:
            print(f'WARNING: Scopus author metrics view {view}: {e}')
    raise FetchError('Complete Scopus author metrics unavailable in permitted views; metrics section hidden')
def refresh_author_metrics(data):
    # Do not persist author-level API data in a public repository without display permission.
    # No legacy/manual metrics survive as a fallback.
    data.pop('metrics',None)
    metrics=fetch_metrics()
    if os.getenv('SHOW_SCOPUS_METRICS','').lower()=='true':
        data['metrics']=metrics
        print('Scopus author metrics refreshed.')
    else:
        print('Scopus author metrics available; public storage/display disabled.')
def fetch_publications():
    entries=[]; start=0; total=None
    while True:
        obj=scopus('https://api.elsevier.com/content/search/scopus',{'query':f'AU-ID({AUTHOR})','view':'STANDARD','sort':'-coverDate','count':25,'start':start}).get('search-results',{})
        n=number(obj.get('opensearch:totalResults'))
        if n is None or n==0: raise FetchError('Missing or zero Scopus search result count')
        if total is None: total=n
        if n!=total: raise FetchError('Result count changed while paging; retry later')
        page=obj.get('entry',[])
        if not isinstance(page,list) or not page or any('error' in e for e in page): raise FetchError('Incomplete Scopus result page')
        entries.extend(page); start+=len(page)
        if start>=total: break
        if start>=5000: raise FetchError('Scopus pagination limit reached')
    if len({e.get('eid') for e in entries if e.get('eid')})!=total: raise FetchError('Duplicate or incomplete EIDs; preserving old bibliography')
    out=[]
    for e in entries:
        title=e.get('dc:title'); eid=e.get('eid'); dt=e.get('prism:coverDate') or ''
        if not title: raise FetchError('Missing title in Scopus results')
        # STANDARD generally returns dc:creator (first author), not full author list.
        p={'title':title,'doi':clean_doi(e.get('prism:doi')),'journal':e.get('prism:publicationName') or '', 'year':dt[:4] if re.match(r'^\d{4}',dt) else '', 'date':dt,'scopus_link':'https://www.scopus.com/record/display.uri?eid='+quote(eid,safe='-'),'index':'scopus','source':'Scopus','scopus_as_of':TODAY}
        cit=number(e.get('citedby-count'))
        if cit is not None: p['citations']=cit
        if e.get('dc:creator'): p['first_author']=e['dc:creator']
        out.append(p)
    return out
def fetch_wos_query(query):
    if not WOS_KEY: raise FetchError('WOS_API_KEY missing')
    out=[]; page=1; total=None; seen=set()
    while True:
        obj=get(WOS_URL,{'db':'WOS','q':query,'limit':50,'page':page}, {'Accept':'application/json','X-ApiKey':WOS_KEY})
        n=number((obj.get('metadata') or {}).get('total')); hits=obj.get('hits',[])
        if n is None or not isinstance(hits,list): raise FetchError('Invalid WoS response')
        if total is None: total=n
        if n!=total: raise FetchError('WoS result count changed during pagination')
        if n==0 and not hits: return []
        if not hits: raise FetchError('Incomplete WoS page')
        for e in hits:
            uid=wos_uid(e.get('uid')); title=e.get('title')
            if not uid or not title or uid in seen: raise FetchError('Missing or repeated WoS record identity')
            seen.add(uid); src=e.get('source') or {}; ids=e.get('identifiers') or {}; doi=clean_doi(ids.get('doi')); year=str(src.get('publishYear') or '')
            p={'title':title,'doi':doi,'year':year,'journal':src.get('sourceTitle') or '', 'wos_uid':uid,'wos_link':'https://www.webofscience.com/wos/woscc/full-record/'+uid,'wos_source':'WoS Starter API','wos_as_of':TODAY,'source':'WoS'}
            names=[a.get('displayName') or a.get('wosStandard') for a in (e.get('names') or {}).get('authors',[])]
            if names and all(names): p['author']=', '.join(names)
            counts=[number(c.get('count')) for c in e.get('citations',[]) if c.get('db')=='WOS']
            if counts and counts[0] is not None: p['wos_citations']=counts[0]
            out.append(p)
        if len(out)>=total: break
        page+=1
        if page>100: raise FetchError('WoS pagination limit reached')
    if len(out)!=total: raise FetchError('Unexpected WoS result length')
    return out

def fetch_wos_publications():
    return fetch_wos_query(f'AI=({RESEARCHER_ID} OR {ORCID})')

def wos_backfill(records):
    # An exact DOI query recovers records not yet connected to the author profile.
    # Only update DOI-matched records; never import unrelated hits from this query.
    ds=sorted({clean_doi(p.get('doi')) for p in records if p.get('doi') and p.get('wos_as_of')!=TODAY})
    ds=[d for d in ds if re.fullmatch(r'10\.\d{4,9}/[^"\s]+',d)]
    for start in range(0,len(ds),25):
        batch=ds[start:start+25]; wanted=set(batch)
        q='DO=('+ ' OR '.join('"'+d+'"' for d in batch)+')'
        for n in fetch_wos_query(q):
            if n['doi'] in wanted:
                old=match(n,records)
                if old: merge(records,[n])

def orcid_records():
    obj=get(f'https://pub.orcid.org/v3.0/{ORCID}/works',headers={'Accept':'application/json'}); out=[]
    for g in obj.get('group',[]):
        ws=g.get('work-summary',[])
        if not ws: continue
        w=ws[0]; title=((w.get('title') or {}).get('title') or {}).get('value'); dt=w.get('publication-date') or {}; ids=(g.get('external-ids') or {}).get('external-id') or []
        # ORCID may carry an accession identifier on a group or an individual summary.
        # Only accept self identifiers; never infer WoS coverage from a DOI or journal name.
        identifiers=list(ids)
        for summary in ws:
            identifiers.extend((summary.get('external-ids') or {}).get('external-id') or [])
        dois=set(); uids=set()
        for x in identifiers:
            if x.get('external-id-relationship') not in (None,'self'): continue
            typ=str(x.get('external-id-type') or '').lower(); val=str(x.get('external-id-value') or '').strip()
            if typ=='doi' and val: dois.add(clean_doi(val))
            if typ=='wosuid' and val:
                candidate=wos_uid(val if val.upper().startswith('WOS:') else 'WOS:'+val)
                if candidate: uids.add(candidate)
        # Conflicting identifiers could describe different versions; leave those groups untouched.
        if len(dois)>1 or len(uids)>1:
            print('WARNING: Ambiguous ORCID work identifiers; skipped.')
            continue
        d=next(iter(dois),''); uid=next(iter(uids),'')
        if title:
            p={'title':title,'doi':d,'year':(dt.get('year') or {}).get('value',''),'journal':(w.get('journal-title') or {}).get('value','')}
            if uid: p.update(wos_uid=uid,wos_link='https://www.webofscience.com/wos/woscc/full-record/'+uid,wos_source='ORCID (record identifier)',source='ORCID')
            out.append(p)
    return out
def crossref(p):
    d=clean_doi(p.get('doi'))
    if not d: return
    m=get('https://api.crossref.org/works/'+quote(d,safe='/'),headers={'User-Agent':'AcademicWebsiteUpdater/2.0 (mailto:ekinhaneriskin@sdu.edu.tr)'}).get('message',{})
    aa=m.get('author',[])
    names=[(' '.join(str(a.get(k,'')).strip() for k in ('given','family')).strip() or a.get('name','')) for a in aa]
    if any(names) and (not p.get('author') or p.get('author','').endswith('(author list incomplete)')): p['author']=', '.join(x for x in names if x)
    if not p.get('journal') and m.get('container-title'): p['journal']=m['container-title'][0]
    if not p.get('year'):
        dp=(m.get('published') or {}).get('date-parts',[])
        if dp and dp[0]: p['year']=str(dp[0][0])
def merge(records,new):
    for n in new:
        old=match(n,records)
        if old is None: records.append(n.copy()); continue
        for k in ('doi','journal','year','date','scopus_link','first_author','wos_link','wos_uid','author'):
            if n.get(k) and not old.get(k): old[k]=n[k]
        if n.get('author') and str(old.get('author','')).endswith('(author list incomplete)'): old['author']=n['author']
        for k in ('citations','wos_citations','scopus_as_of','wos_as_of'):
            if k in n: old[k]=n[k]
        if n.get('wos_source')=='WoS Starter API':
            for k in ('wos_uid','wos_link','wos_source'):
                if n.get(k): old[k]=n[k]
        elif n.get('wos_source') and not old.get('wos_source'): old['wos_source']=n['wos_source']
        if n.get('scopus_link') and (not old.get('index') or old['index']=='other'): old['index']='scopus'
    return records

def merge_orcid(records,new):
    for n in new:
        # ORCID is not an index; import unmatched works only with a WoS accession number.
        old=match(n,records)
        if old or record_wos_uid(n): merge(records,[n])
    return records
def main():
    # Refuse to silently replace an invalid archive.
    data=json.loads(PATH.read_text(encoding='utf-8'))
    if isinstance(data,list): data={'metrics':{},'publications':data}
    original=data['publications']; records=deduplicate(original); removed=len(original)-len(records); meta=data.setdefault('metadata',{}); errors=[]
    # Editorial metadata keeps explicitly selected papers visible before index discovery.
    editorial=json.loads((ROOT/'editorial.json').read_text(encoding='utf-8'))
    merge(records,[{'doi':d,**e['bibliography']} for d,e in editorial.get('papers',{}).items() if e.get('bibliography')])
    try:
        new=fetch_publications(); merge(records,new); meta['scopus_publications_as_of']=TODAY; print(f'Scopus: {len(new)} records retrieved.')
    except FetchError as e: errors.append('Scopus publications: '+str(e))
    if os.getenv('SHOW_SCOPUS_METRICS','').lower()=='true':
        try: refresh_author_metrics(data)
        except FetchError as e: errors.append('Scopus author metrics: '+str(e))
    else:
        data.pop('metrics',None)
        print('INFO: Scopus author metrics disabled; optional API request skipped.')
    try:
        merge_orcid(records,orcid_records()); meta['orcid_as_of']=TODAY
        print('ORCID: matched publications enriched; WoS-identified new records imported.')
    except FetchError as e: errors.append('ORCID: '+str(e))
    if WOS_KEY:
        try:
            new=fetch_wos_publications()
            merge(records,new)
            print(f'WoS: {len(new)} author-identifier records retrieved.')
            wos_backfill(records)
            meta['wos_publications_as_of']=TODAY
        except FetchError as e: errors.append('WoS: '+str(e))
    else:
        print('INFO: WoS direct synchronization not configured (WOS_API_KEY); ORCID fallback remains active.')
    before=len(records)
    records=deduplicate(records)
    removed+=before-len(records)
    print(f'Duplicate DOI records consolidated: {removed}')
    for p in records:
        if (not p.get('author') or p.get('author','').endswith('(author list incomplete)')) and p.get('doi'):
            try: crossref(p)
            except FetchError as e: print('WARNING:',e)
    # Do not pretend a first author is a complete author list.
    for p in records:
        if p.get('first_author') and not p.get('author'): p['author']=p['first_author']+' et al. (author list incomplete)'
    sdg_classifier.enrich(records, ROOT/'sdg_report.json', force=os.getenv('FORCE_SDG_REFRESH','').lower()=='true')
    data['publications']=sorted(records,key=lambda p:(str(p.get('year') or ''),str(p.get('date') or '')),reverse=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=ROOT,delete=False) as f:
        json.dump(data,f,ensure_ascii=False,indent=2); f.write('\n'); tmp=f.name
    os.replace(tmp,PATH)
    for error in errors: print('WARNING:',error)
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f:
            f.write('\n## Publication source synchronization\n\n')
            f.write('\n'.join('- '+e.replace('\n',' ') for e in errors)+'\n' if errors else 'No publication source errors reported.\n')
    print(f'{len(records)} total records preserved.')
    return 2 if errors else 0
if __name__=='__main__': sys.exit(main())
