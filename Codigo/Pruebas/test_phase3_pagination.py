import requests
import json
import urllib.parse

API_BASE = "http://localhost:8000/api/v1"

def test_pagination():
    print("Prueba 1: Obtener Titulaciones con límite 5 y cabecera X-Total-Count")
    res = requests.get(f"{API_BASE}/titulaciones?limit=5")
    if res.status_code == 200:
        data = res.json()
        total = res.headers.get("X-Total-Count")
        print(f" -> OK: Recibidas {len(data)} titulaciones. Total en BD: {total}")
        assert len(data) == 5, "Debería haber devuelto 5"
        assert total is not None, "Falta la cabecera X-Total-Count"
    else:
        print(f" -> ERROR: {res.status_code} {res.text}")
        
    print("\nPrueba 2: Filtrar titulaciones por CCAA (Andalucía)")
    res = requests.get(f"{API_BASE}/titulaciones?ccaa={urllib.parse.quote('Andalucía')}&limit=1")
    if res.status_code == 200:
        data = res.json()
        total = res.headers.get("X-Total-Count")
        print(f" -> OK: Filtradas. Total de titulaciones en Andalucía: {total}")
    else:
        print(f" -> ERROR: {res.status_code} {res.text}")
        
    print("\nPrueba 3: Obtener Universidades con límite 5 y cabecera X-Total-Count")
    res = requests.get(f"{API_BASE}/universidades?limit=5")
    if res.status_code == 200:
        data = res.json()
        total = res.headers.get("X-Total-Count")
        print(f" -> OK: Recibidas {len(data)} universidades. Total en BD: {total}")
        assert len(data) == 5, "Debería haber devuelto 5"
        assert total is not None, "Falta la cabecera X-Total-Count"
    else:
        print(f" -> ERROR: {res.status_code} {res.text}")

if __name__ == "__main__":
    test_pagination()
