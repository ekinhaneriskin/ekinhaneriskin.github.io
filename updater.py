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
    if not os.path.exists(JSON_FILE_PATH): return {"metrics": {}, "publications": []}
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # Eğer eski yapıdaysa (sadece liste), yeni yapıya dönüştür
            if isinstance(data, list):
                return {"metrics": {}, "publications": data}
            return data
        except: return {"metrics": {}, "publications": []}

def fetch_scopus_metrics():
    print("Scopus metrikleri çekiliyor...")
    url = f"https://api.elsevier.com/content/author/author_id/{SCOPUS_AUTHOR_ID}?apiKey={SCOPUS_API_KEY}"
    headers = {'Accept': 'application/json'}
    metrics = {"h_index": "0", "citation_count": "0", "document_count": "0"}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            coredata = data.get('author-retrieval-response', [{}])[0].get('coredata', {})
            metrics["h_index"] = coredata.get('h-index', '0')
            metrics["citation_count"] = coredata.get('citation-count', '0')
            metrics["document_count"] = coredata.get('document-count', '0')
            print(f"Başarıyla çekildi -> h-index: {metrics['h_index']}")
    except: print("Metrikler çekilemedi.")
    return metrics

def fetch_scopus_data():
    if not SCOPUS_API_KEY: return []
    print("Scopus yayınları taranıyor...")
    url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({SCOPUS_AUTHOR_ID})&apiKey={SCOPUS_API_KEY}&view=STANDARD&count=100"
    headers = {'Accept': 'application/xml', 'User-Agent': 'Mozilla/5.0'}
    pubs = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'dc': 'http://purl.org/dc/elements/1.1/', 'prism': 'http://prismstandard.org/namespaces/basic/2.0/'}
            for entry in root.findall('atom:entry', ns):
                title_node = entry.find('dc:title', ns)
                cit_node = entry.find('atom:citedby-count', ns)
                jrnl_node = entry.find('prism:publicationName', ns)
                author_node = entry.find('dc:creator', ns)
                doi_node = entry.find('prism:doi', ns)
                date_node = entry.find('prism:coverDate', ns)
                eid_node = entry.find('atom:eid', ns)

                pubs.append({
                    "title": title_node.text if title_node is not None else "Untitled",
                    "author": author_node.text if author_node is not None else "Eriskin, E.",
                    "year": date_node.text.split('-')[0] if date_node is not None else "2026",
                    "journal": jrnl_node.text if jrnl_node is not None else "",
                    "index": "scopus",
                    "doi": doi_node.text if doi_node is not None else "",
                    "citations": cit_node.text if cit_node is not None else "0",
                    "scopus_link": f"https://www.scopus.com/record/display.uri?eid={eid_node.text}" if eid_node is not None else ""
                })
            print(f"Scopus'tan {len(pubs)} yayın çekildi.")
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

def merge_and_save(local_data, fetched_pubs, metrics):
    # Mevcut yayınları bir sözlüğe al (DOI veya Başlık bazlı)
    local_dict = { (p.get('doi') or p.get('title') or "").lower().strip(): p for p in local_data['publications'] if p }
    
    for n in fetched_pubs:
        n_doi = str(n.get('doi') or "").strip().lower()
        n_title = str(n.get('title') or "").strip().lower()
        key = n_doi if n_doi else n_title
        if not key: continue

        if key in local_dict:
            for field in ['scopus_link', 'wos_link', 'citations', 'journal', 'author']:
                if n.get(field): local_dict[key][field] = n[field]
            if n.get('index') == 'sci': local_dict[key]['index'] = 'sci'
        else:
            local_dict[key] = n
    
    # Yeni JSON yapısı
    output = {
        "metrics": metrics,
        "publications": sorted(local_dict.values(), key=lambda x: str(x.get('year', '0')), reverse=True)
    }
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    local_data = load_local_data()
    metrics = fetch_scopus_metrics()
    all_pubs = fetch_scopus_data() + fetch_orcid_data()
    
    if all_pubs:
        merge_and_save(local_data, all_pubs, metrics)
        print(f"İşlem Başarılı! {len(local_pubs['publications']) if 'publications' in locals() else 'Tüm'} yayınlar ve metrikler güncellendi.")
