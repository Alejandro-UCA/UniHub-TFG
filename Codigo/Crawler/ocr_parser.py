import os
import re

OCR_AVAILABLE = False
try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

class OCRPDFParser:
    """
    Local OCR parser for historical scanned BOE PDFs (2008-2012)
    that lack vector text layers. Reconstructs text layer via tesseract OCR.
    """
    def __init__(self, dpi=200):
        self.dpi = dpi

    def extract_text_via_ocr(self, pdf_filepath: str) -> str:
        """
        Converts PDF pages to images and runs local Tesseract OCR.
        Safe fallback returning empty string if OCR engine or Tesseract binary is unavailable.
        """
        if not OCR_AVAILABLE or not os.path.exists(pdf_filepath):
            return ""

        try:
            images = convert_from_path(pdf_filepath, dpi=self.dpi, first_page=1, last_page=5)
            ocr_text_parts = []
            for img in images:
                txt = pytesseract.image_to_string(img, lang="spa")
                if txt:
                    ocr_text_parts.append(txt)
            return "\n".join(ocr_text_parts)
        except Exception as err:
            print(f"   [OCR Fallback] Local OCR notice for '{pdf_filepath}': {err}")
            return ""
