from unittest import mock

from rest_framework.test import APITestCase

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .models import AsignacionCompromiso, Compromiso, RegistroAvance
from .tests import CLAVE, crear_usuario


# ============================================================
# PRUEBAS: API DE LA TRANSACCIÓN T1 (ASIGNACIÓN DEL COMPROMISO)
# ============================================================
# Los ID CP-ASG-### se registran en la matriz de resultado esperado vs.
# obtenido del informe de Back End.


def crear_delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre,
        direccion="Dirección de prueba",
        encargado="Encargado",
        email=f"{nombre.split()[-1].lower()}.t1@laserena.cl",
        telefono="51 2 000 000",
        celular="+56 9 1111 1111",
    )


class PruebasAPIAsignaciones(APITestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = crear_delegacion("Delegación Centro")
        cls.rural = crear_delegacion("Delegación Rural")
        cls.aseo = Servicio.objects.create(delegacion=cls.centro, nombre="Aseo")
        cls.tramites = Servicio.objects.create(delegacion=cls.centro, nombre="Trámites")
        cls.riego = Servicio.objects.create(delegacion=cls.rural, nombre="Riego")
        cls.inactivo = Servicio.objects.create(
            delegacion=cls.centro, nombre="Dado de baja", activo=False
        )

        cls.admin = crear_usuario("13.333.333-3", "admin.t1@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario(
            "14.444.444-4", "sup.t1@laserena.cl", SUPERVISOR, delegacion=cls.centro
        )
        cls.administrativo = crear_usuario(
            "15.555.555-5", "adm.t1@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro
        )

    def setUp(self):
        self.compromiso = Compromiso.objects.create(tarea="Plataforma de trámites", cumplimiento=0)

    def como(self, usuario):
        self.client.force_authenticate(user=usuario)

    def asignar(self, servicio=None, delegacion=None, compromiso=None, **extra):
        servicio = servicio or self.aseo
        datos = {
            "compromiso": (compromiso or self.compromiso).pk,
            "delegacion": (delegacion or servicio.delegacion).pk,
            "servicio": servicio.pk,
            "observacion": "Coordinar con la unidad",
        }
        datos.update(extra)
        return self.client.post("/api/asignaciones/", datos, format="json")

    # --- REGISTRAR (POST) ---
    def test_cp_asg_001_sin_token_responde_401(self):
        self.assertEqual(self.client.get("/api/asignaciones/").status_code, 401)

    def test_cp_asg_002_supervisor_asigna_compromiso(self):
        self.como(self.supervisor)
        respuesta = self.asignar()

        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue(respuesta.data["vigente"])
        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.delegacion, self.centro)
        self.assertEqual(self.compromiso.servicio, self.aseo)

    def test_cp_asg_003_con_token_jwt(self):
        token = self.client.post(
            "/api/token/", {"username": "14.444.444-4", "password": CLAVE}, format="json"
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.asignar().status_code, 201)

    def test_cp_asg_004_reasignar_deja_historial(self):
        self.como(self.supervisor)
        primera = self.asignar().data["id"]
        segunda = self.asignar(servicio=self.tramites).data["id"]

        self.assertFalse(AsignacionCompromiso.objects.get(pk=primera).activo)
        self.assertTrue(AsignacionCompromiso.objects.get(pk=segunda).activo)
        self.assertEqual(self.compromiso.asignaciones.count(), 2)

    def test_cp_asg_005_supervisor_no_asigna_a_otra_delegacion_403(self):
        self.como(self.supervisor)
        respuesta = self.asignar(servicio=self.riego)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(AsignacionCompromiso.objects.exists())

    def test_cp_asg_006_servicio_de_otra_delegacion_responde_409(self):
        self.como(self.admin)
        respuesta = self.asignar(servicio=self.riego, delegacion=self.centro)
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("no pertenece", respuesta.data["detail"])

    def test_cp_asg_007_servicio_inactivo_responde_409(self):
        self.como(self.admin)
        respuesta = self.asignar(servicio=self.inactivo)
        self.assertEqual(respuesta.status_code, 409)

    def test_cp_asg_008_compromiso_inactivo_responde_409(self):
        self.compromiso.activo = False
        self.compromiso.save()
        self.como(self.admin)
        self.assertEqual(self.asignar().status_code, 409)

    def test_cp_asg_009_compromiso_inexistente_responde_404(self):
        self.como(self.admin)
        respuesta = self.client.post("/api/asignaciones/", {
            "compromiso": 99999, "delegacion": self.centro.pk, "servicio": self.aseo.pk,
        }, format="json")
        self.assertEqual(respuesta.status_code, 404)

    def test_cp_asg_010_datos_faltantes_responden_400(self):
        self.como(self.supervisor)
        respuesta = self.client.post(
            "/api/asignaciones/", {"compromiso": self.compromiso.pk}, format="json"
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("servicio", respuesta.data)

    def test_cp_asg_011_administrativo_no_asigna_403(self):
        self.como(self.administrativo)
        self.assertEqual(self.asignar().status_code, 403)

    def test_cp_asg_012_falla_a_mitad_revierte_todo(self):
        self.como(self.supervisor)
        self.asignar()

        with mock.patch.object(
            Compromiso, "save", side_effect=RuntimeError("falla simulada")
        ), self.assertLogs("sgr.api", level="ERROR"):
            respuesta = self.asignar(servicio=self.tramites)

        # El error inesperado responde 500 en JSON y no deja nada a medias.
        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(self.compromiso.asignaciones.count(), 1)
        self.assertTrue(self.compromiso.asignaciones.get().activo)

    # --- CONSULTAR (GET) ---
    def test_cp_asg_013_historial_y_filtros(self):
        self.como(self.supervisor)
        self.asignar()
        self.asignar(servicio=self.tramites)

        todas = self.client.get(f"/api/asignaciones/?compromiso={self.compromiso.pk}").data
        vigentes = self.client.get(
            f"/api/asignaciones/?compromiso={self.compromiso.pk}&vigentes=true"
        ).data
        self.assertEqual(len(todas), 2)
        self.assertEqual(len(vigentes), 1)
        self.assertEqual(
            self.client.get("/api/asignaciones/?compromiso=abc").status_code, 400
        )

    def test_cp_asg_014_fuera_de_ambito_no_se_ve(self):
        self.como(self.admin)
        pk = self.asignar(servicio=self.riego).data["id"]

        self.como(self.administrativo)
        self.assertEqual(self.client.get("/api/asignaciones/").data, [])
        self.assertEqual(self.client.get(f"/api/asignaciones/{pk}/").status_code, 403)

    def test_cp_asg_015_nombre_del_funcionario_solo_para_administrador(self):
        self.como(self.supervisor)
        pk = self.asignar().data["id"]
        self.assertNotIn("asignado_por", self.client.get(f"/api/asignaciones/{pk}/").data)

        self.como(self.admin)
        self.assertIn("asignado_por", self.client.get(f"/api/asignaciones/{pk}/").data)

    # --- MODIFICAR (PUT) ---
    def test_cp_asg_016_corregir_observacion(self):
        self.como(self.supervisor)
        pk = self.asignar().data["id"]

        respuesta = self.client.put(
            f"/api/asignaciones/{pk}/", {"observacion": "Contactar a Juan"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["observacion"], "Contactar a Juan")
        self.assertEqual(respuesta.data["servicio"], self.aseo.pk)

    def test_cp_asg_017_asignacion_historica_no_se_modifica_409(self):
        self.como(self.supervisor)
        antigua = self.asignar().data["id"]
        self.asignar(servicio=self.tramites)

        respuesta = self.client.put(
            f"/api/asignaciones/{antigua}/", {"observacion": "x"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 409)

    # --- ANULAR (DELETE) ---
    def test_cp_asg_018_anular_vuelve_a_la_asignacion_anterior(self):
        self.como(self.supervisor)
        primera = self.asignar().data["id"]
        segunda = self.asignar(servicio=self.tramites).data["id"]

        respuesta = self.client.delete(
            f"/api/asignaciones/{segunda}/", {"motivo": "Servicio equivocado"}, format="json"
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["anulada"])
        self.assertTrue(AsignacionCompromiso.objects.get(pk=primera).activo)
        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.servicio, self.aseo)
        # Baja lógica: la anulada sigue en el historial.
        self.assertTrue(AsignacionCompromiso.objects.filter(pk=segunda).exists())

    def test_cp_asg_019_anular_la_unica_deja_sin_asignar(self):
        self.como(self.supervisor)
        pk = self.asignar().data["id"]

        self.client.delete(f"/api/asignaciones/{pk}/?motivo=Error")
        self.compromiso.refresh_from_db()
        self.assertIsNone(self.compromiso.delegacion)
        self.assertIsNone(self.compromiso.servicio)

    def test_cp_asg_020_anular_sin_motivo_responde_400(self):
        self.como(self.supervisor)
        pk = self.asignar().data["id"]

        respuesta = self.client.delete(f"/api/asignaciones/{pk}/")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("motivo", respuesta.data)

    def test_cp_asg_021_con_avances_no_se_anula_409(self):
        self.como(self.supervisor)
        pk = self.asignar().data["id"]
        RegistroAvance.objects.create(
            compromiso=self.compromiso,
            usuario_registro=self.administrativo,
            porcentaje_avance=30,
            evidencia="Acta",
        )

        respuesta = self.client.delete(f"/api/asignaciones/{pk}/?motivo=Error")
        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("avances", respuesta.data["detail"])

    def test_cp_asg_022_anulada_no_se_vuelve_a_anular_409(self):
        self.como(self.supervisor)
        pk = self.asignar().data["id"]
        self.client.delete(f"/api/asignaciones/{pk}/?motivo=Error")

        self.como(self.admin)
        respuesta = self.client.delete(f"/api/asignaciones/{pk}/?motivo=Otra vez")
        self.assertEqual(respuesta.status_code, 409)

    def test_cp_asg_023_historial_web_marca_la_anulada(self):
        self.como(self.supervisor)
        self.asignar()
        pk = self.asignar(servicio=self.tramites).data["id"]
        self.client.delete(f"/api/asignaciones/{pk}/?motivo=Servicio equivocado")

        self.client.force_login(self.supervisor)
        respuesta = self.client.get(f"/gestion/compromisos/{self.compromiso.pk}/historial/")
        self.assertContains(respuesta, "Anulada")
        self.assertContains(respuesta, "Servicio equivocado")

    def test_cp_asg_024_swagger_documenta_t1(self):
        self.como(self.admin)
        self.assertIn("/api/asignaciones/", self.client.get("/api/schema/").content.decode())
