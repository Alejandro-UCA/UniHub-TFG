import sys
import os

# Add Crawler dir to path
sys.path.append("d:/Proyecto/Codigo/Crawler")

from univ_web_crawler import UniversityWebCrawler

crawler = UniversityWebCrawler()

test_univ = {
    "codigo": "001",
    "nombre": "Universidad de Cádiz",
    "tipo": "Universidad Pública",
    "web": "https://www.uca-url-inventada-falsa.es"  # Intentionally broken
}

titulaciones = {
    "001": {
        "titulaciones_vigentes": [
            {
                "codigo_estudio": "TEST001",
                "titulo": "Grado en Pruebas Falsas"
            }
        ]
    }
}

print("Iniciando prueba de rescate...")
stats = crawler.process_university_web(test_univ, titulaciones)
print("Stats finales:")
print(stats)
