"""Pure formatting helpers; keep original author order and safe text exports."""
import re
from urllib.parse import quote
from .publication_metadata import fold, text
from .publication_records import valid_doi

OWNER='0000-0002-0087-0933'

def is_owner(a):
    orcid=str(a.get('orcid') or '').rstrip('/').rsplit('/',1)[-1]
    if orcid: return orcid==OWNER
    return fold(a.get('family',''))=='eriskin' and fold(a.get('given','')).strip('. ') in ('e','ekinhan')

def full_name(a):
    return a.get('name') or ' '.join(x for x in (a.get('given'),a.get('family')) if x)

def original_authors(p):
    return str(p.get('author') or 'Author metadata pending')

def author_html(p,m,h):
    aa=m['crossref'].get('authors') or []
    # Preserve the existing complete author list verbatim. Fill missing or explicitly
    # incomplete lists from the publisher's ordered author metadata.
    if aa and (not p.get('author') or 'incomplete' in original_authors(p) or re.search(r'\bet al\.',original_authors(p),re.I)):
        return ', '.join('<strong>'+h(full_name(a))+'</strong>' if is_owner(a) else h(full_name(a)) for a in aa)
    # Existing archive uses both surname-first initials and given-name-first forms.
    pattern=r'(?<!\w)(?:Er[iİı][sş]kin\s*,\s*(?:Ekinhan|E\.)|(?:Ekinhan|E\.)\s+Er[iİı][sş]kin)(?!\w)'
    s=original_authors(p); out=[]; last=0
    for match in re.finditer(pattern,s,re.I):
        out.extend([h(s[last:match.start()]),'<strong>'+h(match.group())+'</strong>']); last=match.end()
    out.append(h(s[last:])); return ''.join(out)

def initials(given):
    return ' '.join('-'.join(x[0].upper()+'.' for x in v.split('-') if x) for v in given.split() if v)

def citation(p,m):
    aa=m['crossref'].get('authors') or []
    names=[a.get('name') or (a['family']+(', '+initials(a['given']) if a.get('given') else '')) for a in aa]
    if len(names)>20: au=', '.join(names[:19])+', … '+names[-1]
    elif len(names)>1: au=', '.join(names[:-1])+', & '+names[-1]
    else: au=names[0] if names else (str(p.get('author') or '') if 'incomplete' not in original_authors(p) else '')
    year=str(p.get('year') or 'n.d.'); title=str(p.get('title') or '').rstrip('.'); journal=str(p.get('journal') or ''); d=valid_doi(p.get('doi'))
    vol,issue,page,article=m['volume'],m['issue'],m['page'],m['article-number']; pub=m['publisher']; typ=m['type']
    loc=(str(vol)+('('+str(issue)+')' if issue else '')) if vol else ('('+str(issue)+')' if issue else '')
    pages='Article '+str(article) if article else str(page or '')
    if typ in ('Book chapter','Conference paper') and pub:
        editors=[full_name(a) for a in m['crossref'].get('editors',[])]; source='In '+((', '.join(editors)+' (Ed'+('s' if len(editors)>1 else '')+'.), ') if editors else '')+journal+(' (pp. '+pages+')' if pages else '')+'. '+pub
    else: source=', '.join(x for x in (journal,loc,pages) if x)
    return ' '.join(x for x in ((au.rstrip('.')+'.') if au else '', '('+year+').',title+'.',source.rstrip('.')+'.' if source else '', 'https://doi.org/'+d) if x)

def exports(p,m):
    """Local exports only with structured author metadata; exact formatted exports linked separately."""
    aa=m['crossref'].get('authors') or []
    if not aa: return {}
    d=valid_doi(p.get('doi')); typ=m['type']; year=str(p.get('year') or ''); title=str(p.get('title') or ''); journal=str(p.get('journal') or '')
    kind={'Journal article':'article','Review':'article','Conference paper':'inproceedings','Book chapter':'incollection','Book':'book','Thesis':'phdthesis','Report':'techreport'}.get(typ,'misc')
    # Escape special TeX characters in metadata, preserve UTF-8 names and title capitalization.
    def tex(s):
        trans={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','&':r'\&','%':r'\%','_':r'\_','#':r'\#','$':r'\$','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
        return ''.join(trans.get(c,c) for c in str(s))
    def bibname(a): return '{'+tex(a['name'])+'}' if a.get('name') else tex(a['family'])+(', '+tex(a['given']) if a.get('given') else '')
    key=re.sub(r'[^a-zA-Z0-9]+','',fold(aa[0].get('family') or 'work')+year)+'_'+re.sub(r'[^a-zA-Z0-9]+','',d)[-16:]
    vals={'title':tex(title),'author':' and '.join(map(bibname,aa)), 'year':year,'doi':tex(d),'url':tex('https://doi.org/'+d)}
    if journal and kind not in ('book',): vals['journal' if kind=='article' else 'booktitle' if kind in ('incollection','inproceedings') else 'howpublished']=tex(journal)
    for k,v in [('volume',m['volume']),('number',m['issue']),('pages',str(m['page']).replace('–','--')),('eid',m['article-number']),('publisher',m['publisher'])]:
        if v: vals[k]=tex(v)
    if m['crossref'].get('editors'): vals['editor']=' and '.join(map(bibname,m['crossref']['editors']))
    bib='@'+kind+'{'+key+',\n'+',\n'.join('  '+k+' = {'+v+'}' for k,v in vals.items() if v)+'\n}'
    rtype={'article':'JOUR','inproceedings':'CPAPER','incollection':'CHAP','book':'BOOK','phdthesis':'THES','techreport':'RPRT'}.get(kind,'GEN')
    ris=[('TY',rtype),('TI',title)]+[('AU',a.get('name') or a['family']+(', '+a['given'] if a.get('given') else '')) for a in aa]
    ris += [('PY',year),('JO' if kind=='article' else 'T2',journal),('VL',m['volume']),('IS',m['issue']),('PB',m['publisher']),('DO',d),('UR','https://doi.org/'+d)]
    pages=re.split(r'\s*[-–—]+\s*',str(m['page']),maxsplit=1) if m['page'] else []
    if pages: ris.append(('SP',pages[0])); ris.extend([('EP',pages[1])] if len(pages)>1 else [])
    elif m['article-number']: ris.append(('SP',m['article-number']))
    ris.extend(('ED',a.get('name') or a['family']+(', '+a['given'] if a.get('given') else '')) for a in m['crossref'].get('editors',[]))
    return {'BibTeX':bib,'RIS':'\n'.join(k+'  - '+text(str(v)) for k,v in ris if v)+'\nER  - '}
