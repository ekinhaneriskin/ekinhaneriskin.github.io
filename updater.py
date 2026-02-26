import json
import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime

# --- AYARLAR ---
SCOPUS_API_KEY = os.environ.get('SCOPUS_API_KEY')
SCOPUS_AUTHOR_ID = '57039193000'
ORCID_ID = '0000-0002-0087-0933'
JSON_FILE_PATH = 'publications.json'

def load_local_data():
    if not os.path.exists(JSON_FILE_PATH): return {}
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            return { (p.get('doi') or p.get('title') or "").lower().strip(): p for p in data if p }
        except: return {}

def fetch_scopus_data():
    if not SCOPUS_API_KEY: return []
    print("Scopus taranıyor (Zengin Veri & XML Parser)...")
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD"
    headers = {'Accept': 'application/xml', 'User-Agent': 'Mozilla/5.0'}
    
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'dc': 'http://purl.org/dc/elements/1.1/',
                'prism': 'http://prismstandard.org/namespaces/basic/2.0/'
            }
            
            for entry in root.findall('atom:entry', ns):
                doi = entry.find('prism:doi', ns)
                title = entry.find('dc:title', ns)
                year = entry.find('prism:coverDate', ns)
                citations = entry.find('atom:citedby-count', ns)
                eid = entry.find('atom:eid', ns)
                journal = entry.find('prism:publicationName', ns)
                creator = entry.find('dc:creator', ns)

                pubs.append({
                    "title": title.text if title is not None else "Başlıksız Scopus Yayını",
                    "author": creator.text if creator is not None else "Erişkin, E.",
                    "year": year.text.split('-')[0] if year is not None else "2026",
                    "journal": journal.text if journal is not None else "",
                    "index": "scopus",
                    "doi": doi.text if doi is not None else "",
                    "scopus_citations": citations.text if citations is not None else "0",
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={eid.text}" if eid is not None else ""
                })
            print(f"Scopus'tan {len(pubs)} kayıt çekildi.")
    except Exception as e: print(f"Scopus XML Hatası: {e}")
    return pubs

def fetch_trdizin_data():
    print("TR Dizin taranıyor...")
    url = "https://search.trdizin.gov.tr/api/defaultSearch/publication/?q=Ekinhan+Eriskin&order=publicationYear-DESC&limit=100"
    headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://search.trdizin.gov.tr/'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            hits = res.json().get('hits', {}).get('hits', [])
            for hit in hits:
                s = hit.get('_source', {})
                if not s: continue # Boş kaynak kontrolü
                
                doi = s.get('doi', '')
                title = s.get('title', 'Başlıksız Yayın')
                year = s.get('publicationYear', '2026')
                
                # Yazar listesini güvenli bir şekilde çekelim
                authors_raw = s.get('authors', [])
                author_names = []
                if authors_raw:
                    for a in authors_raw:
                        if a and a.get('fullName'):
                            author_names.append(a.get('fullName'))
                
                # Dergi ismini güvenli çekelim
                journal_data = s.get('journal')
                j_name = journal_data.get('name', '') if journal_data else ''

                pubs.append({
                    "title": title,
                    "author": ", ".join(author_names) if author_names else "Erişkin, E.",
                    "year": str(year),
                    "journal": j_name,
                    "index": "trdizin",
                    "doi": doi if doi else "",
                    "trdizin_link": f"https://search.trdizin.gov.tr/tr/yayin/detay/{hit.get('_id', '')}"
                })
            print(f"TR Dizin'den {len(pubs)} kayıt çekildi.")
    except Exception as e: print(f"TR Dizin Hatası: {e}")
    return pubs
def fetch_orcid_data():
    print("ORCID taranıyor...")
    url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
    headers = {'Accept': 'application/json'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            for g in res.json().get('group', []):
                w = g.get('work-summary', [{}])[0]
                doi = wos = ""
                for eid in w.get('external-ids', {}).get('external-id', []):
                    if eid.get('external-id-type') == 'doi': doi = eid.get('external-id-value') or ""
                    if eid.get('external-id-type') == 'wosuid': wos = eid.get('external-id-value') or ""
                
                pubs.append({
                    "title": w.get('title', {}).get('title', {}).get('value', 'Bilinmeyen Başlık'),
                    "author": "Erişkin, E.",
                    "year": w.get('publication-date', {}).get('year', {}).get('value', '2026') if w.get('publication-date') else "2026",
                    "index": "sci" if wos else "other",
                    "doi": doi,
                    "wos_link": f"https://www.webofscience.com/wos/woscc/full-record/{wos}" if wos else ""
                })
            print(f"ORCID'den {len(pubs)} yayın çekildi.")
    except: pass
    return pubs

def merge_and_save(local, fetched):
    for n in fetched:
        n_doi = str(n.get('doi') or "").strip().lower()
        n_title = str(n.get('title') or "").strip().lower()
        key = n_doi if n_doi else n_title
        if not key: continue

        if key in local:
            # Eşleşme varsa sadece boş alanları doldur (Manuel veriyi korur)
            for field in ['scopus_link', 'trdizin_link', 'wos_link', 'scopus_citations', 'journal']:
                if n.get(field) and not local[key].get(field):
                    local[key][field] = n[field]
            if n.get('index') == 'sci': local[key]['index'] = 'sci'
        else:
            # Dosyada yoksa yeni olarak ekle
            local[key] = n
    
    # Yıla göre azalan sıralama
    final_list = sorted(local.values(), key=lambda x: str(x.get('year', '0')), reverse=True)
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    current_local = load_local_data()
    all_fetched = fetch_scopus_data() + fetch_trdizin_data() + fetch_orcid_data()
    if all_fetched:
        merge_and_save(current_local, all_fetched)
        print(f"İşlem Tamam! Toplam {len(current_local)} benzersiz yayın güncellendi/kaydedildi.")
