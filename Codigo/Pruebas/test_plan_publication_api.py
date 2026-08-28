import os
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from API.database.connection import get_db
from API.main import app
from API.models.models import Base, ElementoCurricular, PlanEstudios, Titulacion, Universidad


class TestPlanPublicationApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)

        session = cls.Session()
        university = Universidad(codigo="001", nombre="Universidad de Prueba")
        verified_degree = Titulacion(
            codigo_estudio="2500001",
            titulo="Grado en Ingeniería Informática",
            nivel_academico="Grado",
            universidad_codigo="001",
        )
        pending_degree = Titulacion(
            codigo_estudio="2500002",
            titulo="Grado en Datos Inciertos",
            nivel_academico="Grado",
            universidad_codigo="001",
        )
        session.add_all([university, verified_degree, pending_degree])
        session.flush()
        verified_plan = PlanEstudios(
            codigo_estudio="2500001",
            estado_calidad="verificado_boe",
            origen_fuente="boe",
            fuente_verificada_url="https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf",
        )
        pending_plan = PlanEstudios(
            codigo_estudio="2500002",
            estado_calidad="pendiente_revision",
            motivos_calidad={"errores": ["titulo_plan_no_coincide"]},
        )
        session.add_all([verified_plan, pending_plan])
        session.flush()
        session.add_all([
            ElementoCurricular(plan_estudio_id=verified_plan.id, nombre_elemento="Programación", creditos_ects="6"),
            ElementoCurricular(plan_estudio_id=pending_plan.id, nombre_elemento="Dato no verificado", creditos_ects="6"),
        ])
        session.commit()
        session.close()

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def test_public_api_only_returns_verified_curriculum(self):
        verified = self.client.get("/api/v1/titulaciones/2500001/plan-estudios")
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()["estado_calidad"], "verificado_boe")

        pending = self.client.get("/api/v1/titulaciones/2500002/plan-estudios")
        self.assertEqual(pending.status_code, 404)
        self.assertIn("verificado", pending.json()["detail"])

    def test_unverified_children_are_not_publicly_listed(self):
        listed = self.client.get("/api/v1/titulaciones?con_plan=true")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["codigo_estudio"] for item in listed.json()], ["2500001"])

        pending_subjects = self.client.get("/api/v1/titulaciones/2500002/asignaturas")
        self.assertEqual(pending_subjects.status_code, 200)
        self.assertEqual(pending_subjects.json(), [])

    def test_degree_detail_hides_non_publishable_relationship(self):
        pending_detail = self.client.get("/api/v1/titulaciones/2500002")
        self.assertEqual(pending_detail.status_code, 200)
        self.assertIsNone(pending_detail.json()["plan_estudios"])


if __name__ == "__main__":
    unittest.main()
