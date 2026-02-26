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
    if not SCOPUS_API_KEY: 
        print("Hata: SCOPUS_API_KEY bulunamadı.")
        return []
    
    print("Scopus taranıyor (Güvenli Parametre Modu)...")
    url = "https://api.elsevier.com/content/search/scopus"
    
    # Parametreleri ayrı bir sözlük olarak gönderiyoruz (Requests bunu otomatik encode eder)
    query_params = {
        'query': f'AU-ID({SCOPUS_AUTHOR_ID})',
        'apiKey': SCOPUS_API_KEY,
        'view': 'STANDARD',
        'sort': '-coverDate' # '-' işareti en yeniden en eskiye sıralar
    }
    
    headers = {'Accept': 'application/xml'}
    
    pubs = []
    try:
        # URL yerine params=query_params kullanıyoruz (400 hatasını bu çözer)
        res = requests.get(url, headers=headers, params=query_params)
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            entries = root.findall('.//{*}entry')
            
            for entry in entries:
                title_node = entry.find('.//{*}title')
                title = title_node.text if title_node is not None else ""
                if not title: continue

                doi_node = entry.find('.//{*}doi')
                doi = doi_node.text if doi_node is not None else ""
                
                cit_node = entry.find('.//{*}citedby-count')
                citations = cit_node.text if cit_node is not None else "0"

                eid_node = entry.find('.//{*}eid')
                eid = eid_node.text if eid_node is not None else ""
                scopus_link = f"https://www.scopus.com/record/display.uri?eid={eid}" if eid else ""

                jrnl_node = entry.find('.//{*}publicationName')
                journal = jrnl_node.text if jrnl_node is not None else ""

                date_node = entry.find('.//{*}coverDate')
                year = date_node.text.split('-')[0] if date_node is not None else "2026"

                pubs.append({
                    "title": title,
                    "author": "Eriskin, E.", 
                    "year": year,
                    "journal": journal,
                    "index": "scopus",
                    "doi": doi,
                    "citations": citations,
                    "scopus_link": scopus_link
                })
            print(f"Scopus'tan {len(pubs)} kayıt başarıyla çekildi.")
        else:
            print(f"Scopus API Hatası ({res.status_code}): {res.text}")
    except Exception as e: 
        print(f"Sistem Hatası: {e}")
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

def merge_and_save(local_data, fetched_pubs, metrics):
    # Mevcut yayınları DOI veya Başlık bazlı bir sözlüğe al
    local_dict = { (p.get('doi') or p.get('title') or "").lower().strip(): p for p in local_data['publications'] if p }
    
    for n in fetched_pubs:
        n_doi = str(n.get('doi') or "").strip().lower()
        n_title = str(n.get('title') or "").strip().lower()
        key = n_doi if n_doi else n_title
        if not key: continue

        if key in local_dict:
            # --- EŞLEŞME VARSA: SADECE DEĞİŞKEN VERİLERİ GÜNCELLE ---
            # Atıf sayısı her zaman güncellenir
            local_dict[key]['citations'] = n.get('citations', local_dict[key].get('citations', '0'))
            
            # Eksik olan linkleri veya dergi adını doldur (varsa dokunma)
            for field in ['scopus_link', 'wos_link', 'journal']:
                if n.get(field) and not local_dict[key].get(field):
                    local_dict[key][field] = n[field]
            
            # İndeks SCI-E ise yükselt
            if n.get('index') == 'sci':
                local_dict[key]['index'] = 'sci'
        else:
            # --- YENİ YAYIN: LİSTEYE EKLE ---
            local_dict[key] = n
    
    # Final JSON Yapısı
    output = {
        "metrics": metrics,
        "publications": sorted(local_dict.values(), key=lambda x: str(x.get('year', '0')), reverse=True)
    }
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    # Verileri oku
    local_data = load_local_data()
    
    # API'lerden taze verileri çek
    metrics = fetch_scopus_metrics()
    s_pubs = fetch_scopus_data()
    o_pubs = fetch_orcid_data()
    
    # Birleştir ve Kaydet
    merge_and_save(local_data, s_pubs + o_pubs, metrics)
    
    print(f"İşlem Başarılı! {len(local_data['publications'])} yayın kontrol edildi, atıf sayıları güncellendi.")
