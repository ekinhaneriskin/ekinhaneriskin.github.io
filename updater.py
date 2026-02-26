import json
import requests
import os
import xml.etree.ElementTree as ET

# --- AYARLAR ---
SCOPUS_API_KEY = os.environ.get('SCOPUS_API_KEY') or 'a5210b26f0964c067ea0ed118b6df34c'
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
            
            # XML Ad Alanları (Namespace)
            # ÖNEMLİ: Entry etiketinin kendisi default namespace'dedir (ön eksiz)
            ns = {
                'dns': 'http://www.w3.org/2005/Atom', # Default namespace için 'dns' takısı verdik
                'dc': 'http://purl.org/dc/elements/1.1/',
                'prism': 'http://prismstandard.org/namespaces/basic/2.0/'
            }
            
            # 'entry' etiketlerini bul (dns:entry olarak arıyoruz)
            for entry in root.findall('dns:entry', ns):
                title_node = entry.find('dc:title', ns)
                title = title_node.text if title_node is not None else ""
                
                if not title: continue # Başlıksız veriyi atla

                doi_node = entry.find('prism:doi', ns)
                doi = doi_node.text if doi_node is not None else ""
                
                # Atıf sayısı (prefix'siz düz etiket)
                cit_node = entry.find('dns:citedby-count', ns)
                citations = cit_node.text if cit_node is not None else "0"

                eid_node = entry.find('dns:eid', ns)
                scopus_link = ""
                if eid_node is not None:
                    scopus_link = f"https://www.scopus.com/record/display.uri?eid={eid_node.text}"

                pubs.append({
                    "title": title,
                    "author": (entry.find('dc:creator', ns).text if entry.find('dc:creator', ns) is not None else "Eriskin, E."),
                    "year": (entry.find('prism:coverDate', ns).text.split('-')[0] if entry.find('prism:coverDate', ns) is not None else ""),
                    "journal": (entry.find('prism:publicationName', ns).text if entry.find('prism:publicationName', ns) is not None else ""),
                    "index": "scopus",
                    "doi": doi,
                    "citations": citations,
                    "scopus_link": scopus_link
                })
            print(f"Scopus'tan {len(pubs)} adet kayıt başarıyla okundu.")
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
