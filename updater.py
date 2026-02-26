import json
import requests
import os
from datetime import datetime

# --- AYARLAR ---
SCOPUS_API_KEY = 'a5210b26f0964c067ea0ed118b6df34c' # Anahtarı buraya tırnak içinde yapıştırdık
SCOPUS_AUTHOR_ID = '57039193000'
TRDIZIN_AUTHOR_ID = '341496'
ORCID_ID = '0000-0002-0087-0933'
JSON_FILE_PATH = 'publications.json'

def load_local_data():
    if not os.path.exists(JSON_FILE_PATH):
        return {}
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}
    local_pubs = {}
    for pub in data:
        key = pub.get('doi', '').strip().lower()
        if not key:
            key = pub.get('title', '').strip().lower()
        local_pubs[key] = pub
    return local_pubs

def fetch_scopus_data():
    print("Scopus verileri çekiliyor...")
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=COMPLETE&sort=-coverDate"
    headers = {'Accept': 'application/json'}
    pubs = []
    
    if not SCOPUS_API_KEY:
        print("HATA: Scopus API Anahtarı bulunamadı!")
        return pubs
        
    try:
        response = requests.get(url, headers=headers)
        print(f"Scopus Yanıt Kodu: {response.status_code}")
        
        if response.status_code == 200:
            entries = response.json().get('search-results', {}).get('entry', [])
            current_year = str(datetime.now().year)
            for entry in entries:
                doi = entry.get('prism:doi', '')
                cover_date = entry.get('prism:coverDate')
                year = cover_date.split('-')[0] if cover_date else current_year
                    
                pubs.append({
                    "title": entry.get('dc:title', ''),
                    "author": entry.get('dc:creator', 'Erişkin, E.'),
                    "year": year,
                    "index": "scopus",
                    "doi": doi,
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={entry.get('eid', '')}",
                })
    except Exception as e:
        print(f"Scopus bağlantı hatası: {e}")
    return pubs

def fetch_trdizin_data():
    print("TR Dizin verileri çekiliyor...")
    url = f"https://search.trdizin.gov.tr/api/author/{TRDIZIN_AUTHOR_ID}/publications"
    pubs = []
    try:
        headers = {'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        print(f"TR Dizin Yanıt Kodu: {response.status_code}")
        
        if response.status_code == 200:
            entries = response.json().get('data', [])
            current_year = str(datetime.now().year)
            for entry in entries:
                doi = entry.get('doi', '')
                year_raw = entry.get('year')
                year = str(year_raw) if year_raw else current_year
                pubs.append({
                    "title": entry.get('title', ''),
                    "author": entry.get('authors', 'Erişkin, E.'),
                    "year": year,
                    "index": "trdizin",
                    "doi": doi,
                    "trdizin_link": f"https://search.trdizin.gov.tr/en/yayin/detay/{entry.get('id', '')}"
                })
    except Exception as e:
        print(f"TR Dizin bağlantı hatası: {e}")
    return pubs

def fetch_orcid_data():
    """ORCID üzerinden ücretsiz veri ve WoS kimliklerini (WOSUID) çeker"""
    print("ORCID (WoS) verileri çekiliyor...")
    url = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
    headers = {'Accept': 'application/json'}
    pubs = []
    try:
        response = requests.get(url, headers=headers)
        print(f"ORCID Yanıt Kodu: {response.status_code}")
        
        if response.status_code == 200:
            groups = response.json().get('group', [])
            current_year = str(datetime.now().year)
            
            for group in groups:
                work_summaries = group.get('work-summary', [])
                if not work_summaries:
                    continue
                work = work_summaries[0] # İlk özeti al
                
                title = work.get('title', {}).get('title', {}).get('value', '') if work.get('title') else ''
                pub_date = work.get('publication-date', {})
                year = pub_date.get('year', {}).get('value', current_year) if pub_date else current_year
                
                doi = ''
                wosuid = ''
                ext_ids = work.get('external-ids', {}).get('external-id', [])
                for ext_id in ext_ids:
                    id_type = ext_id.get('external-id-type', '').lower()
                    id_val = ext_id.get('external-id-value', '')
                    if id_type == 'doi':
                        doi = id_val
                    elif id_type == 'wosuid':
                        wosuid = id_val # WoS Kimliğini yakaladık!
                
                pub_entry = {
                    "title": title,
                    "author": "Erişkin, E.",
                    "year": year,
                    "index": "sci" if wosuid else "other",
                    "doi": doi
                }
                
                # Eğer makalenin WoS kimliği varsa otomatik link oluştur
                if wosuid:
                    pub_entry["wos_link"] = f"https://www.webofscience.com/wos/woscc/full-record/{wosuid}"
                    
                pubs.append(pub_entry)
    except Exception as e:
        print(f"ORCID bağlantı hatası: {e}")
    return pubs

def merge_and_save(local_data, fetched_data):
    for new_pub in fetched_data:
        key = new_pub.get('doi', '').strip().lower()
        if not key:
            key = new_pub.get('title', '').strip().lower()
            
        if key in local_data:
            existing_pub = local_data[key]
            # Sadece boş olan linkleri doldur (WoS, Scopus, TRDizin)
            if not existing_pub.get('scopus_link') and new_pub.get('scopus_link'):
                existing_pub['scopus_link'] = new_pub['scopus_link']
            if not existing_pub.get('trdizin_link') and new_pub.get('trdizin_link'):
                existing_pub['trdizin_link'] = new_pub['trdizin_link']
            if not existing_pub.get('wos_link') and new_pub.get('wos_link'):
                existing_pub['wos_link'] = new_pub['wos_link']
            
            # Eğer local verideki "index" other veya scopus ise ve yeni veride sci (WoS) varsa, indexi sci yap
            if existing_pub.get('index') != 'sci' and new_pub.get('index') == 'sci':
                existing_pub['index'] = 'sci'
        else:
            local_data[key] = new_pub

    final_list = list(local_data.values())
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)
    print(f"Güncelleme Tamamlandı! Toplam {len(final_list)} yayın kaydedildi.")

if __name__ == "__main__":
    local_pubs = load_local_data()
    
    # 3 Motoru birden çalıştır
    scopus_pubs = fetch_scopus_data()
    trdizin_pubs = fetch_trdizin_data()
    orcid_pubs = fetch_orcid_data()
    
    # Tüm verileri havuzda topla
    all_fetched = scopus_pubs + trdizin_pubs + orcid_pubs
    
    if all_fetched:
        merge_and_save(local_pubs, all_fetched)
    else:
        print("HİÇ YENİ VERİ ÇEKİLEMEDİ! Dosyaya dokunulmuyor.")
