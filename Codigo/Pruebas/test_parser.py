import os
import sys

sys.path.append('/app')

from Crawler.parsers import parse_boe_pdf

import urllib.request
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

url = "https://www.boe.es/boe/dias/2010/11/11/pdfs/BOE-A-2010-17372.pdf"
pdf_path = "/tmp/test_boe_uca.pdf"

try:
    print("Downloading PDF...")
    urllib.request.urlretrieve(url, pdf_path)
    print("Parsing PDF...")
    data = parse_boe_pdf(pdf_path)
    
    print(f"Total Elementos Extracted: {data.get('total_elementos', 0)}")
    for e in data.get("elementos_curriculares", []):
        print(f" - {e['nombre_elemento']}")

except Exception as e:
    print(f"Error: {e}")
