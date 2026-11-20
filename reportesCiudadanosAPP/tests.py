from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from emergenciasTerritorialesAPP.tests import BaseEmergencias, crear_contacto, crear_zona

from .models import DerivacionReporte, ReporteCiudadano
from .transaccion import (
    ReglaNegocioError,
    anular_derivacion,
    derivar_reporte,
    modificar_derivacion,
    resolver_reporte,
)


# ============================================================
# PRUEBAS: TRANSACCIÓN DE DERIVACIÓN DEL REPORTE CIUDADANO
# ============================================================
# Los ID CP-REP-### se registran en la matriz de resultado esperado vs.
# obtenido del informe de Back End.


def crear_reporte(delegacion, **extra):
    datos = {
        "delegacion": delegacion,
        "tipo": "alumbrado",
        "prioridad": "alta",
        "descripcion": "Luminarias apagadas frente a la plaza.",
        "ubicacion": "Av. Francisco de Aguirre 300",
        "nombre_vecino": "Juan Soto",
        "telefono_vecino": "+56 9 8765 4321",
        "email_vecino": "juan.soto@correo.cl",
    }
    datos.update(extra)
    return ReporteCiudadano.objects.create(**datos)


class BaseReportes(BaseEmergencias):

    def setUp(self):
        self.reporte = crear_reporte(self.centro)
        self.reporte_rural = crear_reporte(self.rural)
        self.zona_2 = crear_zona(self.centro, "Sector La Antena")
        self.contacto_2 = crear_contacto(self.centro, "Seguridad Ciudadana")


# ============================================================
# REGLAS DE LA TRANSACCIÓN (MISMAS PARA WEB Y API)
# ============================================================

class PruebasTransaccion(BaseReportes, TestCase):

    def derivar(self, usuario=None, zona=None, contacto=None, reporte=None):
        return derivar_reporte(
            usuario or self.supervisor,
            (reporte or self.reporte).pk,
            (zona or self.zona).pk,
            (contacto or self.contacto).pk,
            "Revisar hoy",
        )

    def test_cp_rep_001_derivar_actualiza_reporte_e_historial(self):
        derivacion = self.derivar()
        self.reporte.refresh_from_db()

        self.assertEqual(self.reporte.estado, "derivado")
        self.assertEqual(self.reporte.zona, self.zona)
        self.assertEqual(self.reporte.contacto, self.contacto)
        self.assertTrue(derivacion.activo)
        self.assertEqual(derivacion.usuario, self.supervisor)

    def test_cp_rep_002_rederivar_conserva_la_anterior_como_historial(self):
        primera = self.derivar()
        segunda = self.derivar(zona=self.zona_2, contacto=self.contacto_2)

        primera.refresh_from_db()
        self.assertFalse(primera.activo)
        self.assertFalse(primera.anulada)
        self.assertTrue(segunda.activo)
        self.assertEqual(self.reporte.derivaciones.count(), 2)
        self.assertEqual(self.reporte.derivaciones.filter(activo=True).count(), 1)

    def test_cp_rep_003_zona_de_otra_delegacion_se_rechaza(self):
        with self.assertRaises(ReglaNegocioError):
            self.derivar(usuario=self.admin, zona=self.zona_rural)

        self.reporte.refresh_from_db()
        self.assertEqual(self.reporte.estado, "pendiente")
        self.assertFalse(DerivacionReporte.objects.exists())

    def test_cp_rep_004_contacto_inactivo_se_rechaza(self):
        self.contacto_2.activo = False
        self.contacto_2.save()

        with self.assertRaises(ReglaNegocioError):
            self.derivar(contacto=self.contacto_2)

    def test_cp_rep_005_reporte_resuelto_no_se_deriva(self):
        self.derivar()
        resolver_reporte(self.supervisor, self.reporte.pk)

        with self.assertRaises(ReglaNegocioError):
            self.derivar(zona=self.zona_2, contacto=self.contacto_2)

    def test_cp_rep_006_fuera_de_ambito_responde_permiso_denegado(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self.derivar(
                usuario=self.supervisor_rural,
                zona=self.zona_rural,
                contacto=self.contacto_rural,
            )

    def test_cp_rep_007_falla_a_mitad_revierte_todo(self):
        # Borde: la derivación anterior ya se marcó como histórica y la
        # nueva ya se creó cuando falla el último paso; nada debe quedar.
        primera = self.derivar()

        with mock.patch.object(
            ReporteCiudadano, "save", side_effect=RuntimeError("falla simulada")
        ):
            with self.assertRaises(RuntimeError):
                self.derivar(zona=self.zona_2, contacto=self.contacto_2)

        primera.refresh_from_db()
        self.reporte.refresh_from_db()
        self.assertTrue(primera.activo)
        self.assertEqual(self.reporte.derivaciones.count(), 1)
        self.assertEqual(self.reporte.zona, self.zona)

    def test_cp_rep_008_modificar_cambia_derivacion_y_reporte(self):
        derivacion = self.derivar()
        modificar_derivacion(
            self.supervisor, derivacion.pk, zona_id=self.zona_2.pk, observacion="Nueva"
        )

        derivacion.refresh_from_db()
        self.reporte.refresh_from_db()
        self.assertEqual(derivacion.zona, self.zona_2)
        self.assertEqual(derivacion.observacion, "Nueva")
        self.assertEqual(self.reporte.zona, self.zona_2)

    def test_cp_rep_009_derivacion_historica_no_se_modifica(self):
        primera = self.derivar()
        self.derivar(zona=self.zona_2, contacto=self.contacto_2)

        with self.assertRaises(ReglaNegocioError):
            modificar_derivacion(self.supervisor, primera.pk, observacion="x")

    def test_cp_rep_010_anular_deja_el_reporte_pendiente(self):
        derivacion = self.derivar()
        anular_derivacion(self.supervisor, derivacion.pk)

        derivacion.refresh_from_db()
        self.reporte.refresh_from_db()
        self.assertFalse(derivacion.activo)
        self.assertTrue(derivacion.anulada)
        self.assertEqual(self.reporte.estado, "pendiente")
        self.assertIsNone(self.reporte.zona)
        self.assertTrue(DerivacionReporte.objects.filter(pk=derivacion.pk).exists())

    def test_cp_rep_011_solo_se_resuelve_un_reporte_derivado(self):
        with self.assertRaises(ReglaNegocioError):
            resolver_reporte(self.supervisor, self.reporte.pk)

        self.derivar()
        reporte = resolver_reporte(self.supervisor, self.reporte.pk)
        self.assertEqual(reporte.estado, "resuelto")
        self.assertIsNotNone(reporte.fecha_resolucion)


# ============================================================
# APLICACIÓN WEB
# ============================================================

class PruebasWebReportes(BaseReportes, TestCase):

    def test_cp_rep_012_administrativo_registra_reporte(self):
        self.client.force_login(self.administrativo)
        respuesta = self.client.post(reverse("reportes:reporte_crear"), {
            "delegacion": self.centro.pk,
            "tipo": "baches",
            "prioridad": "media",
            "descripcion": "Bache profundo",
            "ubicacion": "Calle Cienfuegos 120",
        })

        reporte = ReporteCiudadano.objects.get(descripcion="Bache profundo")
        self.assertRedirects(
            respuesta, reverse("reportes:reporte_detalle", args=[reporte.pk])
        )
        self.assertEqual(reporte.estado, "pendiente")

    def test_cp_rep_013_supervisor_deriva_desde_la_web(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(
            reverse("reportes:reporte_derivar", args=[self.reporte.pk]),
            {"zona": self.zona.pk, "contacto": self.contacto.pk, "observacion": ""},
        )

        self.assertRedirects(
            respuesta, reverse("reportes:reporte_detalle", args=[self.reporte.pk])
        )
        self.reporte.refresh_from_db()
        self.assertEqual(self.reporte.estado, "derivado")

    def test_cp_rep_014_administrativo_no_puede_derivar(self):
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(
            reverse("reportes:reporte_derivar", args=[self.reporte.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_rep_015_reporte_de_otra_delegacion_responde_403(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(
            reverse("reportes:reporte_detalle", args=[self.reporte_rural.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_rep_016_detalle_muestra_historial(self):
        derivar_reporte(self.supervisor, self.reporte.pk, self.zona.pk, self.contacto.pk)
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("reportes:reporte_detalle", args=[self.reporte.pk])
        )
        self.assertContains(respuesta, "Historial de derivaciones")
        self.assertContains(respuesta, "Vigente")

    def test_cp_rep_017_reporte_derivado_no_se_da_de_baja(self):
        derivar_reporte(self.supervisor, self.reporte.pk, self.zona.pk, self.contacto.pk)
        self.client.force_login(self.supervisor)
        self.client.post(reverse("reportes:reporte_cambiar_estado", args=[self.reporte.pk]))

        self.reporte.refresh_from_db()
        self.assertTrue(self.reporte.activo)


# ============================================================
# API RESTFUL
# ============================================================

class PruebasAPIReportes(BaseReportes, APITestCase):

    def como(self, usuario):
        self.client.force_authenticate(user=usuario)

    def derivar_api(self, **extra):
        datos = {
            "reporte": self.reporte.pk,
            "zona": self.zona.pk,
            "contacto": self.contacto.pk,
            "observacion": "Revisar hoy",
        }
        datos.update(extra)
        return self.client.post("/api/derivaciones/", datos, format="json")

    def test_cp_rep_018_get_reportes_solo_de_su_delegacion(self):
        self.como(self.supervisor)
        respuesta = self.client.get("/api/reportes/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual([r["id"] for r in respuesta.data], [self.reporte.pk])

    def test_cp_rep_019_usuario_no_ve_datos_del_vecino(self):
        self.como(self.supervisor)
        datos = self.client.get(f"/api/reportes/{self.reporte.pk}/").data

        for campo in ("nombre_vecino", "telefono_vecino", "email_vecino"):
            self.assertNotIn(campo, datos)
        self.assertEqual(datos["ubicacion"], "Av. Francisco de Aguirre 300")

    def test_cp_rep_020_administrador_ve_datos_del_vecino(self):
        self.como(self.admin)
        datos = self.client.get(f"/api/reportes/{self.reporte.pk}/").data
        self.assertEqual(datos["telefono_vecino"], "+56 9 8765 4321")

    def test_cp_rep_021_post_reporte_crea_pendiente_201(self):
        self.como(self.administrativo)
        respuesta = self.client.post("/api/reportes/", {
            "delegacion": self.centro.pk,
            "tipo": "basura",
            "prioridad": "baja",
            "descripcion": "Microbasural",
            "ubicacion": "Pasaje Los Olivos",
            "estado": "resuelto",
        }, format="json")

        self.assertEqual(respuesta.status_code, 201)
        # El estado es de solo lectura: se ignora el valor enviado.
        self.assertEqual(respuesta.data["estado"], "pendiente")

    def test_cp_rep_022_post_derivacion_201(self):
        self.como(self.supervisor)
        respuesta = self.derivar_api()

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["reporte_estado"], "derivado")
        # El nombre del funcionario es dato sensible.
        self.assertNotIn("usuario_nombre", respuesta.data)

    def test_cp_rep_023_regla_de_negocio_responde_409(self):
        self.como(self.admin)
        respuesta = self.derivar_api(zona=self.zona_rural.pk)

        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("delegación", respuesta.data["detail"])

    def test_cp_rep_024_datos_faltantes_responden_400(self):
        self.como(self.supervisor)
        respuesta = self.client.post(
            "/api/derivaciones/", {"reporte": self.reporte.pk}, format="json"
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("zona", respuesta.data)
        self.assertIn("contacto", respuesta.data)

    def test_cp_rep_025_derivar_reporte_ajeno_responde_403(self):
        self.como(self.supervisor)
        respuesta = self.derivar_api(
            reporte=self.reporte_rural.pk,
            zona=self.zona_rural.pk,
            contacto=self.contacto_rural.pk,
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_cp_rep_026_administrativo_no_deriva_403(self):
        self.como(self.administrativo)
        self.assertEqual(self.derivar_api().status_code, 403)

    def test_cp_rep_027_put_modifica_la_derivacion(self):
        self.como(self.supervisor)
        pk = self.derivar_api().data["id"]

        respuesta = self.client.put(f"/api/derivaciones/{pk}/", {
            "zona": self.zona_2.pk,
            "contacto": self.contacto_2.pk,
            "observacion": "Cambio de zona",
        }, format="json")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["zona"], self.zona_2.pk)

    def test_cp_rep_028_delete_anula_y_conserva_historial(self):
        self.como(self.supervisor)
        pk = self.derivar_api().data["id"]

        respuesta = self.client.delete(f"/api/derivaciones/{pk}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.data["anulada"])
        self.assertEqual(respuesta.data["reporte_estado"], "pendiente")
        self.assertTrue(DerivacionReporte.objects.filter(pk=pk).exists())

    def test_cp_rep_029_resolver_y_luego_no_modificar(self):
        self.como(self.supervisor)
        pk = self.derivar_api().data["id"]

        respuesta = self.client.post(f"/api/reportes/{self.reporte.pk}/resolver/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["estado"], "resuelto")

        respuesta = self.client.delete(f"/api/derivaciones/{pk}/")
        self.assertEqual(respuesta.status_code, 409)

        respuesta = self.client.patch(
            f"/api/reportes/{self.reporte.pk}/", {"prioridad": "baja"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 409)

    def test_cp_rep_030_historial_filtrado_por_reporte(self):
        self.como(self.supervisor)
        self.derivar_api()
        self.derivar_api(zona=self.zona_2.pk, contacto=self.contacto_2.pk)

        todas = self.client.get(f"/api/derivaciones/?reporte={self.reporte.pk}").data
        vigentes = self.client.get(
            f"/api/derivaciones/?reporte={self.reporte.pk}&vigentes=true"
        ).data

        self.assertEqual(len(todas), 2)
        self.assertEqual(len(vigentes), 1)

    def test_cp_rep_031_filtro_reporte_invalido_responde_400(self):
        self.como(self.supervisor)
        respuesta = self.client.get("/api/derivaciones/?reporte=abc")
        self.assertEqual(respuesta.status_code, 400)

    def test_cp_rep_032_delete_reporte_derivado_responde_409(self):
        self.como(self.supervisor)
        self.derivar_api()

        respuesta = self.client.delete(f"/api/reportes/{self.reporte.pk}/")
        self.assertEqual(respuesta.status_code, 409)
