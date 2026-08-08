import pdfplumber

pdf_filepath = "test_boe_uca.pdf"
try:
    with pdfplumber.open(pdf_filepath) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()
        if tables:
            print("First table headers:")
            print(tables[0][0])
            print("First row:")
            print(tables[0][1])
            print("Second row:")
            print(tables[0][2])
            print("Third row:")
            print(tables[0][3])
        else:
            print("No tables found on first page.")
except Exception as e:
    print(f"Error: {e}")
