"""Conservative, cached SDG recommendations; no abstract or credential is saved."""
import json, os, re, time, math
from datetime import date
from pathlib import Path
from urllib.parse import quote
from html import unescape
import requests

VERSION = 'openalex-aurora-v2'
MODELS = ('aurora-sdg-multi', 'elsevier-sdg-multi')
AURORA_THRESHOLD = .80
CACHE_DAYS = 90
REVIEW_DAYS = 30
ERROR_DAYS = 1
class SDGError(Exception): pass

def doi(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',str(value or '').strip(),flags=re.I).lower()

def goal(value):
    if isinstance(value,bool): return None
    m = re.fullmatch(r'(?:https?://openalex\.org/sdgs/|SDG[ _-]*|Goal[ _-]*)?0*([1-9]|1[0-7])',str(value or '').strip(),re.I)
    return int(m.group(1)) if m else None

def score(value,percent=False):
    try:
        if isinstance(value,bool): return None
        s=str(value).strip(); pct=s.endswith('%'); n=float(s.rstrip('%'))
        if pct or percent: n/=100
        return n if math.isfinite(n) and 0<=n<=1 else None
    except (ValueError,TypeError): return None

def goals(value):
    return sorted({g for x in value if (g:=goal(x)) is not None}) if isinstance(value,list) else []

def request_json(method,url,**kwargs):
    # Fixed host paths; no secrets in exception messages. No key sent to Aurora.
    try:
        r=requests.request(method,url,timeout=(10,35),**kwargs)
        r.raise_for_status(); return r.json()
    except requests.RequestException as e:
        status=getattr(getattr(e,'response',None),'status_code',None)
        raise SDGError(f'{url.split("/")[2]}: HTTP {status}' if status else f'{url.split("/")[2]}: {type(e).__name__}') from None
    except ValueError: raise SDGError(f'{url.split("/")[2]}: invalid JSON') from None

def abstract_from_index(idx):
    if not isinstance(idx,dict): return ''
    words={}
    for word,positions in idx.items():
        if isinstance(positions,list):
            for i in positions:
                if isinstance(i,int) and 0<=i<20000: words[i]=word
    return ' '.join(words[i] for i in sorted(words))

def openalex(d,key):
    obj=request_json('GET','https://api.openalex.org/works/https://doi.org/'+quote(d,safe='/'),headers={'Authorization':'Bearer '+key,'Accept':'application/json'},params={'select':'doi,title,abstract_inverted_index,sustainable_development_goals'})
    if not isinstance(obj,dict) or doi(obj.get('doi'))!=d: raise SDGError('OpenAlex DOI identity mismatch')
    vals=obj.get('sustainable_development_goals')
    if not isinstance(vals,list): raise SDGError('OpenAlex SDG field missing or invalid')
    out={}
    for item in vals:
        if not isinstance(item,dict): raise SDGError('OpenAlex SDG item invalid')
        n=goal(item.get('id')); s=score(item.get('score'))
        if n is None or s is None: raise SDGError('OpenAlex SDG score invalid')
        out[n]=s
    return out,abstract_from_index(obj.get('abstract_inverted_index'))

def crossref_abstract(d):
    obj=request_json('GET','https://api.crossref.org/works/'+quote(d,safe='/'),headers={'Accept':'application/json','User-Agent':'AcademicWebsiteUpdater/2.1 (mailto:ekinhaneriskin@sdu.edu.tr)'})
    m=obj.get('message',{}) if isinstance(obj,dict) else {}
    if doi(m.get('DOI'))!=d: raise SDGError('Crossref DOI identity mismatch')
    text=m.get('abstract')
    return ' '.join(unescape(re.sub(r'<[^>]*>',' ',text)).split()) if isinstance(text,str) else ''

def aurora_scores(obj):
    """Accept explicit goal/score pairs or goal-keyed maps; fail closed on unknown schema."""
    out={}
    def put(g,v):
        n=goal(g)
        if n is None: return
        if isinstance(v,dict):
            for field in ('probability','score','confidence','value','probability_percent','percentage','prob'):
                if field in v:
                    put_value(n,v[field],field in ('probability_percent','percentage')); return
        else: put_value(n,v,False)
    def put_value(n,v,pct):
        s=score(v,pct)
        if s is None and not pct:
            # Some clients represent probability on a 0–100 scale.
            try:
                if 1<float(v)<=100: s=score(v,True)
            except (ValueError,TypeError): pass
        if s is not None: out[n]=max(s,out.get(n,0))
    def walk(x):
        if isinstance(x,list):
            for y in x: walk(y)
        elif isinstance(x,dict):
            for k in ('sdg','sdg_id','sdgId','sdg_number','sdg_label','goal','goal_id','goalId','goal_number','id','label','name','class'):
                if goal(x.get(k)) is not None:
                    put(x[k],x); return
            for k,v in x.items():
                if goal(k) is not None: put(k,v)
                elif k in ('results','result','predictions','prediction','scores','probabilities','sdgs','SDGs','goals','data','classification','classifications','labels','output','predicted_labels','prediction_results'): walk(v)
    walk(obj)
    if not out:
        shape = ', '.join(str(k)[:40] for k in list(obj)[:12]) if isinstance(obj,dict) else type(obj).__name__
        raise SDGError('Aurora response has no recognized goal-score pairs; top-level schema: '+shape)
    return out

def aurora(text,model):
    # Use the documented JSON POST API; stay well below 5 requests/sec.
    time.sleep(.25)
    return aurora_scores(request_json('POST','https://aurora-sdg.labs.vu.nl/classifier/classify/'+model,json={'text':text},headers={'Accept':'application/json'}))

def manual(p):
    if p.get('sdg_manual') is True: return True
    if 'sdg' not in p: return False
    c=p.get('sdg_classification')
    return not isinstance(c,dict) or 'applied' not in c or goals(p['sdg'])!=goals(c['applied'])

def classify(p,key,force=False,today=None):
    today=today or date.today(); stamp=today.isoformat(); d=doi(p.get('doi')); old=p.get('sdg_classification') or {}; locked=manual(p)
    if locked: p['sdg_manual']=True
    # Cache by DOI and title: a new DOI or edited title triggers a fresh attempt.
    identity=d+'|'+str(p.get('title') or '')
    if not force and old.get('version')==VERSION and old.get('identity')==identity:
        try:
            days=(today-date.fromisoformat(old['checked_on'])).days
            ttl=ERROR_DAYS if old.get('errors') else REVIEW_DAYS if old.get('status')!='classified' else CACHE_DAYS
            if 0<=days<ttl: return 'cached'
        except (KeyError,TypeError,ValueError): pass
    if not key: return 'missing_key'
    if not p.get('title'): return 'missing_title'
    errors=[]; oa={}; abstract=''; results={}
    if re.fullmatch(r'10\.\d{4,9}/\S+',d):
        try: oa,abstract=openalex(d,key)
        except SDGError as e: errors.append(str(e))
    abstract_source='OpenAlex' if abstract else None
    if not abstract and re.fullmatch(r'10\.\d{4,9}/\S+',d):
        try:
            abstract=crossref_abstract(d)
            if abstract: abstract_source='Crossref'
        except SDGError as e: errors.append(str(e))
    text=str(p['title'])+ ('\n\n'+abstract if abstract else '')
    # The published OpenAlex labels are usable independently of the Aurora service.
    # Aurora supplements these when both models agree on abstract-based labels.
    for model in MODELS:
        try: results[model]=aurora(text,model)
        except SDGError as e: errors.append(model+': '+str(e))
    oa_labels=set(oa)
    strong_by_model={m:{n for n,s in r.items() if s>=AURORA_THRESHOLD} for m,r in results.items()}
    strong_aurora=set().union(*strong_by_model.values()) if strong_by_model else set()
    aurora_agreement=set.intersection(*(strong_by_model[m] for m in MODELS)) if abstract and all(m in strong_by_model for m in MODELS) else set()
    selected=sorted(oa_labels | aurora_agreement)
    provenance={str(n): ('OpenAlex + Aurora' if n in oa_labels and n in aurora_agreement else 'OpenAlex' if n in oa_labels else 'Aurora + Elsevier model') for n in selected}
    candidates=sorted(oa_labels | strong_aurora)
    previous=goals(p.get('sdg'))
    if not locked and selected:
        # A partial provider failure must not erase previously assigned tags.
        applied_now=sorted(set(previous)|set(selected)) if errors else selected
        prior_sources=p.get('sdg_sources') or {}
        p['sdg_sources']={str(n):provenance.get(str(n),prior_sources.get(str(n),p.get('sdg_source','OpenAlex + Aurora'))) for n in applied_now}
        p['sdg']=applied_now; p['sdg_source']='OpenAlex / Aurora'; p['sdg_manual']=False
    applied=goals(p.get('sdg'))
    status='manual' if locked else 'classified' if selected else 'review' if candidates or not abstract or errors or applied else 'no_consensus'
    p['sdg_classification']={'version':VERSION,'identity':identity,'checked_on':stamp,'input':'title+abstract' if abstract else 'title only','abstract_source':abstract_source,'status':status,'openalex':{str(k):v for k,v in sorted(oa.items())},'aurora':{m:{str(k):v for k,v in sorted(r.items())} for m,r in results.items()},'recommended':selected,'recommended_sources':provenance,'review_candidates':sorted(set(candidates)-set(selected)),'applied':applied,'errors':errors}
    # Preserve automatic ownership even after an unsuccessful attempt with no sdg field.
    return status

def enrich(records,report_path,force=False):
    key=os.getenv('OPENALEX_API_KEY','').strip(); counts={}
    # Never query without the configured key. Report existing assignments even if unavailable.
    for p in records:
        result=classify(p,key,force=force) if key else 'missing_key'
        counts[result]=counts.get(result,0)+1
    report={'method':VERSION,'thresholds':{'OpenAlex':'published labels as returned','Aurora_both_models':AURORA_THRESHOLD},'counts':counts,'papers':[]}
    for p in records:
        report['papers'].append({'title':p.get('title'),'doi':doi(p.get('doi')),'displayed_sdgs':goals(p.get('sdg')),'manual':manual(p),'classification':p.get('sdg_classification')})
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SDG summary: '+json.dumps(counts,sort_keys=True))
    if not key: print('WARNING: OPENALEX_API_KEY missing; SDG enrichment skipped.')
    return counts
