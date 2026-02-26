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
    print("Scopus taranıyor (Gelişmiş Erişim)...")
    # API Key'i URL'den çıkardık, başlık (header) içine koyacağız
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&view=COMPLETE&sort=-coverDate&count=25"
    
    headers = {
        'X-ELS-APIKey': SCOPUS_API_KEY, # Elsevier'in tercih ettiği yöntem
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        print(f"Scopus Yanıt Kodu: {res.status_code}")
        
        if res.status_code == 200:
            data = res.json()
            entries = data.get('search-results', {}).get('entry', [])
            print(f"Scopus'tan {len(entries)} adet yayın çekildi.")
            
            for e in entries:
                doi = e.get('prism:doi', '')
                cover_date = e.get('prism:coverDate')
                year = cover_date.split('-')[0] if cover_date else "2026"
                
                pubs.append({
                    "title": e.get('dc:title', 'Başlıksız Scopus Yayını'),
                    "author": e.get('dc:creator', 'Erişkin, E.'),
                    "year": year,
                    "index": "scopus",
                    "doi": doi,
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={e.get('eid', '')}"
                })
        elif res.status_code == 401:
            print("HATA: Scopus API Anahtarı yetkisiz (401)! Lütfen anahtarı Elsevier portalından kontrol edin.")
            # Hata detayını görebilmek için:
            print(f"Elsevier Yanıtı: {res.text}")
        else:
            print(f"Scopus Beklenmedik Hata: {res.status_code}")
            
    except Exception as e:
        print(f"Scopus Bağlantı Hatası: {e}")
    return pubs

def fetch_trdizin_data():
    print("TR Dizin taranıyor (Nihai Form)...")
    # Sorguyu en kararlı hale getirdik
    url = "https://search.trdizin.gov.tr/api/defaultSearch/publication/?q=Ekinhan+Eriskin&order=publicationYear-DESC&limit=100"
    
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://search.trdizin.gov.tr/'
    }
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            hits_list = res.json().get('hits', {}).get('hits', [])
            print(f"TR Dizin'den {len(hits_list)} yayın yakalandı.")
            
            for hit in hits_list:
                source = hit.get('_source', {})
                authors_list = source.get('authors', [])
                # Yazar isimlerini birleştiriyoruz
                author_names = ", ".join([a.get('fullName', 'Erişkin, E.') for a in authors_list])
                
                pubs.append({
                    "title": source.get('title', 'Başlıksız Yayın'),
                    "author": author_names if author_names else "Erişkin, E.",
                    "year": str(source.get('publicationYear', '2026')),
                    "index": "trdizin",
                    "doi": source.get('doi', ''),
                    "trdizin_link": f"https://search.trdizin.gov.tr/tr/yayin/detay/{hit.get('_id', '')}"
                })
            print(f"Listeye eklenen TR Dizin yayını: {len(pubs)}")
        else:
            print(f"TR Dizin API Hatası: {res.status_code}")
    except Exception as e:
        print(f"TR Dizin Bağlantı Hatası: {e}")
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
