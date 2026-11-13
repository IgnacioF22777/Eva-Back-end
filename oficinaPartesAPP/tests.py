"""
Evaluación 3 - Tubo de cartas de Oficina de Partes.

Cada prueba tiene un ID CP-CTA-xxx para la matriz de resultado esperado
vs. obtenido del informe. Se incluyen casos normales y de borde.
"""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from tubo_gestionAPP.tests import crear_usuario

from .models import DIAS_ALERTA, CartaOficinaPartes


class BaseCartas(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro", direccion="D", encargado="E",
            email="c@laserena.cl", telefono="1", celular="1",
        )
        cls.mar = Delegacion.objects.create(
            nombre="Delegación Av. del Mar", direccion="D", encargado="E",
            email="m@laserena.cl", telefono="1", celular="1",
        )
        cls.admin = crear_usuario("11.111.111-1", "admin@laserena.cl", ADMINISTRADOR)
        cls.supervisor = crear_usuario("12.345.678-5", "sup@laserena.cl", SUPERVISOR, delegacion=cls.centro)
        cls.administrativo = crear_usuario("22.222.222-2", "adm@laserena.cl", ADMINISTRATIVO, delegacion=cls.centro)
        cls.sin_delegacion = crear_usuario("15.555.555-5", "sin@laserena.cl", ADMINISTRATIVO)

    def carta(self, delegacion=None, **campos):
        datos = {
            "delegacion": delegacion or self.centro,
            "remitente": "Junta de Vecinos El Faro",
            "tema": "Solicita patrocinio para feria costumbrista",
            "numero_ingreso": "10093",
        }
        datos.update(campos)
        return CartaOficinaPartes.objects.create(**datos)

    def datos(self, **cambios):
        datos = {
            "delegacion": self.centro.pk,
            "fecha_recepcion": date.today().isoformat(),
            "numero_ingreso": "10219",
            "destinatario": "ALCALDESA",
            "remitente": "Cruz Roja Chilena",
            "telefono_contacto": "+56 9 5317 1972",
            "tema": "Solicita apoyo para limpieza de playas",
            "fecha_actividad": "09 al 14/07/2026",
            "encargado_seguimiento": "Patrocinios",
            "estado": "EN_PROCESO",
            "pronunciamiento": "",
            "derivada_a": "",
            "observacion": "",
        }
        datos.update(cambios)
        return datos


class PruebasModeloCarta(BaseCartas):

    def test_CP_CTA_001_fecha_de_cierre_automatica(self):
        """CP-CTA-001: al finalizar o marcar «no aplica» se fija la fecha de cierre; al reabrir se borra."""
        carta = self.carta()
        self.assertIsNone(carta.fecha_cierre)

        carta.estado = CartaOficinaPartes.FINALIZADA
        carta.save()
        self.assertEqual(carta.fecha_cierre, date.today())

        carta.estado = CartaOficinaPartes.EN_PROCESO
        carta.save(update_fields=["estado"])
        carta.refresh_from_db()
        self.assertIsNone(carta.fecha_cierre)

    def test_CP_CTA_002_atrasada_desde_el_dia_16(self):
        """CP-CTA-002 (borde): una carta en proceso con 15 días no está atrasada; con 16 sí; cerrada nunca."""
        hoy = date.today()
        en_limite = self.carta(fecha_recepcion=hoy - timedelta(days=DIAS_ALERTA))
        pasada = self.carta(fecha_recepcion=hoy - timedelta(days=DIAS_ALERTA + 1))
        cerrada = self.carta(fecha_recepcion=hoy - timedelta(days=60), estado=CartaOficinaPartes.NO_APLICA)

        self.assertFalse(en_limite.atrasada)
        self.assertTrue(pasada.atrasada)
        self.assertFalse(cerrada.atrasada)

    def test_CP_CTA_003_validaciones_del_modelo(self):
        """CP-CTA-003 (borde): remitente vacío, tema en blanco, fecha futura y teléfono inválido se rechazan."""
        casos = {
            "remitente": {"remitente": "   "},
            "tema": {"tema": "   "},
            "fecha_recepcion": {"fecha_recepcion": date.today() + timedelta(days=1)},
            "telefono_contacto": {"telefono_contacto": "123"},
        }
        for campo, cambios in casos.items():
            datos = {"delegacion": self.centro, "remitente": "X", "tema": "Y"}
            datos.update(cambios)
            with self.subTest(campo=campo):
                with self.assertRaises(ValidationError) as error:
                    CartaOficinaPartes(**datos).full_clean()
                self.assertIn(campo, error.exception.message_dict)

    def test_CP_CTA_004_telefonos_chilenos_validos(self):
        """CP-CTA-004: se aceptan los formatos de teléfono de la planilla."""
        for telefono in ("9 5317 1972", "+56 9 5317 1972", "512200000", "(51) 220-0000", ""):
            with self.subTest(telefono=telefono):
                CartaOficinaPartes(
                    delegacion=self.centro, remitente="X", tema="Y", telefono_contacto=telefono
                ).full_clean()

    def test_CP_CTA_005_numero_de_ingreso_repetido_se_permite(self):
        """CP-CTA-005 (borde): como en la planilla, dos cartas pueden compartir N° de ingreso."""
        self.carta(numero_ingreso="10093")
        segunda = CartaOficinaPartes(
            delegacion=self.centro, remitente="Otra persona", tema="Otro tema", numero_ingreso="10093"
        )
        segunda.full_clean()


class PruebasTuboCartas(BaseCartas):

    def test_CP_CTA_006_administrativo_registra_carta(self):
        """CP-CTA-006: el Administrativo (Apoyo Administrativo) registra una carta en su delegación."""
        self.client.force_login(self.administrativo)
        respuesta = self.client.post(reverse("oficina_partes:carta_crear"), self.datos())

        self.assertRedirects(respuesta, reverse("oficina_partes:carta_lista"))
        carta = CartaOficinaPartes.objects.get()
        self.assertEqual(carta.delegacion, self.centro)
        self.assertEqual(carta.registrada_por, self.administrativo)

    def test_CP_CTA_007_no_registra_en_otra_delegacion(self):
        """CP-CTA-007 (borde): una delegación ajena enviada a mano es opción no válida."""
        self.client.force_login(self.administrativo)
        respuesta = self.client.post(reverse("oficina_partes:carta_crear"), self.datos(delegacion=self.mar.pk))

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("delegacion", respuesta.context["form"].errors)
        self.assertFalse(CartaOficinaPartes.objects.exists())

    def test_CP_CTA_008_cada_delegacion_ve_sus_cartas(self):
        """CP-CTA-008: el tubo muestra solo las cartas de la delegación; el Administrador ve todas."""
        self.carta(remitente="REMITENTE CENTRO")
        self.carta(delegacion=self.mar, remitente="REMITENTE MAR")

        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        self.assertContains(respuesta, "REMITENTE CENTRO")
        self.assertNotContains(respuesta, "REMITENTE MAR")

        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        self.assertContains(respuesta, "REMITENTE MAR")

    def test_CP_CTA_009_no_opera_cartas_ajenas(self):
        """CP-CTA-009 (borde): editar o anular una carta de otra delegación es 403."""
        ajena = self.carta(delegacion=self.mar)
        self.client.force_login(self.supervisor)

        self.assertEqual(self.client.get(reverse("oficina_partes:carta_editar", args=[ajena.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("oficina_partes:carta_cambiar_estado", args=[ajena.pk])).status_code, 403)
        ajena.refresh_from_db()
        self.assertTrue(ajena.activo)

    def test_CP_CTA_010_seguimiento_cambia_estado(self):
        """CP-CTA-010: el seguimiento registra pronunciamiento, derivación y cierre."""
        carta = self.carta()
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(
            reverse("oficina_partes:carta_editar", args=[carta.pk]),
            self.datos(estado="FINALIZADA", pronunciamiento="DELEGADO", derivada_a="DISERCO"),
        )

        self.assertRedirects(respuesta, reverse("oficina_partes:carta_lista"))
        carta.refresh_from_db()
        self.assertEqual(carta.estado, "FINALIZADA")
        self.assertEqual(carta.derivada_a, "DISERCO")
        self.assertEqual(carta.fecha_cierre, date.today())

    def test_CP_CTA_011_resumen_por_estado_y_atrasadas(self):
        """CP-CTA-011: el resumen cuenta las cartas vigentes por estado y las atrasadas de su delegación."""
        antigua = date.today() - timedelta(days=30)
        self.carta(fecha_recepcion=antigua)
        self.carta(estado=CartaOficinaPartes.APROBADA)
        self.carta(estado=CartaOficinaPartes.NO_APLICA)
        self.carta(activo=False)
        self.carta(delegacion=self.mar, fecha_recepcion=antigua)

        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        resumen = {i["clave"]: i["total"] for i in respuesta.context["resumen"]}

        self.assertEqual(resumen, {"EN_PROCESO": 1, "APROBADA": 1, "FINALIZADA": 0, "NO_APLICA": 1})
        self.assertEqual(respuesta.context["total_vigentes"], 3)
        self.assertEqual(respuesta.context["total_atrasadas"], 1)

    def test_CP_CTA_012_busqueda_y_filtros(self):
        """CP-CTA-012: busca por remitente, tema o N° y filtra por estado, destinatario y atrasadas."""
        self.carta(remitente="CRUZ ROJA", tema="Limpieza de playas", numero_ingreso="10297")
        self.carta(remitente="EXPOSITORES DIAGUITAS", destinatario=CartaOficinaPartes.DELEGADO,
                   estado=CartaOficinaPartes.APROBADA)
        self.carta(remitente="CARTA ANTIGUA", fecha_recepcion=date.today() - timedelta(days=40))
        self.client.force_login(self.supervisor)
        url = reverse("oficina_partes:carta_lista")

        self.assertContains(self.client.get(url, {"q": "playas"}), "CRUZ ROJA")
        self.assertNotContains(self.client.get(url, {"q": "10297"}), "DIAGUITAS")
        respuesta = self.client.get(url, {"destinatario": "DELEGADO"})
        self.assertContains(respuesta, "DIAGUITAS")
        self.assertNotContains(respuesta, "CRUZ ROJA")
        respuesta = self.client.get(url, {"atrasadas": "1"})
        self.assertContains(respuesta, "CARTA ANTIGUA")
        self.assertNotContains(respuesta, "CRUZ ROJA")

    def test_CP_CTA_013_anular_y_reactivar(self):
        """CP-CTA-013: el Supervisor anula (baja lógica) y reactiva; el Administrativo no puede anular."""
        carta = self.carta()

        self.client.force_login(self.administrativo)
        self.assertEqual(self.client.post(reverse("oficina_partes:carta_cambiar_estado", args=[carta.pk])).status_code, 403)

        self.client.force_login(self.supervisor)
        self.client.post(reverse("oficina_partes:carta_cambiar_estado", args=[carta.pk]))
        carta.refresh_from_db()
        self.assertFalse(carta.activo)
        self.assertTrue(CartaOficinaPartes.objects.filter(pk=carta.pk).exists())

    def test_CP_CTA_014_sin_delegacion_no_registra(self):
        """CP-CTA-014 (borde): un usuario sin delegación no ve cartas ni puede registrar."""
        self.carta()
        self.client.force_login(self.sin_delegacion)

        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        self.assertContains(respuesta, "no tiene una delegación asignada")
        self.assertEqual(respuesta.context["total_vigentes"], 0)
        self.assertEqual(self.client.get(reverse("oficina_partes:carta_crear")).status_code, 403)

    def test_CP_CTA_015_requiere_sesion(self):
        """CP-CTA-015: sin sesión el tubo redirige al login."""
        respuesta = self.client.get(reverse("oficina_partes:carta_lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])
