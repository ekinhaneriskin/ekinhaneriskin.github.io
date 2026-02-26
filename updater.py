import json
import requests
import os
import xml.etree.ElementTree as ET

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
            # Sadece geçerli başlığı olanları yükle (TR Dizin kirliliğini temizlemek için)
            return { (p.get('doi') or p.get('title') or "").lower().strip(): p 
                     for p in data if p and len(p.get('title', '')) > 5 }
        except: return {}

def fetch_scopus_data():
    if not SCOPUS_API_KEY: return []
    print("Scopus taranıyor...")
    
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD&count=100"
    headers = {'Accept': 'application/xml'}
    
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            
            # Scopus XML'inde namespace karmaşasını aşmak için wildcard (*) kullanıyoruz
            for entry in root.findall('.//{*}entry'):
                # Başlık: dc:title (Namespace içinde dc olanı bul)
                title_node = entry.find('.//{http://purl.org/dc/elements/1.1/}title')
                title = title_node.text if title_node is not None else ""
                
                if not title: continue

                # DOI: prism:doi
                doi_node = entry.find('.//{http://prismstandard.org/namespaces/basic/2.0/}doi')
                doi = doi_node.text if doi_node is not None else ""
                
                # Atıf Sayısı (Ön eksiz veya atom namespace'inde olabilir)
                cit_node = entry.find('.//{*}citedby-count')
                citations = cit_node.text if cit_node is not None else "0"

                # EID ve Link
                eid_node = entry.find('.//{*}eid')
                scopus_link = f"https://www.scopus.com/record/display.uri?eid={eid_node.text}" if eid_node is not None else ""

                pubs.append({
                    "title": title,
                    "author": "Eriskin, E.", # dc:creator da aranabilir
                    "year": entry.find('.//{http://prismstandard.org/namespaces/basic/2.0/}coverDate').text.split('-')[0] if entry.find('.//{http://prismstandard.org/namespaces/basic/2.0/}coverDate') is not None else "",
                    "journal": entry.find('.//{http://prismstandard.org/namespaces/basic/2.0/}publicationName').text if entry.find('.//{http://prismstandard.org/namespaces/basic/2.0/}publicationName') is not None else "",
                    "index": "scopus",
                    "doi": doi,
                    "citations": citations,
                    "scopus_link": scopus_link
                })
            print(f"Scopus'tan {len(pubs)} kayıt başarıyla çekildi.")
    except Exception as e: 
        print(f"Scopus Hatası: {e}")
    return pubs

def fetch_orcid_data():
    # ... (Önceki ORCID kodunuz aynı kalabilir, o JSON çalıştığı için sorun çıkarmaz)
    # Ancak burada da başlıksız verileri engellemek için filtre eklemeyi unutmayın.
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
                if not title or len(title) < 5: continue
                
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
            print(f"ORCID'den {len(pubs)} yayın çekildi.")
    except: pass
    return pubs

def merge_and_save(local, fetched):
    for n in fetched:
        key = (n.get('doi') or n.get('title')).lower().strip()
        if key in local:
            # Mevcut kaydı zenginleştir
            for field in ['scopus_link', 'wos_link', 'citations', 'journal', 'author']:
                if n.get(field): local[key][field] = n[field]
            if n.get('index') == 'sci': local[key]['index'] = 'sci'
        else:
            local[key] = n
    
    # Final temizliği: TR Dizin kalıntılarını (başlığı olmayanları) uçur
    final_list = [p for p in local.values() if p and len(p.get('title', '')) > 5]
    final_list = sorted(final_list, key=lambda x: str(x.get('year', '0')), reverse=True)
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    local_pubs = load_local_data()
    all_fetched = fetch_scopus_data() + fetch_orcid_data()
    if all_fetched:
        merge_and_save(local_pubs, all_fetched)
        print(f"İşlem Tamam! Toplam {len(local_pubs)} benzersiz yayın kaydedildi.")
