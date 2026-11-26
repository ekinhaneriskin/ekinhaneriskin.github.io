#!/usr/bin/env python3
"""Build static academic homepage from bibliography and editorial records."""
import json, re, shutil, argparse, os, sys
from pathlib import Path
from datetime import date
from html import escape
from urllib.parse import urlparse, quote
if __package__:
    from .publication_metadata import metadata, top_label, topic_groups
    from .citation_display import author_html, citation, exports
    from .github_repos import repositories_for_site
    from .publication_records import normalize_doi, valid_doi, deduplicate
else:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from tools.publication_metadata import metadata, top_label, topic_groups
    from tools.citation_display import author_html, citation, exports
    from github_repos import repositories_for_site
    from publication_records import normalize_doi, valid_doi, deduplicate
ROOT=Path(__file__).resolve().parents[1]
def h(s): return escape(str(s or ''),quote=True)
def doi(s): return normalize_doi(s)
def web(s):
    p=urlparse(str(s or '')); return str(s) if p.scheme=='https' and p.netloc and not p.username and not p.password else ''
def link(url,label,cls=''):
    return f'<a href="{h(url)}" class="{h(cls)}">{h(label)}</a>' if url else ''
def paper_access(e):
    a=e.get('access',{}); kind=a.get('kind'); url=web(a.get('url'))
    if kind=='publisher_oa' and url and a.get('license') and web(a.get('policy')):
        return url,'Open access full text',a['license']
    if kind!='approved_file' or a.get('approved') is not True: return None
    if a.get('version') not in ('accepted manuscript','preprint','version of record') or not a.get('license') or not web(a.get('policy')) or not a.get('notice'): return None
    try:
        if date.fromisoformat(a['release_on'])>date.today(): return None
    except (KeyError,ValueError,TypeError): return None
    path=Path(a.get('path',''))
    if path.is_absolute() or len(path.parts)!=2 or path.parts[0]!='papers' or not re.fullmatch(r'[A-Za-z0-9_.-]+\.pdf',path.name,re.I): return None
    actual=ROOT/path
    if not actual.is_file() or actual.is_symlink() or actual.resolve().parent!=(ROOT/'papers').resolve(): return None
    return path.as_posix(),a['version'].capitalize()+' (PDF)',a['license']+' · '+a['notice']
def displayed_access(e):
    # DOI already links to the publisher; only separately hosted, approved PDFs need an extra link.
    return paper_access(e) if e.get('access', {}).get('kind') == 'approved_file' else None
SDG_NAMES = {1:'No poverty',2:'Zero hunger',3:'Good health and well-being',4:'Quality education',5:'Gender equality',6:'Clean water and sanitation',7:'Affordable and clean energy',8:'Decent work and economic growth',9:'Industry, innovation and infrastructure',10:'Reduced inequalities',11:'Sustainable cities and communities',12:'Responsible consumption and production',13:'Climate action',14:'Life below water',15:'Life on land',16:'Peace, justice and strong institutions',17:'Partnerships for the goals'}
def sdg_impact(p):
    goals = list(dict.fromkeys(int(x) for x in (p.get('sdg') or []) if str(x).isdigit() and 1 <= int(x) <= 17))
    if not goals: return ''
    items = []
    for n in goals:
        raw_source=(p.get('sdg_sources') or {}).get(str(n),p.get('sdg_source'))
        source=raw_source+' (automated classification)' if (str(n) in (p.get('sdg_sources') or {}) or p.get('sdg_manual') is not True) and raw_source in ('OpenAlex + Aurora','OpenAlex','Aurora + Elsevier model','OpenAlex / Aurora') else 'Manual / existing assignment'
        # Original UN icons; goal names remain accessible without visible adjacent text.
        src=f'https://www.un.org/sustainabledevelopment/wp-content/uploads/2019/08/E-Inverted-Icons_WEB-{n:02d}-1024x1024.png'
        items.append(f'<a class="sdg-chip" href="https://sdgs.un.org/goals/goal{n}" title="SDG {n}: {h(SDG_NAMES[n])} · {h(source)}" aria-label="SDG {n}: {h(SDG_NAMES[n])}"><img src="{src}" width="38" height="38" loading="lazy" decoding="async" alt="SDG {n}: {h(SDG_NAMES[n])}"></a>')
    return '<div class="impact" aria-label="Sustainable Development Goals"><div class="sdg-list">'+''.join(items)+'</div></div>'
def title_link(p):
    d=doi(p.get('doi')); u='https://doi.org/'+quote(d,safe='/():;._-') if d.startswith('10.') else web(p.get('scopus_link')) or web(p.get('wos_link')) or web(p.get('trdizin_link'))
    return link(u,p['title']) if u else h(p['title'])
def actions(p,e,plum=False):
    d=doi(p.get('doi')); aa=[]
    if d.startswith('10.'):
        u='https://doi.org/'+quote(d,safe='/():;._-')
        aa.append(f'<a href="{h(u)}" class="doi-link" title="{h(d)}" aria-label="DOI {h(d)}">DOI</a>' if plum else link(u,d,'doi-link'))
    for key,label in ([] if plum else [('wos_link','WoS'),('scopus_link','Scopus'),('trdizin_link','TR Dizin')]):
        u=web(p.get(key));
        if u: aa.append(link(u,label,'index-link '+key.removesuffix('_link')))
    a=displayed_access(e)
    if a: aa.append(link(a[0],a[1],'full')); aa.append(f'<span class="license">{h(a[2])}</span>')
    if web(e.get('video')): aa.append(link(e['video'],'Video overview'))
    if not plum and e.get('repo'): aa.append(link('https://github.com/ekinhaneriskin/'+quote(e['repo'],safe=''),'Research code'))
    if plum and d.startswith('10.'):
        aa.append(cite_controls(p,metadata(p)))
    return '<div class="actions">'+''.join(aa)+'</div>' if aa else ''
def plum_widget(p):
    d=doi(p.get('doi'))
    if d.startswith('10.'):
        config=h(json.dumps({'hideWhenEmpty':True,'printSize':'medium','popupDirection':'top'},separators=(',',':')))
        return f'<span class="plum-holder"><plumx-widget type="artifact" identifier-type="doi" identifier="{h(d)}" display="plumprint" theme="Liberty" config="{config}"></plumx-widget></span>'
    return ''
def cite_controls(p,m):
    d=doi(p.get('doi')); formats={'APA-style' if m['crossref'].get('authors') else 'Bibliographic citation':citation(p,m),**exports(p,m)}
    # Native disclosure works without JS; copy buttons are progressively enhanced.
    blocks=[]
    for label,value in formats.items():
        blocks.append(f'<div class="cite-format"><label>{h(label)}<textarea readonly rows="3">{h(value)}</textarea></label><button type="button" class="btn copy-cite" hidden>Copy {h(label)}</button></div>')
    if 'BibTeX' not in formats:
        base='https://api.crossref.org/works/'+quote(d,safe='/')+'/transform/'
        blocks.append('<div class="cite-downloads">'+link(base+'application/x-bibtex','BibTeX (Crossref)')+' '+link(base+'application/x-research-info-systems','RIS (Crossref)')+'</div>')
    fwci=m['openalex'].get('fwci'); pct=m['openalex'].get('percentile')
    if fwci is not None or pct is not None:
        detail=' · '.join(x for x in (f'FWCI: {fwci:.2f}' if isinstance(fwci,(int,float)) else '',f'Citation percentile: {pct*100:.1f}' if isinstance(pct,(int,float)) else '') if x)
        blocks.append(f'<p class="cite-metrics">{h(detail)} · OpenAlex ({h(m["openalex"].get("checked_on"))})</p>')
    return '<details class="cite-details"><summary>Cite</summary><div class="cite-panel">'+''.join(blocks)+'<span class="copy-status" role="status"></span><p class="note">Generated from available bibliographic metadata; verify formatting before submission.</p></div></details>'

def publication_info(p,e,m,badge,indices):
    oa=m['openalex']; label=top_label(p,m); badges=[badge] if badge else []
    if label: badges.append(f'<span class="top-cited" title="OpenAlex normalized citation percentile · checked {h(oa.get("checked_on"))}">{h(label)}</span>')
    for key,name in [('scopus_link','Scopus'),('wos_link','WoS'),('trdizin_link','TR Dizin')]:
        if web(p.get(key)): badges.append(link(web(p[key]),name,'index-link '+key.removesuffix('_link')))
    if oa.get('is_oa') is True or paper_access(e) and e.get('access',{}).get('kind')=='publisher_oa':
        source='OpenAlex · '+str(oa.get('oa_status') or '') if oa.get('is_oa') is True else 'Publisher open access (editorial record)'
        badges.append(f'<span class="oa-indicator" title="{h(source)}"><svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0"/></svg> Open Access</span>')
    return '<div class="record-badges">'+''.join(badges)+'</div>' if badges else ''

def author_metrics_html(m):
    if os.getenv('SHOW_SCOPUS_METRICS','').lower()!='true': return ''
    if not isinstance(m,dict) or m.get('source')!='Scopus API': return ''
    try:
        stamp=date.fromisoformat(m.get('as_of',''))
        if stamp>date.today(): return ''
    except (TypeError,ValueError): return ''
    fields=[('citation_count','Citations'),('h_index','h-index'),('document_count','Scopus-indexed documents')]
    if not all(str(m.get(k,'')).isdigit() for k,_ in fields): return ''
    if int(m['document_count'])<=0 or int(m['h_index'])>int(m['document_count']) or int(m['h_index'])**2>int(m['citation_count']): return ''
    stats=''.join(f'<div class="stat"><strong>{int(m[k]):,}</strong><span>{label}</span></div>' for k,label in fields)
    source=link('https://www.scopus.com/authid/detail.uri?authorId=57039193000','Scopus author profile')
    return f'<section class="metrics" aria-label="Scopus research metrics">{stats}<p class="metric-note">{source} · Updated {h(stamp.isoformat())}</p></section>'
def build():
    raw=json.loads((ROOT/'publications.json').read_text()); ed=json.loads((ROOT/'editorial.json').read_text()); raw=raw if isinstance(raw,dict) else {'publications':raw,'metrics':{}}; pubs=list(raw['publications']); papers=ed['papers']; m=raw.get('metrics',{}); existing={doi(p.get('doi')) for p in pubs if p.get('doi')}; pubs.extend({'doi':d,**e['bibliography']} for d,e in papers.items() if e.get('bibliography') and doi(d) not in existing)
    pubs=[p for p in deduplicate(pubs) if valid_doi(p.get('doi'))]
    bydoi={p['doi']:p for p in pubs}
    pubs=sorted(pubs,key=lambda p:(str(p.get('year') or '0000'),str(p.get('date') or '')),reverse=True)
    rows=[]; features=[]; all_groups=set(); all_types=set()
    for d in dict.fromkeys([*(ed.get('featured') or []), *papers]):
        p=bydoi.get(doi(d)); e=papers.get(doi(d),{})
        if not p or not web(e.get('video')): continue
        features.append(f'<article class="feature"><span class="tag">{h(e.get("topic","Research"))}</span><h3>{title_link(p)}</h3><p>{h(e.get("summary"))}</p><div class="meta">{h(p.get("journal"))} · {h(p.get("year"))}</div>{actions(p,e)}{sdg_impact(p)}</article>')
    for k,p in enumerate(pubs):
        d=doi(p.get('doi')); e=papers.get(d,{}); indices=[]
        for idx,field in [('scopus','scopus_link'),('wos','wos_link'),('trdizin','trdizin_link')]:
            if web(p.get(field)): indices.append(idx)
        if displayed_access(e): indices.append('fulltext')
        if 'wos' in indices and 'scopus' in indices: indices.append('both')
        elif 'wos' in indices: indices.append('wos-only')
        elif 'scopus' in indices: indices.append('scopus-only')
        else: indices.append('neither')
        citations=p.get('citations'); ci=int(citations) if str(citations).isdigit() else -1
        pm=metadata(p); groups=topic_groups(pm); all_groups.update(groups)
        if pm['type']: all_types.add(pm['type'])
        search=(' '.join(str(p.get(x) or '') for x in ('title','author','journal','doi'))+' '+ ' '.join(pm['topics']+groups)+' '+ ' '.join(str(a.get('given',''))+' '+str(a.get('family','')) for a in pm['crossref'].get('authors',[]))).lower()
        attr=f'data-order="{k}" data-year="{h(p.get("year"))}" data-title="{h(p["title"])}" data-search="{h(search)}" data-indices="{" ".join(indices)}" data-citations="{ci}" data-wos-citations="{int(p['wos_citations']) if str(p.get('wos_citations','')).isdigit() else -1}"'
        attr+=f' data-type="{h(pm["type"])}" data-topics="{h(json.dumps(groups,ensure_ascii=False))}"'
        badge=f'<span class="citations-count" title="Scopus citation count" aria-label="Scopus citations: {ci}">Cited: {ci}</span>' if ci>0 and 'scopus' in indices else ''
        ctext=''
        wc=p.get('wos_citations')
        if str(wc).isdigit() and 'wos' in indices: ctext+=f' · WoS citations: {wc}'
        volume,issue=pm['volume'],pm['issue']; pages=pm['page']; article=pm['article-number']
        bibliog=' · '.join(x for x in ('Vol. '+str(volume) if volume else '', 'Issue '+str(issue) if issue else '', 'Article '+str(article) if article else 'pp. '+str(pages) if pages else '') if x)
        topics=' · '.join([x for x in [pm['type'],*pm['topics'][:2]] if x])
        topic_html=f'<p class="record-topics">{h(topics)}</p>' if topics else ''
        impacts=sdg_impact(p)+plum_widget(p)
        rows.append(f'<article class="pub" {attr}><div class="year">{h(p.get("year") or "—")}</div><div class="pub-body"><div class="pub-heading"><h3>{title_link(p)}</h3></div><p class="record-authors">{author_html(p,pm,h)}</p><p><i>{h(p.get("journal"))}</i>{h(" · "+bibliog if bibliog else "")}{h(ctext)}</p>{topic_html}{publication_info(p,e,pm,badge,indices)}<div class="record-impact">{impacts}</div>{actions(p,e,True)}</div></article>')

    metrics=author_metrics_html(m)
    repos=[]
    for r in repositories_for_site(ed, ROOT):
        details=' · '.join(x for x in (r['name'],r['language'],'Archived' if r['archived'] else '') if x)
        description=f'<p>{h(r["description"])}</p>' if r['description'] else ''
        repos.append(f'<a class="repo" href="{h(r["url"])}"><h3>{h(r["title"])} ↗</h3>{description}<small>{h(details)}</small></a>')
    if not repos: repos.append('<p class="note">No public repositories listed. See the GitHub profile for details.</p>')
    years=''.join(f'<option value="{h(y)}">{h(y)}</option>' for y in sorted({str(p['year']) for p in pubs if p.get('year')},reverse=True))
    meta=raw.get('metadata',{}); update=' '.join(f'{label}: {meta.get(key) or "not yet recorded"}. ' for key,label in [('scopus_publications_as_of','Scopus sync'),('wos_publications_as_of','WoS API sync'),('orcid_as_of','ORCID sync')])
    t=(ROOT/'tools/index.template.html').read_text(); vals={'METRICS':metrics,'FEATURED':''.join(features),'PUBLICATIONS':''.join(rows),'YEARS':years,'COUNT':str(len(pubs)),'REPOSITORIES':''.join(repos),'UPDATE':h(update),'CURRENT_YEAR':str(date.today().year),'FULLTEXT_OPTION':'<option value="fulltext">Author-shared PDF available</option>' if any(displayed_access(papers.get(doi(p.get('doi')),{})) for p in pubs) else '', 'FULLTEXT_NOTE':' Author-shared PDFs are provided only for individually approved versions.' if any(displayed_access(papers.get(doi(p.get('doi')),{})) for p in pubs) else ''}
    vals['TOPIC_OPTIONS']=''.join(f'<option value="{h(v)}">{h(v)}</option>' for v in sorted(all_groups))
    vals['TYPE_OPTIONS']=''.join(f'<option value="{h(v)}">{h(v)}</option>' for v in sorted(all_types))
    for k,v in vals.items(): t=t.replace('@@'+k+'@@',v)
    (ROOT/'index.html').write_text(t,encoding='utf-8'); return ed

def stage(ed):
    out=ROOT/'_site'; shutil.rmtree(out,ignore_errors=True); out.mkdir()
    for n in ['index.html','foto.jpeg','background.jpg','background2.jpeg','icon.ico','CNAME']:
        p=ROOT/n
        if p.is_file() and not p.is_symlink(): shutil.copy2(p,out/n)
    for e in ed['papers'].values():
        a=displayed_access(e)
        if a and a[0].startswith('papers/'):
            dst=out/a[0]; dst.parent.mkdir(exist_ok=True); shutil.copy2(ROOT/a[0],dst)
    (out/'.nojekyll').touch()
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--stage',action='store_true'); args=parser.parse_args(); e=build()
    if args.stage: stage(e)
