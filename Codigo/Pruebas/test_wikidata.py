import requests
import urllib.parse
import sys

def get_university_url(univ_name):
    headers = {
        "User-Agent": "UniHubCrawler/1.0 (https://github.com/Alejandro-UCA/UniHub-TFG; alejandro@example.com) requests/2.31.0"
    }
    
    # Step 1: Search Wikipedia for the university to get the title/pageid
    search_url = "https://es.wikipedia.org/w/api.php"
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": univ_name,
        "format": "json",
        "utf8": 1,
        "srlimit": 1
    }
    
    response = requests.get(search_url, params=search_params, headers=headers)
    try:
        data = response.json()
    except Exception as e:
        print(f"Error decoding JSON. Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        return None
    
    if not data.get("query", {}).get("search"):
        print(f"No Wikipedia page found for {univ_name}")
        return None
        
    title = data["query"]["search"][0]["title"]
    print(f"Found Wikipedia page: {title}")
    
    # Step 2: Get Wikidata Item ID for the Wikipedia page
    prop_params = {
        "action": "query",
        "prop": "pageprops",
        "titles": title,
        "format": "json"
    }
    
    prop_response = requests.get(search_url, params=prop_params, headers=headers)
    prop_data = prop_response.json()
    
    pages = prop_data.get("query", {}).get("pages", {})
    page = list(pages.values())[0]
    wikibase_item = page.get("pageprops", {}).get("wikibase_item")
    
    if not wikibase_item:
        print(f"No Wikidata item found for {title}")
        return None
        
    print(f"Found Wikidata ID: {wikibase_item}")
    
    # Step 3: Get Official Website (Property P856) from Wikidata
    wikidata_url = f"https://www.wikidata.org/w/api.php"
    wd_params = {
        "action": "wbgetentities",
        "ids": wikibase_item,
        "props": "claims",
        "format": "json"
    }
    
    wd_response = requests.get(wikidata_url, params=wd_params, headers=headers)
    wd_data = wd_response.json()
    
    claims = wd_data.get("entities", {}).get(wikibase_item, {}).get("claims", {})
    website_claims = claims.get("P856", [])
    
    if website_claims:
        website = website_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        return website
        
    print("No official website (P856) found in Wikidata.")
    return None

if __name__ == "__main__":
    test_univs = ["Universidad de Cádiz", "Universidad Católica San Antonio de Murcia", "Universitat Pompeu Fabra"]
    for u in test_univs:
        url = get_university_url(u)
        print(f"Result for {u}: {url}\n")
