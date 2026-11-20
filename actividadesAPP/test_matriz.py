
"""
Pruebas de acceso, permisos y visualización de la matriz.

Casos CP-MAT-001 a CP-MAT-008.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse

from seguridadAPP.models import Cargo, PerfilUsuario
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo

from .models import RegistroActividad


FECHA_PRUEBA = datetime(
    2026, 11, 11, 12, 0,
    tzinfo=ZoneInfo("America/Santiago"),
)


@override_settings(MAX_INGRESOS_DIARIOS=7)
class PruebasVistaMatriz(TestCase):

    @classmethod
    def setUpTestData(cls):

        modelo_usuario = get_user_model()

        cls.cargo = Cargo.objects.create(
            nombre="Cargo de prueba matriz",
        )

        cls.usuario = modelo_usuario.objects.create_user(
            username="matriz_funcionario",
            password="ClaveTemporalPruebas2026!",
        )

        cls.otro_usuario = modelo_usuario.objects.create_user(
            username="matriz_otro_funcionario",
            password="ClaveTemporalPruebas2026!",
        )

        cls.sin_permiso = modelo_usuario.objects.create_user(
            username="matriz_sin_permiso",
            password="ClaveTemporalPruebas2026!",
        )

        cls.sin_perfil = modelo_usuario.objects.create_user(
            username="matriz_sin_perfil",
            password="ClaveTemporalPruebas2026!",
        )

        cls.funcionario = PerfilUsuario.objects.create(
            usuario=cls.usuario,
            rut="12345678-5",
            cargo=cls.cargo,
        )

        cls.otro_funcionario = PerfilUsuario.objects.create(
            usuario=cls.otro_usuario,
            rut="22222222-2",
            cargo=cls.cargo,
        )

        cls.periodo = Periodo.objects.create(
            codigo="PER-MATRIZ-2026",
            nombre="Periodo de prueba matriz",
            fecha_inicio=date(2026, 11, 9),
            fecha_fin=date(2026, 11, 15),
        )

        cls.actividad = CatalogoActividad.objects.create(
            codigo="MAT-EJ-001",
            nombre="Actividad de prueba matriz",
            tipo_gestion="EJECUCION",
        )

        cls.meta = Meta.objects.create(
            codigo="MAT-META-001",
            nombre="Meta de prueba matriz",
            periodo=cls.periodo,
            actividad=cls.actividad,
            cargo=cls.cargo,
            valor_objetivo=Decimal("2.00"),
            ponderacion=Decimal("100.00"),
        )

        tipo = ContentType.objects.get_for_model(
            RegistroActividad
        )

        permiso = Permission.objects.get(
            content_type=tipo,
            codename="view_registroactividad",
        )

        cls.usuario.user_permissions.add(permiso)
        cls.otro_usuario.user_permissions.add(permiso)
        cls.sin_perfil.user_permissions.add(permiso)

    def setUp(self):

        reloj = patch(
            "actividadesAPP.models.timezone.now",
            return_value=FECHA_PRUEBA,
        )

        reloj.start()
        self.addCleanup(reloj.stop)

        self.url = reverse("actividades:matriz")

    def registrar(self, funcionario=None):

        if funcionario is None:
            funcionario = self.funcionario

        return RegistroActividad.objects.create(
            funcionario=funcionario,
            actividad=self.actividad,
            fecha_actividad=date(2026, 11, 10),
            solicitante_tipo="VECINO",
            nombre_usuario="Vecino de prueba",
            telefono_usuario="912345678",
            detalle="Actividad realizada",
        )

    def test_CP_MAT_001_requiere_sesion(self):
        """CP-MAT-001: un visitante sin sesión es redirigido."""

        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.status_code,
            302,
        )

    def test_CP_MAT_002_requiere_permiso(self):
        """CP-MAT-002: un usuario sin permiso recibe HTTP 403."""

        self.client.force_login(self.sin_permiso)

        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.status_code,
            403,
        )

    def test_CP_MAT_003_requiere_perfil(self):
        """CP-MAT-003: un usuario sin perfil de funcionario recibe HTTP 403."""

        self.client.force_login(self.sin_perfil)

        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.status_code,
            403,
        )

    def test_CP_MAT_004_muestra_matriz(self):
        """CP-MAT-004: un funcionario autorizado puede consultar su matriz."""

        self.registrar()

        self.client.force_login(self.usuario)

        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.assertTemplateUsed(
            respuesta,
            "actividades/matriz.html",
        )

        matriz = respuesta.context["matriz"]
        resumen = respuesta.context["resumen"]

        self.assertEqual(
            matriz["funcionario"].pk,
            self.funcionario.pk,
        )

        self.assertEqual(
            matriz["items"][0]["avance"],
            1,
        )

        self.assertEqual(
            matriz["puntaje_total"],
            Decimal("50.00"),
        )

        self.assertEqual(
            resumen["total_ingresos"],
            1,
        )

    def test_CP_MAT_005_no_muestra_registros_ajenos(self):
        """CP-MAT-005: la matriz no suma ingresos de otros funcionarios."""

        self.registrar(
            funcionario=self.otro_funcionario,
        )

        self.client.force_login(self.usuario)

        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.assertEqual(
            respuesta.context["matriz"]["puntaje_total"],
            Decimal("0.00"),
        )

        self.assertEqual(
            respuesta.context["resumen"]["total_ingresos"],
            0,
        )

    def test_CP_MAT_006_periodo_valido(self):
        """CP-MAT-006: permite seleccionar un período existente."""

        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            self.url,
            {"periodo": str(self.periodo.pk)},
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.assertEqual(
            respuesta.context["periodo"].pk,
            self.periodo.pk,
        )

    def test_CP_MAT_007_periodo_invalido(self):
        """CP-MAT-007: rechaza identificadores de período incorrectos."""

        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            self.url,
            {"periodo": "invalido"},
        )

        self.assertEqual(
            respuesta.status_code,
            404,
        )

    def test_CP_MAT_008_no_permite_elegir_funcionario(self):
        """CP-MAT-008: un parámetro de URL no permite consultar a otro funcionario."""

        self.registrar(
            funcionario=self.otro_funcionario,
        )

        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            self.url,
            {
                "periodo": str(self.periodo.pk),
                "funcionario": str(
                    self.otro_funcionario.pk
                ),
            },
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.assertEqual(
            respuesta.context["funcionario"].pk,
            self.funcionario.pk,
        )

        self.assertEqual(
            respuesta.context["matriz"]["puntaje_total"],
            Decimal("0.00"),
        )

        self.assertEqual(
            respuesta.context["resumen"]["total_ingresos"],
            0,
        )
