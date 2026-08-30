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
from API.models.models import Base, ElementoCurricular, PlanEstudios, ResumenCreditos, Titulacion, Universidad


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
        university = Universidad(codigo="001", nombre="Universidad de Prueba", tipo="Pública")
        verified_degree = Titulacion(
            codigo_estudio="2500001",
            titulo="Grado en Ingeniería Informática",
            nivel_academico="Grado",
            universidad_codigo="001",
            centro_adscrito="Escuela de Prueba",
            es_alianza_europea=True,
            web_fuente_directa_url="https://universidad.example/plan",
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
            tipo_estructura="consorcio_europeo_erasmus_mundus",
            ects_exigidos="60",
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
            ResumenCreditos(plan_estudio_id=verified_plan.id, tipo_credito="Obligatorios", cantidad_creditos="60"),
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

    def test_public_api_returns_incomplete_curriculum_with_quality_status(self):
        verified = self.client.get("/api/v1/titulaciones/2500001/plan-estudios")
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()["estado_calidad"], "verificado_boe")

        pending = self.client.get("/api/v1/titulaciones/2500002/plan-estudios")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["estado_calidad"], "pendiente_revision")
        self.assertEqual(pending.json()["motivos_calidad"]["errores"], ["titulo_plan_no_coincide"])

    def test_incomplete_children_are_publicly_listed_with_their_degree(self):
        listed = self.client.get("/api/v1/titulaciones?con_plan=true")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            {item["codigo_estudio"] for item in listed.json()},
            {"2500001", "2500002"},
        )
        pending_listing = next(item for item in listed.json() if item["codigo_estudio"] == "2500002")
        self.assertFalse(pending_listing["tiene_plan_verificado"])
        self.assertTrue(pending_listing["plan_incompleto"])
        self.assertEqual(pending_listing["estado_calidad_plan"], "pendiente_revision")

        pending_subjects = self.client.get("/api/v1/titulaciones/2500002/asignaturas")
        self.assertEqual(pending_subjects.status_code, 200)
        self.assertEqual([item["nombre_elemento"] for item in pending_subjects.json()], ["Dato no verificado"])

    def test_degree_detail_exposes_non_publishable_relationship_with_warning_state(self):
        pending_detail = self.client.get("/api/v1/titulaciones/2500002")
        self.assertEqual(pending_detail.status_code, 200)
        self.assertEqual(pending_detail.json()["plan_estudios"]["estado_calidad"], "pendiente_revision")
        self.assertTrue(pending_detail.json()["plan_incompleto"])

    def test_public_contract_exposes_verified_provenance_and_plan_structure(self):
        listing = self.client.get("/api/v1/titulaciones?con_plan=true")
        self.assertEqual(listing.status_code, 200)
        degree = next(item for item in listing.json() if item["codigo_estudio"] == "2500001")
        self.assertEqual(degree["universidad_nombre"], "Universidad de Prueba")
        self.assertEqual(degree["universidad_tipo"], "Pública")
        self.assertEqual(degree["centro_adscrito"], "Escuela de Prueba")
        self.assertTrue(degree["es_alianza_europea"])
        self.assertTrue(degree["tiene_plan_verificado"])
        self.assertEqual(degree["fuente_verificada_url"], "https://www.boe.es/boe/dias/2024/01/01/pdfs/BOE-A-2024-1.pdf")

        plan = self.client.get("/api/v1/titulaciones/2500001/plan-estudios")
        self.assertEqual(plan.status_code, 200)
        payload = plan.json()
        self.assertEqual(payload["tipo_estructura"], "consorcio_europeo_erasmus_mundus")
        self.assertEqual(payload["ects_exigidos"], "60")
        self.assertEqual(payload["resumen_creditos"], [{"id": payload["resumen_creditos"][0]["id"], "tipo_credito": "Obligatorios", "cantidad_creditos": "60"}])


if __name__ == "__main__":
    unittest.main()
