import json
import requests
import os
from datetime import datetime

# --- AYARLAR ---
SCOPUS_API_KEY = os.environ.get('SCOPUS_API_KEY')
SCOPUS_AUTHOR_ID = '57039193000'
ORCID_ID = '0000-0002-0087-0933'
TRDIZIN_AUTHOR_ID = '341496'
JSON_FILE_PATH = 'publications.json'

def load_local_data():
    if not os.path.exists(JSON_FILE_PATH): return {}
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # Dosyadaki verileri DOI veya Başlık üzerinden bir sözlükte tutuyoruz
            return { (p.get('doi') or p.get('title') or "").lower().strip(): p for p in data if p }
        except: return {}

def fetch_scopus_data():
    if not SCOPUS_API_KEY: return []
    print("Scopus taranıyor (Zengin Veri Modu)...")
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD&sort=-coverDate&count=50"
    headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            entries = res.json().get('search-results', {}).get('entry', [])
            for e in entries:
                doi = e.get('prism:doi') or ""
                pubs.append({
                    "title": e.get('dc:title', 'Başlıksız Yayın'),
                    "author": e.get('dc:creator', 'Erişkin, E.'),
                    "year": (e.get('prism:coverDate') or "2026").split('-')[0],
                    "journal": e.get('prism:publicationName', ''),
                    "index": "scopus",
                    "doi": doi,
                    "scopus_citations": e.get('citedby-count', '0'), # Scopus Atıf Sayısı
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={e.get('eid', '')}",
                    "type": e.get('subtypeDescription', 'Article')
                })
    except: pass
    return pubs

def fetch_trdizin_data():
    print("TR Dizin taranıyor (Kesin Filtre)...")
    url = "https://search.trdizin.gov.tr/api/defaultSearch/publication/?q=Ekinhan+Eriskin&order=publicationYear-DESC&limit=100"
    headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://search.trdizin.gov.tr/'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            hits = res.json().get('hits', {}).get('hits', [])
            for hit in hits:
                s = hit.get('_source', {})
                authors = s.get('authors', [])
                # Sadece senin ID'nin (341496) olduğu yayınları al
                if any(str(a.get('id')) == TRDIZIN_AUTHOR_ID for a in authors):
                    pubs.append({
                        "title": s.get('title', 'Başlıksız Yayın'),
                        "author": ", ".join([a.get('fullName', '') for a in authors]),
                        "year": str(s.get('publicationYear', '2026')),
                        "journal": s.get('journal', {}).get('name', ''),
                        "index": "trdizin",
                        "doi": s.get('doi') or "",
                        "trdizin_link": f"https://search.trdizin.gov.tr/tr/yayin/detay/{hit.get('_id', '')}",
                        "abstract_preview": s.get('abstracts', [{}])[0].get('abstract', '')[:150] + "..." # Özet önizleme
                    })
    except: pass
    return pubs

def fetch_orcid_data():
    print("ORCID taranıyor (WoS Kontrolü)...")
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
                    if eid.get('external-id-type') == 'doi': doi = eid.get('external-id-value')
                    if eid.get('external-id-type') == 'wosuid': wos = eid.get('external-id-value')
                pubs.append({
                    "title": w.get('title', {}).get('title', {}).get('value', ''),
                    "year": w.get('publication-date', {}).get('year', {}).get('value', '2026') if w.get('publication-date') else "2026",
                    "doi": doi or "",
                    "wos_link": f"https://www.webofscience.com/wos/woscc/full-record/{wos}" if wos else "",
                    "index": "sci" if wos else "other"
                })
    except: pass
    return pubs

def merge_and_save(local, fetched):
    for n in fetched:
        n_doi = str(n.get('doi') or "").strip().lower()
        n_title = str(n.get('title') or "").strip().lower()
        key = n_doi if n_doi else n_title
        if not key: continue

        if key in local:
            # EŞLEŞME: Mevcut kaydı API verileriyle zenginleştir (silme yapmaz)
            for field in ['scopus_link', 'trdizin_link', 'wos_link', 'scopus_citations', 'abstract_preview', 'journal']:
                if n.get(field): local[key][field] = n[field]
            if n.get('index') == 'sci': local[key]['index'] = 'sci'
        else:
            # YENİ YAYIN: Dosyada yoksa ekle
            local[key] = n
    
    # Yıla göre sırala
    final_list = sorted(local.values(), key=lambda x: str(x.get('year', '0')), reverse=True)
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    current_local = load_local_data()
    scopus = fetch_scopus_data()
    trdizin = fetch_trdizin_data()
    orcid = fetch_orcid_data()
    
    merge_and_save(current_local, scopus + trdizin + orcid)
    print(f"İşlem Tamam! Toplam {len(current_local)} benzersiz yayın güncellendi/kaydedildi.")
