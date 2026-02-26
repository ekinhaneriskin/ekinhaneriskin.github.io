import json
import requests
import os
import xml.etree.ElementTree as ET

# --- GÜVENLİ AYARLAR (Secrets/Environment Variables) ---
SCOPUS_API_KEY = os.environ.get('SCOPUS_API_KEY')
SCOPUS_AUTHOR_ID = '57039193000'
ORCID_ID = '0000-0002-0087-0933'
JSON_FILE_PATH = 'publications.json'

def load_local_data():
    """Mevcut JSON dosyasını yükler ve kirli verileri (başlıksız vb.) eler."""
    if not os.path.exists(JSON_FILE_PATH): return {}
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # Yüklerken bile filtre uyguluyoruz: Başlığı olmayan veya çok kısa olanları alma
            return { 
                (p.get('doi') or p.get('title') or "").lower().strip(): p 
                for p in data if p and len(p.get('title', '')) > 5 
            }
        except: return {}

def fetch_scopus_data():
    if not SCOPUS_API_KEY: 
        print("Hata: SCOPUS_API_KEY tanımlı değil!")
        return []
    
    print("Scopus taranıyor (Temiz Veri Modu)...")
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD&count=100"
    headers = {'Accept': 'application/xml'}
    
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'dc': 'http://purl.org/dc/elements/1.1/', 'prism': 'http://prismstandard.org/namespaces/basic/2.0/'}
            
            for entry in root.findall('atom:entry', ns):
                title = entry.find('dc:title', ns).text if entry.find('dc:title', ns) is not None else ""
                if not title or len(title) < 10: continue # Kirli veri engelleme
                
                doi = entry.find('prism:doi', ns).text if entry.find('prism:doi', ns) is not None else ""
                
                pubs.append({
                    "title": title,
                    "author": entry.find('dc:creator', ns).text if entry.find('dc:creator', ns) is not None else "Eriskin, E.",
                    "year": entry.find('prism:coverDate', ns).text.split('-')[0] if entry.find('prism:coverDate', ns) is not None else "2026",
                    "journal": entry.find('prism:publicationName', ns).text if entry.find('prism:publicationName', ns) is not None else "",
                    "index": "scopus",
                    "doi": doi,
                    "citations": entry.find('atom:citedby-count', ns).text if entry.find('atom:citedby-count', ns) is not None else "0",
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={entry.find('atom:eid', ns).text}" if entry.find('atom:eid', ns) is not None else ""
                })
    except Exception as e: print(f"Scopus Hatası: {e}")
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
                title = w.get('title', {}).get('title', {}).get('value', '')
                if not title or len(title) < 10: continue
                
                doi = next((eid.get('external-id-value') for eid in w.get('external-ids', {}).get('external-id', []) if eid.get('external-id-type') == 'doi'), "")
                wos = next((eid.get('external-id-value') for eid in w.get('external-ids', {}).get('external-id', []) if eid.get('external-id-type') == 'wosuid'), "")

                pubs.append({
                    "title": title,
                    "author": "Eriskin, E.",
                    "year": w.get('publication-date', {}).get('year', {}).get('value', '2026') if w.get('publication-date') else "2026",
                    "index": "sci" if wos else "other",
                    "doi": doi,
                    "wos_link": f"https://www.webofscience.com/wos/woscc/full-record/{wos}" if wos else ""
                })
    except Exception as e: print(f"ORCID Hatası: {e}")
    return pubs

def merge_and_save(local, fetched):
    # Sadece API'den gelen doğrulanmış verileri işleme alıyoruz
    for n in fetched:
        key = (n.get('doi') or n.get('title')).lower().strip()
        if key in local:
            # Mevcut veriyi zenginleştir (Linkler ve Atıflar)
            for field in ['scopus_link', 'wos_link', 'citations', 'journal']:
                if n.get(field): local[key][field] = n[field]
            if n.get('index') == 'sci': local[key]['index'] = 'sci'
        else:
            local[key] = n
    
    # Kaydetmeden önce TR Dizin kalıntılarını (veya başlıksız verileri) bir kez daha süzüyoruz
    final_list = [p for p in local.values() if len(p.get('title', '')) > 10]
    final_list = sorted(final_list, key=lambda x: str(x.get('year', '0')), reverse=True)
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    local_data = load_local_data()
    # TR Dizin çağrısı kaldırıldı, sadece Scopus ve ORCID
    clean_fetched = fetch_scopus_data() + fetch_orcid_data()
    
    if clean_fetched:
        merge_and_save(local_data, clean_fetched)
        print(f"İşlem Tamam! Toplam {len(local_data)} temiz yayın kaydedildi.")
