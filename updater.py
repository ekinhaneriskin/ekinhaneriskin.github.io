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
    print("Scopus taranıyor (Derin Veri Çekme Modu)...")
    # view=STANDARD ile devam ediyoruz ama XML içindeki her etiketi zorlayacağız
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD&count=100"
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
                # 1. Başlık
                title_node = entry.find('dc:title', ns)
                title = title_node.text if title_node is not None else "Untitled"
                
                # 2. Atıf Sayısı (citedby-count)
                cit_node = entry.find('atom:citedby-count', ns)
                citations = cit_node.text if cit_node is not None else "0"
                
                # 3. Dergi Adı (publicationName)
                jrnl_node = entry.find('prism:publicationName', ns)
                journal = jrnl_node.text if jrnl_node is not None else ""
                
                # 4. Yazarlar (dc:creator genelde ilk yazardır, ama Scopus arama sonucunda tam liste vermez)
                # Buradaki 'dc:creator' verisini alıyoruz, yanına 'et al.' ekleyerek profesyonel gösteriyoruz.
                author_node = entry.find('dc:creator', ns)
                author = author_node.text if author_node is not None else "Eriskin, E."
                
                # 5. DOI ve Yıl
                doi_node = entry.find('prism:doi', ns)
                doi = doi_node.text if doi_node is not None else ""
                
                date_node = entry.find('prism:coverDate', ns)
                year = date_node.text.split('-')[0] if date_node is not None else "2026"

                eid_node = entry.find('atom:eid', ns)
                scopus_link = f"https://www.scopus.com/record/display.uri?eid={eid_node.text}" if eid_node is not None else ""

                pubs.append({
                    "title": title,
                    "author": author, 
                    "year": year,
                    "journal": journal,
                    "index": "scopus",
                    "doi": doi,
                    "citations": citations,
                    "scopus_link": scopus_link
                })
            print(f"Scopus'tan {len(pubs)} adet zengin verili kayıt işlendi.")
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
                doi = wos = ""
                for eid in w.get('external-ids', {}).get('external-id', []):
                    if eid.get('external-id-type') == 'doi': doi = eid.get('external-id-value') or ""
                    if eid.get('external-id-type') == 'wosuid': wos = eid.get('external-id-value') or ""
                
                pubs.append({
                    "title": w.get('title', {}).get('title', {}).get('value', 'Work Title'),
                    "author": "Eriskin, E.",
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
            # Mevcut kaydı API verileriyle (Atıf, Dergi, Link) zenginleştir
            for field in ['scopus_link', 'wos_link', 'citations', 'journal', 'author']:
                if n.get(field):
                    # Scopus'tan gelen yazar bilgisini ORCID'deki jenerik ismin üzerine yazar
                    local[key][field] = n[field]
            if n.get('index') == 'sci': local[key]['index'] = 'sci'
        else:
            local[key] = n
    
    # Sıralama
    final_list = sorted(local.values(), key=lambda x: str(x.get('year', '0')), reverse=True)
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    local_pubs = load_local_data()
    all_fetched = fetch_scopus_data() + fetch_orcid_data()
    if all_fetched:
        merge_and_save(local_pubs, all_fetched)
        print(f"İşlem Tamam! {len(local_pubs)} benzersiz yayın güncel atıf ve dergi bilgileriyle kaydedildi.")


burada var mı güncellenecek birşey
