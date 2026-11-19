from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from apiAPP.tests import crear_delegacion
from delegacionesAPP.models import Delegacion
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from tubo_gestionAPP.tests import CLAVE, crear_usuario

from .forms import ContactoEmergenciaForm, ZonaRiesgoForm
from .models import ContactoEmergencia, ZonaRiesgo


# ============================================================
# PRUEBAS: EMERGENCIAS TERRITORIALES (MANTENEDORES 1 Y 2)
# ============================================================
# Los ID CP-EMG-### se registran en la matriz de resultado esperado vs.
# obtenido del informe de Back End.


def crear_zona(delegacion, nombre="Quebrada Peñuelas", **extra):
    datos = {
        "nombre": nombre,
        "delegacion": delegacion,
        "descripcion_riesgo": "Desborde en lluvias intensas.",
        "nivel_peligro": "alto",
        "coordenadas_aprox": "-29.94, -71.26",
    }
    datos.update(extra)
    return ZonaRiesgo.objects.create(**datos)


def crear_contacto(delegacion, nombre="Central de Bomberos", **extra):
    datos = {
        "nombre": nombre,
        "cargo": "Unidad de Emergencia",
        "telefono": "+56 9 1234 5678",
        "email": "central@bomberos.cl",
        "delegacion": delegacion,
    }
    datos.update(extra)
    return ContactoEmergencia.objects.create(**datos)


class BaseEmergencias:

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = crear_delegacion("Delegación Centro")
        cls.rural = crear_delegacion("Delegación Rural")

        cls.admin = crear_usuario("11.111.111-1", "admin@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario(
            "12.345.678-5", "sup@laserena.cl", SUPERVISOR, delegacion=cls.centro
        )
        cls.administrativo = crear_usuario(
            "22.222.222-2", "adm@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro
        )
        cls.supervisor_rural = crear_usuario(
            "15.555.555-5", "sup.rural@laserena.cl", SUPERVISOR, delegacion=cls.rural
        )

        cls.zona = crear_zona(cls.centro)
        cls.zona_rural = crear_zona(cls.rural, "Cerro Grande")
        cls.contacto = crear_contacto(cls.centro, zona_asignada=cls.zona)
        cls.contacto_rural = crear_contacto(cls.rural, "Carabineros Rural")


# ============================================================
# MODELOS Y FORMULARIOS
# ============================================================

class PruebasModelosYFormularios(BaseEmergencias, TestCase):

    def test_cp_emg_001_delegacion_con_zonas_no_se_borra(self):
        # PROTECT: antes era CASCADE y borraba zonas, alertas y contactos.
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            Delegacion.objects.filter(pk=self.centro.pk).delete()

        self.assertTrue(ZonaRiesgo.objects.filter(pk=self.zona.pk).exists())

    def test_cp_emg_002_zona_duplicada_en_misma_delegacion(self):
        form = ZonaRiesgoForm(data={
            "nombre": "quebrada peñuelas",
            "delegacion": self.centro.pk,
            "nivel_peligro": "bajo",
            "descripcion_riesgo": "Otra descripción",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("nombre", form.errors)

    def test_cp_emg_003_mismo_nombre_en_otra_delegacion_se_acepta(self):
        form = ZonaRiesgoForm(data={
            "nombre": "Quebrada Peñuelas",
            "delegacion": self.rural.pk,
            "nivel_peligro": "bajo",
            "descripcion_riesgo": "Riesgo en la delegación rural",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_cp_emg_004_telefono_invalido_se_rechaza(self):
        form = ContactoEmergenciaForm(data={
            "nombre": "Contacto",
            "cargo": "Cargo",
            "telefono": "abc",
            "delegacion": self.centro.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("telefono", form.errors)

    def test_cp_emg_005_numero_corto_de_emergencia_se_acepta(self):
        # Borde: 132 (Bomberos) tiene solo 3 dígitos y es válido.
        form = ContactoEmergenciaForm(data={
            "nombre": "Bomberos",
            "cargo": "Central",
            "telefono": "132",
            "delegacion": self.centro.pk,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_cp_emg_006_zona_de_otra_delegacion_se_rechaza(self):
        form = ContactoEmergenciaForm(data={
            "nombre": "Contacto",
            "cargo": "Cargo",
            "telefono": "51 2 000 000",
            "delegacion": self.centro.pk,
            "zona_asignada": self.zona_rural.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("zona_asignada", form.errors)

    def test_cp_emg_007_supervisor_solo_elige_su_delegacion(self):
        form = ZonaRiesgoForm(usuario=self.supervisor)
        self.assertEqual(
            list(form.fields["delegacion"].queryset), [self.centro]
        )


# ============================================================
# APLICACIÓN WEB
# ============================================================

class PruebasWeb(BaseEmergencias, TestCase):

    def test_cp_emg_008_listado_requiere_sesion(self):
        respuesta = self.client.get(reverse("emergencias:zona_lista"))
        self.assertEqual(respuesta.status_code, 302)

    def test_cp_emg_009_supervisor_ve_solo_su_delegacion(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("emergencias:zona_lista"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Quebrada Peñuelas")
        self.assertNotContains(respuesta, "Cerro Grande")

    def test_cp_emg_010_supervisor_crea_zona(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(reverse("emergencias:zona_crear"), {
            "nombre": "Sector La Florida",
            "delegacion": self.centro.pk,
            "nivel_peligro": "medio",
            "descripcion_riesgo": "Microbasurales",
        })

        self.assertRedirects(respuesta, reverse("emergencias:zona_lista"))
        self.assertTrue(ZonaRiesgo.objects.filter(nombre="Sector La Florida").exists())

    def test_cp_emg_011_administrativo_no_crea_zonas(self):
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("emergencias:zona_crear"))
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_emg_012_editar_zona_de_otra_delegacion_responde_403(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(
            reverse("emergencias:zona_editar", args=[self.zona_rural.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_emg_013_zona_con_contactos_no_se_da_de_baja(self):
        self.client.force_login(self.supervisor)
        self.client.post(reverse("emergencias:zona_cambiar_estado", args=[self.zona.pk]))

        self.zona.refresh_from_db()
        self.assertTrue(self.zona.activo)

    def test_cp_emg_014_baja_logica_y_reactivacion_de_contacto(self):
        self.client.force_login(self.supervisor)
        url = reverse("emergencias:contacto_cambiar_estado", args=[self.contacto.pk])

        self.client.post(url)
        self.contacto.refresh_from_db()
        self.assertFalse(self.contacto.activo)
        self.assertTrue(ContactoEmergencia.objects.filter(pk=self.contacto.pk).exists())

        self.client.post(url)
        self.contacto.refresh_from_db()
        self.assertTrue(self.contacto.activo)

    def test_cp_emg_015_menu_muestra_emergencias(self):
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("emergencias:contacto_lista"))
        self.assertContains(respuesta, "Zonas de Riesgo")
        self.assertContains(respuesta, "Reportes Ciudadanos")


# ============================================================
# API RESTFUL
# ============================================================

class PruebasAPI(BaseEmergencias, APITestCase):

    def como(self, usuario):
        self.client.force_authenticate(user=usuario)

    def test_cp_emg_016_sin_token_responde_401(self):
        self.assertEqual(self.client.get("/api/zonas-riesgo/").status_code, 401)

    def test_cp_emg_017_token_jwt_da_acceso(self):
        token = self.client.post(
            "/api/token/",
            {"username": "12.345.678-5", "password": CLAVE},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        respuesta = self.client.get("/api/contactos-emergencia/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/json")

    def test_cp_emg_018_administrador_ve_datos_sensibles(self):
        self.como(self.admin)
        respuesta = self.client.get(f"/api/contactos-emergencia/{self.contacto.pk}/")

        self.assertEqual(respuesta.data["telefono"], "+56 9 1234 5678")
        self.assertEqual(respuesta.data["email"], "central@bomberos.cl")

    def test_cp_emg_019_usuario_no_ve_telefono_ni_correo(self):
        for usuario in (self.supervisor, self.administrativo):
            self.como(usuario)
            respuesta = self.client.get(f"/api/contactos-emergencia/{self.contacto.pk}/")

            self.assertEqual(respuesta.status_code, 200)
            self.assertNotIn("telefono", respuesta.data)
            self.assertNotIn("email", respuesta.data)
            self.assertEqual(respuesta.data["nombre"], "Central de Bomberos")

    def test_cp_emg_020_usuario_no_ve_coordenadas_en_listado(self):
        self.como(self.supervisor)
        respuesta = self.client.get("/api/zonas-riesgo/")

        self.assertEqual(len(respuesta.data), 1)
        self.assertNotIn("coordenadas_aprox", respuesta.data[0])

    def test_cp_emg_021_crear_zona_responde_201(self):
        self.como(self.supervisor)
        respuesta = self.client.post("/api/zonas-riesgo/", {
            "nombre": "Sector Las Compañías",
            "delegacion": self.centro.pk,
            "nivel_peligro": "critico",
            "descripcion_riesgo": "Riesgo de incendio",
        }, format="json")

        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue(respuesta.data["activo"])

    def test_cp_emg_022_datos_invalidos_responden_400_por_campo(self):
        self.como(self.supervisor)
        respuesta = self.client.post("/api/contactos-emergencia/", {
            "nombre": "Contacto",
            "cargo": "Cargo",
            "telefono": "abc",
            "delegacion": self.centro.pk,
        }, format="json")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("telefono", respuesta.data)

    def test_cp_emg_023_crear_en_otra_delegacion_se_rechaza(self):
        self.como(self.supervisor)
        respuesta = self.client.post("/api/zonas-riesgo/", {
            "nombre": "Zona ajena",
            "delegacion": self.rural.pk,
            "nivel_peligro": "bajo",
            "descripcion_riesgo": "No es de su delegación",
        }, format="json")

        self.assertIn(respuesta.status_code, (400, 403))
        self.assertFalse(ZonaRiesgo.objects.filter(nombre="Zona ajena").exists())

    def test_cp_emg_024_consultar_zona_ajena_responde_403(self):
        self.como(self.supervisor)
        respuesta = self.client.get(f"/api/zonas-riesgo/{self.zona_rural.pk}/")
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_emg_025_id_inexistente_responde_404(self):
        self.como(self.admin)
        respuesta = self.client.get("/api/zonas-riesgo/99999/")
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("detail", respuesta.data)

    def test_cp_emg_026_put_modifica_contacto(self):
        self.como(self.supervisor)
        respuesta = self.client.put(f"/api/contactos-emergencia/{self.contacto.pk}/", {
            "nombre": "Central de Bomberos",
            "cargo": "Comandancia",
            "telefono": "132",
            "email": "",
            "delegacion": self.centro.pk,
            "zona_asignada": self.zona.pk,
        }, format="json")

        self.assertEqual(respuesta.status_code, 200)
        self.contacto.refresh_from_db()
        self.assertEqual(self.contacto.cargo, "Comandancia")

    def test_cp_emg_027_delete_es_baja_logica_y_se_reactiva(self):
        self.como(self.supervisor)
        url = f"/api/contactos-emergencia/{self.contacto.pk}/"

        respuesta = self.client.delete(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data["activo"])
        self.assertTrue(ContactoEmergencia.objects.filter(pk=self.contacto.pk).exists())

        respuesta = self.client.post(url + "reactivar/")
        self.assertTrue(respuesta.data["activo"])

    def test_cp_emg_028_delete_zona_con_contactos_responde_409(self):
        self.como(self.supervisor)
        respuesta = self.client.delete(f"/api/zonas-riesgo/{self.zona.pk}/")
        self.assertEqual(respuesta.status_code, 409)

    def test_cp_emg_029_administrativo_no_puede_crear_403(self):
        self.como(self.administrativo)
        respuesta = self.client.post("/api/zonas-riesgo/", {}, format="json")
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_emg_030_swagger_documenta_los_endpoints(self):
        respuesta = self.client.get("/api/schema/")
        contenido = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("/api/zonas-riesgo/", contenido)
        self.assertIn("/api/contactos-emergencia/", contenido)
