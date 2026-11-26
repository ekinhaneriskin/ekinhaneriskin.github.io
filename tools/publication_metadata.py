"""DOI-verified publication enrichment, independently cached from SDGs."""
import math, os, re, unicodedata
from datetime import date
from urllib.parse import quote
from .publication_records import valid_doi
from sdg_classifier import request_json, SDGError

VERSION=1
CROSSREF_TYPES={'journal-article':'Journal article','proceedings-article':'Conference paper','book-chapter':'Book chapter','book':'Book','edited-book':'Book','monograph':'Book','posted-content':'Preprint','dissertation':'Thesis','report':'Report','dataset':'Dataset','journal-review':'Review'}
OA_TYPES={'article':'Journal article','review':'Review','book-chapter':'Book chapter','book':'Book','preprint':'Preprint','dissertation':'Thesis','report':'Report','dataset':'Dataset','proceedings-article':'Conference paper'}

def text(v): return ' '.join(v.split()) if isinstance(v,str) else ''
def finite(v): return v if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 else None

def crossref(d):
    obj=request_json('GET','https://api.crossref.org/works/'+quote(d,safe='/'),headers={'User-Agent':'AcademicWebsiteUpdater/2.1 (mailto:ekinhaneriskin@sdu.edu.tr)'})
    m=obj.get('message',{}) if isinstance(obj,dict) else {}
    if valid_doi(m.get('DOI'))!=d: raise SDGError('Crossref DOI identity mismatch')
    authors=[]
    raw=m.get('author') or []
    for a in raw:
        if not isinstance(a,dict): break
        family,given,name=text(a.get('family')),text(a.get('given')),text(a.get('name'))
        if not (family or name): break
        authors.append({'family':family,'given':given,'name':name,'orcid':text(a.get('ORCID'))})
    if len(authors)!=len(raw): authors=[]
    return {'type':CROSSREF_TYPES.get(m.get('type'),''),'authors':authors,**{k:text(m.get(k)) for k in ('volume','issue','page','article-number','publisher')},'editors':[{'family':text(a.get('family')),'given':text(a.get('given')),'name':text(a.get('name'))} for a in (m.get('editor') or []) if isinstance(a,dict) and (a.get('family') or a.get('name'))]}

def openalex(d,key):
    base='https://api.openalex.org/works'; fields='doi,type,primary_location,open_access,biblio,topics,primary_topic,fwci,citation_normalized_percentile,cited_by_count,publication_year'
    params={'api_key':key,'select':fields}
    try:
        obj=request_json('GET',base+'/https://doi.org/'+quote(d,safe='/'),params=params)
        if not isinstance(obj,dict) or valid_doi(obj.get('doi'))!=d: raise SDGError('OpenAlex DOI identity mismatch',404)
    except SDGError as e:
        if e.status not in (400,404): raise
        res=request_json('GET',base,params={**params,'filter':'doi:https://doi.org/'+d,'per_page':10})
        matches=[x for x in res.get('results',[]) if isinstance(x,dict) and valid_doi(x.get('doi'))==d] if isinstance(res,dict) else []
        if len(matches)!=1: raise SDGError('OpenAlex: no unique exact DOI match',404)
        obj=matches[0]
    oa=obj.get('open_access') or {}; pct=obj.get('citation_normalized_percentile') or {}; bib=obj.get('biblio') or {}; src=(obj.get('primary_location') or {}).get('source') or {}; primary=obj.get('primary_topic') or {}
    topics=list(dict.fromkeys(text(t.get('display_name')) for t in [primary,*(obj.get('topics') or [])] if isinstance(t,dict) and text(t.get('display_name'))))[:3]
    subfield=text((primary.get('subfield') or {}).get('display_name'))
    typ=OA_TYPES.get(obj.get('type'),'')
    # OpenAlex article can also be a proceedings contribution. Do not assume journal without source evidence.
    if obj.get('type')=='article': typ='Conference paper' if src.get('type')=='conference' else 'Journal article' if src.get('type')=='journal' else ''
    first,last=text(bib.get('first_page')),text(bib.get('last_page'))
    pvalue=finite(pct.get('value'))
    return {'type':typ,'topics':topics,'subfield':subfield,'is_oa':oa.get('is_oa') if isinstance(oa.get('is_oa'),bool) else None,'oa_status':text(oa.get('oa_status')),'fwci':finite(obj.get('fwci')),'percentile':pvalue if pvalue is not None and pvalue<=1 else None,'top1':pct.get('is_in_top_1_percent') is True,'top10':pct.get('is_in_top_10_percent') is True,'cited_by_count':finite(obj.get('cited_by_count')),'publication_year':obj.get('publication_year'),'volume':text(bib.get('volume')),'issue':text(bib.get('issue')),'page':first+('–'+last if first and last and last!=first else '')}

def fresh(entry,d,today,days):
    if not isinstance(entry,dict) or entry.get('doi')!=d or entry.get('version')!=VERSION: return False
    try: return 0<=(today-date.fromisoformat(entry['checked_on'])).days<days
    except (TypeError,ValueError,KeyError): return False

def enrich(records,key=None,today=None):
    key=os.getenv('OPENALEX_API_KEY','').strip() if key is None else key; today=today or date.today(); counts={}
    for p in records:
        d=valid_doi(p.get('doi'))
        if not d: continue
        meta=p.setdefault('publication_metadata',{})
        if not isinstance(meta,dict): meta={}; p['publication_metadata']=meta
        for source,fn,days in [('crossref',lambda:crossref(d),90),('openalex',lambda:openalex(d,key),7)]:
            if source=='openalex' and not key: continue
            old=meta.get(source)
            if fresh(old,d,today,days): continue
            try:
                data=fn(); meta[source]={'doi':d,'version':VERSION,'checked_on':today.isoformat(),**data}; status='updated'
            except (SDGError,ValueError,TypeError,AttributeError,KeyError) as e:
                # Keep last valid data, never log query strings or API keys.
                status='failed'; print(f'WARNING: publication metadata {source} {d}: {str(e) if isinstance(e,SDGError) else type(e).__name__}')
            counts[source+'_'+status]=counts.get(source+'_'+status,0)+1
    print('Publication metadata: '+str(counts))
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as f: f.write('\n## Publication metadata\n\n'+('\n'.join('- '+k+': '+str(v) for k,v in sorted(counts.items())) or 'All eligible cached records are current.')+'\n')
    return counts

def metadata(p):
    d=valid_doi(p.get('doi')); meta=p.get('publication_metadata') or {}
    def src(name):
        v=meta.get(name) or {}; return v if v.get('doi')==d and v.get('version')==VERSION else {}
    cr,oa=src('crossref'),src('openalex')
    result={k:cr.get(k) or oa.get(k) or p.get(k) or '' for k in ('type','volume','issue','page','article-number','publisher')}
    return {**result,'crossref':cr,'openalex':oa,'topics':oa.get('topics') or [],'subfield':oa.get('subfield') or ''}

def top_label(p,m,today=None):
    # Conservative: wait until the publication year and three subsequent years have ended.
    today=today or date.today(); oa=m['openalex']
    try: year=max(int(oa['publication_year']),int(p.get('year') or oa['publication_year']))
    except (ValueError,TypeError,KeyError): return ''
    if today.year<year+4 or not oa.get('cited_by_count') or oa.get('percentile') is None: return ''
    return 'Top 1% cited' if oa.get('top1') else 'Top 10% cited' if oa.get('top10') else ''

def fold(s): return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c)).replace('ı','i')

def topic_groups(m):
    # Map source-provided topic labels only. Unmatched topics use the source subfield.
    rules=[('Traffic flow & driver behaviour',r'traffic flow|driver behavio|car.follow|roundabout|traffic simulation|traffic congestion'),('Intelligent transportation systems',r'traffic signal|intelligent transport|traffic control|connected vehicle|autonomous vehicle'),('Artificial intelligence & machine learning',r'machine learning|deep learning|neural network|artificial intelligence'),('Pavement engineering & management',r'pavement|asphalt|bitumen|road maintenance'),('Public transportation',r'public transport|transit|bus operation|fare polic'),('Sustainable infrastructure',r'sustainable infrastructure|recycl|waste material|life cycle|sustainable construction'),('Traffic safety',r'traffic safety|road safety|traffic accident|crash')]
    s=fold(' '.join(m['topics'])); found=[name for name,pat in rules if re.search(pat,s)]
    return found or ([m['subfield']] if m['subfield'] else [])
