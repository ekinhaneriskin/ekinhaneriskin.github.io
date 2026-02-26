import json
import requests
import os
from datetime import datetime

# --- AYARLAR ---
SCOPUS_API_KEY = os.environ.get('SCOPUS_API_KEY')
SCOPUS_AUTHOR_ID = '57039193000'
TRDIZIN_AUTHOR_ID = '341496'
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
    # count=200 ekledik: Varsayılan 25 sınırı yerine tek seferde 200 yayını çeker
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=COMPLETE&count=200"
    headers = {'Accept': 'application/json'}
    pubs = []
    if not SCOPUS_API_KEY:
        print("HATA: API Anahtarı bulunamadı!")
        return pubs
        
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            entries = data.get('search-results', {}).get('entry', [])
            current_year = str(datetime.now().year) # Otomatik olarak güncel yılı alır
            
            for entry in entries:
                doi = entry.get('prism:doi', '')
                
                # Tarihi güvenli bir şekilde çek
                cover_date = entry.get('prism:coverDate')
                if cover_date:
                    year = cover_date.split('-')[0]
                else:
                    year = current_year # Tarih yoksa bu seneyi yaz
                    
                pubs.append({
                    "title": entry.get('dc:title', ''),
                    "author": entry.get('dc:creator', 'Erişkin, E.'),
                    "year": year,
                    "index": "scopus",
                    "doi": doi,
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={entry.get('eid', '')}",
                })
    except Exception as e:
        print(f"Scopus hatası: {e}")
    return pubs

def fetch_trdizin_data():
    print("TR Dizin verileri çekiliyor...")
    url = f"https://search.trdizin.gov.tr/api/author/{TRDIZIN_AUTHOR_ID}/publications"
    pubs = []
    try:
        response = requests.get(url, headers={'Accept': 'application/json'})
        if response.status_code == 200:
            entries = response.json().get('data', [])
            current_year = str(datetime.now().year)
            
            for entry in entries:
                doi = entry.get('doi', '')
                
                # TRDizin yılını güvenli al
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
        print(f"TR Dizin hatası: {e}")
    return pubs

def merge_and_save(local_data, fetched_data):
    for new_pub in fetched_data:
        key = new_pub.get('doi', '').strip().lower()
        if not key:
            key = new_pub.get('title', '').strip().lower()
            
        if key in local_data:
            existing_pub = local_data[key]
            if not existing_pub.get('scopus_link') and new_pub.get('scopus_link'):
                existing_pub['scopus_link'] = new_pub['scopus_link']
            if not existing_pub.get('trdizin_link') and new_pub.get('trdizin_link'):
                existing_pub['trdizin_link'] = new_pub['trdizin_link']
        else:
            local_data[key] = new_pub

    final_list = list(local_data.values())
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=4)
    print(f"Güncelleme Tamamlandı! Toplam {len(final_list)} yayın kaydedildi.")

if __name__ == "__main__":
    local_pubs = load_local_data()
    scopus_pubs = fetch_scopus_data()
    trdizin_pubs = fetch_trdizin_data()
    
    all_fetched = scopus_pubs + trdizin_pubs
    merge_and_save(local_pubs, all_fetched)
