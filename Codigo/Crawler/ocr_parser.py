import os
import io
import re
import logging
import shutil

logger = logging.getLogger("ocr_parser")

OCR_AVAILABLE = False
HAS_PDF2IMAGE = False
HAS_PYPDFIUM2 = False
HAS_PYTESSERACT = False

try:
    import pdf2image
    HAS_PDF2IMAGE = True
except ImportError:
    pass

try:
    import pypdfium2
    HAS_PYPDFIUM2 = True
except ImportError:
    pass

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    pass

OCR_AVAILABLE = (HAS_PDF2IMAGE or HAS_PYPDFIUM2) and HAS_PYTESSERACT and bool(shutil.which("tesseract"))


class OCRPDFParser:
    """
    Extractor OCR asistido y liviano para resoluciones escaneadas antiguas del BOE o boletines
    autonómicos que carecen de capa de texto nativa vectorial.
    Soporta flujos directos en memoria RAM (bytes / BytesIO) y rutas en disco, con degradación elegante.
    """
    def __init__(self, dpi: int = 200, max_pages: int = 5, lang: str = "spa"):
        self.dpi = dpi
        self.max_pages = max_pages
        self.lang = lang

    def extract_text_via_ocr(self, pdf_input) -> str:
        """
        Convierte las primeras páginas del PDF a imágenes y aplica Tesseract OCR en memoria.
        Si las librerías o los binarios de OCR del sistema no están instalados,
        retorna cadena vacía sin interrumpir ni bloquear el rastreador.
        """
        if not OCR_AVAILABLE or pdf_input is None:
            return ""

        try:
            images = []
            if isinstance(pdf_input, (bytes, bytearray)):
                if HAS_PDF2IMAGE:
                    images = pdf2image.convert_from_bytes(pdf_input, dpi=self.dpi, first_page=1, last_page=self.max_pages)
                elif HAS_PYPDFIUM2:
                    pdf_doc = pypdfium2.PdfDocument(io.BytesIO(pdf_input))
                    try:
                        for i in range(min(len(pdf_doc), self.max_pages)):
                            page = pdf_doc.get_page(i)
                            pil_img = page.render(scale=self.dpi / 72).to_pil()
                            images.append(pil_img)
                    finally:
                        pdf_doc.close()
            elif isinstance(pdf_input, io.BytesIO):
                raw_bytes = pdf_input.getvalue()
                if HAS_PDF2IMAGE:
                    images = pdf2image.convert_from_bytes(raw_bytes, dpi=self.dpi, first_page=1, last_page=self.max_pages)
                elif HAS_PYPDFIUM2:
                    pdf_doc = pypdfium2.PdfDocument(pdf_input)
                    try:
                        for i in range(min(len(pdf_doc), self.max_pages)):
                            page = pdf_doc.get_page(i)
                            pil_img = page.render(scale=self.dpi / 72).to_pil()
                            images.append(pil_img)
                    finally:
                        pdf_doc.close()
            elif isinstance(pdf_input, str) and os.path.exists(pdf_input):
                if HAS_PDF2IMAGE:
                    images = pdf2image.convert_from_path(pdf_input, dpi=self.dpi, first_page=1, last_page=self.max_pages)
                elif HAS_PYPDFIUM2:
                    pdf_doc = pypdfium2.PdfDocument(pdf_input)
                    try:
                        for i in range(min(len(pdf_doc), self.max_pages)):
                            page = pdf_doc.get_page(i)
                            pil_img = page.render(scale=self.dpi / 72).to_pil()
                            images.append(pil_img)
                    finally:
                        pdf_doc.close()

            if not images:
                return ""

            ocr_parts = []
            for img in images:
                txt = pytesseract.image_to_string(img, lang=self.lang)
                if txt and len(txt.strip()) > 10:
                    ocr_parts.append(txt.strip())

            return "\n".join(ocr_parts)

        except Exception as err:
            logger.debug(f"[OCR Fallback Info] Intento de OCR no disponible o sin binario Tesseract: {err}")
            return ""
