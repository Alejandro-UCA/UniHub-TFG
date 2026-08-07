import parsers
import urllib.request
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

url = "http://www.boe.es/boe/dias/2014/02/25/pdfs/BOE-A-2014-2046.pdf"
pdf_path = "test_boe_uca.pdf"

try:
    print("Downloading 2014 PDF...")
    urllib.request.urlretrieve(url, pdf_path)
    print("Parsing 2014 PDF...")
    data = parsers.parse_boe_pdf(pdf_path)
    
    print(f"Total Elementos Extracted: {data.get('total_elementos', 0)}")
    for e in data.get("elementos_curriculares", []):
        print(f" - {e['nombre_elemento']}")

except Exception as e:
    print(f"Error: {e}")
