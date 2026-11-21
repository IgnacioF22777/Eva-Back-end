from unittest import mock

from django.test import RequestFactory, override_settings

from .errores import MENSAJE_500, error_servidor, pagina_no_encontrada
from .tests import BaseAPI


# ============================================================
# PRUEBAS: DATOS SENSIBLES Y MANEJO SEGURO DE ERRORES DE LA API
# ============================================================
# Los ID CP-SEG-### se registran en la matriz de resultado esperado vs.
# obtenido del informe de Back End.

CAMPOS_SENSIBLES = ("email", "telefono", "celular")


class PruebasDatosSensiblesDelegacion(BaseAPI):

    def test_cp_seg_001_administrador_ve_contacto_de_delegacion(self):
        self.como(self.admin)
        datos = self.client.get(f"/api/delegaciones/{self.centro.pk}/").data

        for campo in CAMPOS_SENSIBLES:
            self.assertIn(campo, datos)

    def test_cp_seg_002_perfil_usuario_no_ve_contacto(self):
        for usuario in (self.supervisor, self.administrativo_centro):
            self.como(usuario)

            detalle = self.client.get(f"/api/delegaciones/{self.centro.pk}/").data
            listado = self.client.get("/api/delegaciones/").data

            for campo in CAMPOS_SENSIBLES:
                self.assertNotIn(campo, detalle)
                self.assertNotIn(campo, listado[0])
            self.assertEqual(detalle["nombre"], "Delegación Centro")

    def test_cp_seg_003_swagger_marca_los_campos_sensibles(self):
        self.como(self.admin)
        esquema = self.client.get("/api/schema/").content.decode()
        self.assertIn("solo lo recibe el perfil Administrador", esquema)


class PruebasErroresJSON(BaseAPI):

    def test_cp_seg_004_ruta_inexistente_de_la_api_responde_404_json(self):
        self.como(self.admin)
        respuesta = self.client.get("/api/no-existe/")

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        self.assertIn("detail", respuesta.json())

    def test_cp_seg_005_fuera_de_la_api_se_mantiene_la_pagina_html(self):
        respuesta = self.client.get("/pagina-que-no-existe/")

        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("text/html", respuesta["Content-Type"])

    def test_cp_seg_006_error_no_controlado_responde_500_json_sin_detalles(self):
        self.como(self.admin)

        with mock.patch(
            "apiAPP.views.filtrar_por_estado",
            side_effect=RuntimeError("SELECT secreto FROM tabla_interna"),
        ), self.assertLogs("sgr.api", level="ERROR") as registro:
            respuesta = self.client.get("/api/delegaciones/")

        # La traza sí queda en el log del servidor.
        self.assertIn("/api/delegaciones/", registro.output[0])

        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(respuesta.data["detail"], MENSAJE_500)
        # No se filtra la traza ni el mensaje interno de la excepción.
        self.assertNotIn("secreto", respuesta.content.decode())

    @override_settings(DEBUG=False)
    def test_cp_seg_007_handlers_de_django_responden_json_bajo_api(self):
        fabrica = RequestFactory()

        respuesta_500 = error_servidor(fabrica.get("/api/delegaciones/"))
        respuesta_404 = pagina_no_encontrada(fabrica.get("/api/x/"), Exception())

        self.assertEqual(respuesta_500.status_code, 500)
        self.assertEqual(respuesta_500["Content-Type"], "application/json")
        self.assertEqual(respuesta_404.status_code, 404)
        self.assertEqual(respuesta_404["Content-Type"], "application/json")

    def test_cp_seg_008_metodo_no_permitido_responde_405_json(self):
        self.como(self.admin)
        respuesta = self.client.post(f"/api/delegaciones/{self.centro.pk}/reactivar/x/")
        self.assertIn(respuesta.status_code, (404, 405))
        self.assertEqual(respuesta["Content-Type"], "application/json")
