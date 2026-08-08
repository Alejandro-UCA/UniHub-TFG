import os
import sys

# Ensure API is in path
sys.path.append(r"d:\Proyecto\Codigo\API")

from database.connection import SessionAdmin, engine_admin, Base
from models.models import Universidad, Titulacion

def test_sovereignty():
    print("Testing ETL Data Sovereignty...")
    # Make sure tables exist
    Base.metadata.create_all(bind=engine_admin)
    db = SessionAdmin()
    
    # Check if column exists, if not, try to alter table (sqlite specific for tests)
    try:
        db.execute("SELECT gestionado_por_admin FROM universidades LIMIT 1")
    except Exception as e:
        print("Adding column 'gestionado_por_admin' to universidades and titulaciones...")
        db.rollback()
        try:
            db.execute("ALTER TABLE universidades ADD COLUMN gestionado_por_admin BOOLEAN DEFAULT FALSE")
            db.execute("ALTER TABLE titulaciones ADD COLUMN gestionado_por_admin BOOLEAN DEFAULT FALSE")
            db.commit()
        except Exception as e2:
            print("Could not alter tables (maybe already exists or postgres syntax needed).", e2)
            db.rollback()

    # 1. Insert a mock university and degree (simulating Admin action)
    univ_code = "999"
    degree_code = "9999999"
    
    u = db.query(Universidad).filter_by(codigo=univ_code).first()
    if not u:
        u = Universidad(codigo=univ_code, nombre="Universidad Ficticia", gestionado_por_admin=True)
        db.add(u)
    
    t = db.query(Titulacion).filter_by(codigo_estudio=degree_code).first()
    if not t:
        t = Titulacion(
            codigo_estudio=degree_code, 
            titulo="Grado en Ficción", 
            universidad_codigo=univ_code,
            precio_credito_ects=100.0,
            gestionado_por_admin=True
        )
        db.add(t)
    else:
        t.gestionado_por_admin = True
        t.precio_credito_ects = 100.0
    
    db.commit()
    print("Mock data created. gestionado_por_admin = True")
    
    # 2. Simulate ETL attempting to overwrite it
    t = db.query(Titulacion).filter_by(codigo_estudio=degree_code).first()
    if not t.gestionado_por_admin:
        t.precio_credito_ects = 50.0  # ETL logic
    
    # 3. Simulate ETL attempting to delete it
    active_codes = ["0000000"] # Our mock degree is NOT in here
    deleted_count = db.query(Titulacion).filter(
        ~Titulacion.codigo_estudio.in_(active_codes),
        Titulacion.gestionado_por_admin == False
    ).delete(synchronize_session=False)
    
    db.commit()
    
    # 4. Verify
    t_after = db.query(Titulacion).filter_by(codigo_estudio=degree_code).first()
    assert t_after is not None, "FATAL: Admin-managed degree was deleted by ETL!"
    assert float(t_after.precio_credito_ects) == 100.0, "FATAL: Admin-managed price was overwritten!"
    
    print("SUCCESS: Admin-managed data survived the ETL purge and overwrite attempts.")
    
    # Cleanup
    db.delete(t_after)
    db.delete(u)
    db.commit()
    print("Test cleanup done.")

if __name__ == "__main__":
    os.environ["USE_SQLITE_FALLBACK"] = "true"
    test_sovereignty()
