import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .models import AdjuntoAvance, AsignacionCompromiso, Compromiso, RegistroAvance
from .tests import CLAVE, crear_usuario


# ============================================================
# PRUEBAS: API DE LA TRANSACCIÓN T2 (REGISTRO DE AVANCE)
# ============================================================
# Los ID CP-AVA-### se registran en la matriz de resultado esperado vs.
# obtenido del informe de Back End.

MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="sgr_media_api_")


def crear_delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre,
        direccion="Dirección de prueba",
        encargado="Encargado",
        email=f"{nombre.split()[-1].lower()}.t2@laserena.cl",
        telefono="51 2 000 000",
        celular="+56 9 1111 1111",
    )


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class PruebasAPIAvances(APITestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = crear_delegacion("Delegación Centro")
        cls.rural = crear_delegacion("Delegación Rural")
        cls.servicio = Servicio.objects.create(delegacion=cls.centro, nombre="Aseo")
        cls.servicio_rural = Servicio.objects.create(delegacion=cls.rural, nombre="Riego")

        cls.admin = crear_usuario("13.333.333-3", "admin.t2@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario(
            "14.444.444-4", "sup.t2@laserena.cl", SUPERVISOR, delegacion=cls.centro
        )
        cls.administrativo = crear_usuario(
            "15.555.555-5", "adm.t2@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro
        )
        cls.administrativo_rural = crear_usuario(
            "16.666.666-6", "adm.rural.t2@laserena.cl", ADMINISTRATIVO, delegacion=cls.rural
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        Path(MEDIA_TEMPORAL).mkdir(parents=True, exist_ok=True)
        self.compromiso = self.crear_compromiso(self.centro, self.servicio)
        self.compromiso_rural = self.crear_compromiso(self.rural, self.servicio_rural)

    def crear_compromiso(self, delegacion, servicio):
        compromiso = Compromiso.objects.create(
            tarea=f"Mejorar luminarias {delegacion.nombre}",
            cumplimiento=0,
            delegacion=delegacion,
            servicio=servicio,
        )
        AsignacionCompromiso.objects.create(
            compromiso=compromiso,
            delegacion=delegacion,
            servicio=servicio,
            usuario_asignador=self.admin,
        )
        return compromiso

    def como(self, usuario):
        self.client.force_authenticate(user=usuario)

    def registrar(self, porcentaje=60, compromiso=None, **extra):
        datos = {
            "compromiso": (compromiso or self.compromiso).pk,
            "porcentaje_avance": porcentaje,
            "evidencia": "Acta N.° 12",
            "observacion": "",
        }
        datos.update(extra)
        return self.client.post("/api/avances/", datos, format="json")

    # --- REGISTRAR (POST) ---
    def test_cp_ava_001_sin_token_responde_401(self):
        self.assertEqual(self.client.get("/api/avances/").status_code, 401)

    def test_cp_ava_002_registrar_actualiza_cumplimiento_y_semaforo(self):
        self.como(self.administrativo)
        respuesta = self.registrar(95)

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["cumplimiento_compromiso"], 95)
        self.assertEqual(respuesta.data["semaforo_compromiso"], "verde")

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 95)

    def test_cp_ava_003_con_token_jwt(self):
        token = self.client.post(
            "/api/token/",
            {"username": "15.555.555-5", "password": CLAVE},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.assertEqual(self.registrar(60).status_code, 201)

    def test_cp_ava_004_avance_que_retrocede_responde_409(self):
        self.como(self.administrativo)
        self.registrar(60)

        respuesta = self.registrar(59)
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("no puede ser menor", respuesta.data["detail"])

    def test_cp_ava_005_mismo_porcentaje_se_acepta(self):
        # Borde: igual al vigente no retrocede.
        self.como(self.administrativo)
        self.registrar(60)
        self.assertEqual(self.registrar(60).status_code, 201)

    def test_cp_ava_006_sin_evidencia_responde_400(self):
        self.como(self.administrativo)
        respuesta = self.registrar(60, evidencia="   ")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("evidencia", respuesta.data)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_cp_ava_007_porcentaje_fuera_de_rango_responde_400(self):
        self.como(self.administrativo)
        self.assertEqual(self.registrar(101).status_code, 400)
        self.assertEqual(self.registrar(-1).status_code, 400)

    def test_cp_ava_008_sin_asignacion_vigente_responde_409(self):
        self.compromiso.asignaciones.update(activo=False)
        self.como(self.administrativo)

        respuesta = self.registrar(60)
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("asignación vigente", respuesta.data["detail"])

    def test_cp_ava_009_compromiso_de_otra_delegacion_responde_403(self):
        self.como(self.administrativo)
        respuesta = self.registrar(60, compromiso=self.compromiso_rural)
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_ava_010_compromiso_inexistente_responde_404(self):
        self.como(self.administrativo)
        respuesta = self.client.post("/api/avances/", {
            "compromiso": 99999,
            "porcentaje_avance": 10,
            "evidencia": "Acta",
        }, format="json")
        self.assertEqual(respuesta.status_code, 404)

    def test_cp_ava_011_supervisor_no_registra_avances_403(self):
        self.como(self.supervisor)
        self.assertEqual(self.registrar(60).status_code, 403)

    def test_cp_ava_012_multipart_con_archivo(self):
        self.como(self.administrativo)
        respuesta = self.client.post("/api/avances/", {
            "compromiso": self.compromiso.pk,
            "porcentaje_avance": 70,
            "evidencia": "Fotografía de la obra",
            "adjuntos": [
                SimpleUploadedFile("foto.jpg", b"jpg", content_type="image/jpeg"),
                SimpleUploadedFile("acta.pdf", b"%PDF", content_type="application/pdf"),
            ],
        }, format="multipart")

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(len(respuesta.data["adjuntos"]), 2)
        self.assertIn("/descargar/", respuesta.data["adjuntos"][0]["descarga"])

    def test_cp_ava_013_archivo_ejecutable_se_rechaza_400(self):
        self.como(self.administrativo)
        respuesta = self.client.post("/api/avances/", {
            "compromiso": self.compromiso.pk,
            "porcentaje_avance": 70,
            "evidencia": "Acta",
            "adjuntos": [SimpleUploadedFile("virus.exe", b"MZ")],
        }, format="multipart")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("adjuntos", respuesta.data)
        self.assertEqual(AdjuntoAvance.objects.count(), 0)

    def test_cp_ava_014_falla_a_mitad_revierte_todo(self):
        self.como(self.administrativo)

        with mock.patch.object(
            Compromiso, "save", side_effect=RuntimeError("falla simulada")
        ):
            with self.assertRaises(RuntimeError):
                self.registrar(80)

        self.assertEqual(RegistroAvance.objects.count(), 0)
        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 0)

    # --- CONSULTAR (GET) ---
    def test_cp_ava_015_historial_solo_de_su_ambito(self):
        self.como(self.admin)
        self.registrar(30)
        self.registrar(40, compromiso=self.compromiso_rural)

        self.como(self.administrativo)
        respuesta = self.client.get("/api/avances/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            {a["compromiso"] for a in respuesta.data}, {self.compromiso.pk}
        )

    def test_cp_ava_016_avance_ajeno_responde_403(self):
        self.como(self.admin)
        pk = self.registrar(40, compromiso=self.compromiso_rural).data["id"]

        self.como(self.administrativo)
        self.assertEqual(self.client.get(f"/api/avances/{pk}/").status_code, 403)

    def test_cp_ava_017_nombre_del_funcionario_solo_para_administrador(self):
        self.como(self.administrativo)
        pk = self.registrar(40).data["id"]

        datos_usuario = self.client.get(f"/api/avances/{pk}/").data
        self.assertNotIn("registrado_por", datos_usuario)

        self.como(self.admin)
        datos_admin = self.client.get(f"/api/avances/{pk}/").data
        self.assertIn("registrado_por", datos_admin)

    def test_cp_ava_018_filtro_compromiso_invalido_responde_400(self):
        self.como(self.administrativo)
        respuesta = self.client.get("/api/avances/?compromiso=abc")
        self.assertEqual(respuesta.status_code, 400)

    # --- MODIFICAR (PUT) ---
    def test_cp_ava_019_supervisor_corrige_evidencia(self):
        self.como(self.administrativo)
        pk = self.registrar(40).data["id"]

        self.como(self.supervisor)
        respuesta = self.client.put(f"/api/avances/{pk}/", {
            "evidencia": "Acta N.° 12 corregida",
            "observacion": "Se corrigió el número del acta.",
        }, format="json")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["evidencia"], "Acta N.° 12 corregida")
        # El porcentaje no cambia con PUT.
        self.assertEqual(respuesta.data["porcentaje_avance"], 40)

    def test_cp_ava_020_avance_antiguo_no_se_modifica_409(self):
        self.como(self.administrativo)
        antiguo = self.registrar(40).data["id"]
        self.registrar(50)

        self.como(self.supervisor)
        respuesta = self.client.put(
            f"/api/avances/{antiguo}/", {"evidencia": "Otra"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 409)

    def test_cp_ava_021_administrativo_no_corrige_403(self):
        self.como(self.administrativo)
        pk = self.registrar(40).data["id"]

        respuesta = self.client.put(
            f"/api/avances/{pk}/", {"evidencia": "Otra"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 403)

    # --- ANULAR (DELETE) ---
    def test_cp_ava_022_anular_vuelve_al_avance_anterior(self):
        self.como(self.administrativo)
        self.registrar(40)
        pk = self.registrar(90).data["id"]

        self.como(self.supervisor)
        respuesta = self.client.delete(
            f"/api/avances/{pk}/", {"motivo": "Se informó 90 en vez de 50."}, format="json"
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["anulado"])
        self.assertEqual(respuesta.data["cumplimiento_compromiso"], 40)
        self.assertEqual(respuesta.data["semaforo_compromiso"], "rojo")
        # Baja lógica: el registro sigue en el historial.
        self.assertTrue(RegistroAvance.objects.filter(pk=pk).exists())

    def test_cp_ava_023_anular_el_unico_avance_deja_cero(self):
        self.como(self.administrativo)
        pk = self.registrar(70).data["id"]

        self.como(self.supervisor)
        respuesta = self.client.delete(f"/api/avances/{pk}/?motivo=Error de digitación")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["cumplimiento_compromiso"], 0)

    def test_cp_ava_024_anular_sin_motivo_responde_400(self):
        self.como(self.administrativo)
        pk = self.registrar(70).data["id"]

        self.como(self.supervisor)
        respuesta = self.client.delete(f"/api/avances/{pk}/")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("motivo", respuesta.data)

    def test_cp_ava_025_tras_anular_se_puede_registrar_menor(self):
        # La anulación es el camino para corregir un porcentaje mal informado.
        self.como(self.administrativo)
        pk = self.registrar(90).data["id"]

        self.como(self.supervisor)
        self.client.delete(f"/api/avances/{pk}/?motivo=Era 50")

        self.como(self.administrativo)
        self.assertEqual(self.registrar(50).status_code, 201)

    def test_cp_ava_026_anulado_no_se_vuelve_a_anular_409(self):
        self.como(self.administrativo)
        pk = self.registrar(70).data["id"]

        self.como(self.supervisor)
        self.client.delete(f"/api/avances/{pk}/?motivo=Error")
        respuesta = self.client.delete(f"/api/avances/{pk}/?motivo=Otra vez")
        self.assertEqual(respuesta.status_code, 409)

    def test_cp_ava_027_historial_vigentes_excluye_anulados(self):
        self.como(self.administrativo)
        self.registrar(40)
        pk = self.registrar(90).data["id"]

        self.como(self.supervisor)
        self.client.delete(f"/api/avances/{pk}/?motivo=Error")

        todos = self.client.get(f"/api/avances/?compromiso={self.compromiso.pk}").data
        vigentes = self.client.get(
            f"/api/avances/?compromiso={self.compromiso.pk}&vigentes=true"
        ).data
        self.assertEqual(len(todos), 2)
        self.assertEqual(len(vigentes), 1)

    def test_cp_ava_028_historial_web_marca_el_anulado(self):
        self.como(self.administrativo)
        pk = self.registrar(70).data["id"]
        self.como(self.supervisor)
        self.client.delete(f"/api/avances/{pk}/?motivo=Error de digitación")

        self.client.force_login(self.supervisor)
        respuesta = self.client.get(f"/gestion/compromisos/{self.compromiso.pk}/historial/")
        self.assertContains(respuesta, "Anulado")
        self.assertContains(respuesta, "Error de digitación")

    def test_cp_ava_029_swagger_documenta_t2(self):
        self.como(self.admin)
        contenido = self.client.get("/api/schema/").content.decode()
        self.assertIn("/api/avances/", contenido)
