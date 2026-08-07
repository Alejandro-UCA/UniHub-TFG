import os
import sys

sys.path.append('d:/Proyecto/Codigo/API')

from database.connection import SessionLocal
from models.models import Titulacion, Universidad

def inject_fake():
    db = SessionLocal()
    
    # Asegurar que UCA existe
    uca = db.query(Universidad).filter(Universidad.codigo == '005').first()
    if not uca:
        uca = Universidad(codigo='005', nombre='Universidad de Cádiz')
        db.add(uca)
        db.flush()

    # Create fake degree
    fake_code = '9999999'
    fake_degree = db.query(Titulacion).filter(Titulacion.codigo_estudio == fake_code).first()
    if not fake_degree:
        fake_degree = Titulacion(
            codigo_estudio=fake_code,
            titulo='Grado Fake de Prueba (DEBE BORRARSE)',
            nivel_academico='Grado',
            estado='Publicado',
            universidad_codigo=uca.codigo
        )
        db.add(fake_degree)
        db.commit()
        print(f"Fake degree '{fake_code}' injected successfully.")
    else:
        print(f"Fake degree '{fake_code}' already exists.")

    db.close()

if __name__ == "__main__":
    inject_fake()
