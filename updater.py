import json
import requests
import os
from datetime import datetime

# --- AYARLAR (Secrets'tan güvenle çekiyoruz) ---
SCOPUS_API_KEY = os.environ.get('SCOPUS_API_KEY')
SCOPUS_AUTHOR_ID = '57039193000'
TRDIZIN_AUTHOR_ID = '341496'
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
    print("Scopus taranıyor...")
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD&sort=-coverDate&count=50"
    headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            for e in res.json().get('search-results', {}).get('entry', []):
                doi = e.get('prism:doi', '')
                pubs.append({
                    "title": e.get('dc:title', 'Başlıksız Scopus Yayını'),
                    "author": e.get('dc:creator', 'Erişkin, E.'),
                    "year": (e.get('prism:coverDate') or "2026").split('-')[0],
                    "index": "scopus",
                    "doi": doi if doi else "",
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={e.get('eid', '')}"
                })
            print(f"Scopus'tan {len(pubs)} yayın doğrulandı.")
    except: pass
    return pubs

def fetch_trdizin_data():
    print("TR Dizin taranıyor (Kesin Filtre Uygulanıyor)...")
    url = "https://search.trdizin.gov.tr/api/defaultSearch/publication/?q=Ekinhan+Eriskin&order=publicationYear-DESC&limit=100"
    headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://search.trdizin.gov.tr/'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            hits = res.json().get('hits', {}).get('hits', [])
            for hit in hits:
                s = hit.get('_source', {})
                # KESİN FİLTRE: Yazarlar listesinde senin ID'n (341496) var mı?
                authors = s.get('authors', [])
                if any(str(a.get('id')) == str(TRDIZIN_AUTHOR_ID) for a in authors):
                    doi = s.get('doi', '')
                    pubs.append({
                        "title": s.get('title', 'Başlıksız Yayın'),
                        "author": ", ".join([a.get('fullName', 'Erişkin, E.') for a in authors]),
                        "year": str(s.get('publicationYear', '2026')),
                        "index": "trdizin",
                        "doi": doi if doi else "",
                        "trdizin_link": f"https://search.trdizin.gov.tr/tr/yayin/detay/{hit.get('_id', '')}"
                    })
            print(f"TR Dizin'den sana ait {len(pubs)} yayın doğrulandı.")
    except: pass
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
                doi = ""
                wos = ""
                for eid in w.get('external-ids', {}).get('external-id', []):
                    if eid.get('external-id-type') == 'doi': doi = eid.get('external-id-value')
                    if eid.get('external-id-type') == 'wosuid': wos = eid.get('external-id-value')
                
                pubs.append({
                    "title": w.get('title', {}).get('title', {}).get('value', 'Bilinmeyen Başlık'),
                    "author": "Erişkin, E.",
                    "year": w.get('publication-date', {}).get('year', {}).get('value', '2026') if w.get('publication-date') else "2026",
                    "index": "sci" if wos else "other",
                    "doi": doi if doi else "",
                    "wos_link": f"https://www.webofscience.com/wos/woscc/full-record/{wos}" if wos else ""
                })
            print(f"ORCID'den {len(pubs)} yayın çekildi.")
    except: pass
    return pubs

def merge_and_save(local, fetched):
    for n in fetched:
        n_doi = n.get('doi') or ""
        n_title = n.get('title') or ""
        key = (n_doi if n_doi else n_title).lower().strip()
        if not key: continue

        if key in local:
            for link in ['scopus_link', 'trdizin_link', 'wos_link']:
                if n.get(link): local[key][link] = n[link]
            if n.get('index') == 'sci': local[key]['index'] = 'sci'
        else: local[key] = n
    
    # Sıralama: En yeni yıl en üstte
    final_list = sorted(local.values(), key=lambda x: x.get('year', '0'), reverse=True)
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    local_pubs = load_local_data()
    all_data = fetch_scopus_data() + fetch_trdizin_data() + fetch_orcid_data()
    if all_data:
        merge_and_save(local_pubs, all_data)
        print(f"İşlem Başarılı! Şuan {len(local_pubs)} benzersiz yayınınız vitrinde.")
