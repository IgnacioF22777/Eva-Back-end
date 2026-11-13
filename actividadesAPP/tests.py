
"""Pruebas EVA 3 de actividades R1-R5.

Responsable: José Villalobos.
Los ID CP-ACT permiten registrar los resultados
esperados y obtenidos en el informe.
"""

from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario
from sgr_maestrosAPP.models import CatalogoActividad

from .models import RegistroActividad, ZONA_CHILE


# Fechas fijas para evitar depender del día actual.
LUNES = datetime(
    2026, 11, 9, 12, 0, tzinfo=ZONA_CHILE
)
MARTES = datetime(
    2026, 11, 10, 12, 0, tzinfo=ZONA_CHILE
)
VIERNES_ANTERIOR = date(2026, 11, 6)


@override_settings(MAX_INGRESOS_DIARIOS=7)
class PruebasRegistroActividad(TestCase):
    """Casos normales, de borde y de seguridad."""

    @classmethod
    def setUpTestData(cls):
        cls.delegacion = Delegacion.objects.create(
            nombre="Centro",
            direccion="Dirección de prueba",
            encargado="Delegado Centro",
            email="delegado@example.com",
            telefono="512345678",
            celular="987654321",
        )

        User = get_user_model()

        cls.usuario = User.objects.create_user(
            username="jose_prueba",
            password="ClavePrueba#2026",
        )

        cls.otro_usuario = User.objects.create_user(
            username="otro_prueba",
            password="ClavePrueba#2026",
        )

        cls.sin_permiso = User.objects.create_user(
            username="sin_permiso",
            password="ClavePrueba#2026",
        )

        cls.funcionario = PerfilUsuario.objects.create(
            usuario=cls.usuario,
            rut="12345678-5",
            delegacion=cls.delegacion,
        )

        cls.otro_funcionario = PerfilUsuario.objects.create(
            usuario=cls.otro_usuario,
            rut="22222222-2",
            delegacion=cls.delegacion,
        )

        cls.ejecucion = CatalogoActividad.objects.create(
            codigo="ACT-PRUEBA-EJ",
            nombre="Realización de taller",
            tipo_gestion="EJECUCION",
        )

        cls.preparatoria = CatalogoActividad.objects.create(
            codigo="ACT-PRUEBA-PR",
            nombre="Coordinación de taller",
            tipo_gestion="PREPARATORIA",
        )

        tipo = ContentType.objects.get_for_model(
            RegistroActividad
        )

        permisos = [
            Permission.objects.get(
                content_type=tipo,
                codename=f"{accion}_registroactividad",
            )
            for accion in (
                "view",
                "add",
                "change",
                "delete",
            )
        ]

        cls.usuario.user_permissions.add(*permisos)
        cls.otro_usuario.user_permissions.add(*permisos)

    def setUp(self):
        reloj = patch(
            "actividadesAPP.models.timezone.now",
            return_value=LUNES,
        )
        reloj.start()
        self.addCleanup(reloj.stop)

    def crear_registro(self, **cambios):
        datos = {
            "funcionario": self.funcionario,
            "actividad": self.ejecucion,
            "fecha_actividad": date(2026, 11, 9),
            "solicitante_tipo": "VECINO",
            "nombre_usuario": "Vecina de prueba",
            "telefono_usuario": "912345678",
            "detalle": "Atención realizada",
        }
        datos.update(cambios)

        return RegistroActividad.objects.create(**datos)

    def datos_formulario(self, **cambios):
        datos = {
            "actividad": self.ejecucion.pk,
            "fecha_actividad": "2026-11-09",
            "solicitante_tipo": "VECINO",
            "nombre_usuario": "Vecina de prueba",
            "telefono_usuario": "912345678",
            "detalle": "Atención realizada",
        }
        datos.update(cambios)
        return datos

    # =====================================================
    # CP-ACT-001 - DELEGADO NO GENERA PUNTAJE
    # =====================================================

    def test_CP_ACT_001_delegado_no_puntua(self):
        casos = (
            {"solicitante_tipo": "DELEGADO"},
            {"nombre_usuario": " delegado CENTRO "},
            {"telefono_usuario": "+56 9 8765 4321"},
        )

        for cambios in casos:
            with self.subTest(cambios=cambios):
                registro = self.crear_registro(**cambios)

                self.assertFalse(registro.puntua)
                self.assertIn(
                    "delegado",
                    registro.motivo_sin_puntaje.lower(),
                )

    # =====================================================
    # CP-ACT-002 - CONTACTO INCOMPLETO
    # =====================================================

    def test_CP_ACT_002_sin_contacto_no_puntua(self):
        casos = (
            {"nombre_usuario": ""},
            {"telefono_usuario": ""},
            {"telefono_usuario": "123"},
        )

        for cambios in casos:
            with self.subTest(cambios=cambios):
                registro = self.crear_registro(**cambios)

                self.assertFalse(registro.puntua)
                self.assertIn(
                    "teléfono",
                    registro.motivo_sin_puntaje,
                )

    # =====================================================
    # CP-ACT-003 - SEPTIMO INGRESO ACEPTADO
    # =====================================================

    def test_CP_ACT_003_septimo_ingreso_aceptado(self):
        for _ in range(7):
            self.crear_registro()

        total = RegistroActividad.objects.filter(
            activo=True
        ).count()

        self.assertEqual(total, 7)

    # =====================================================
    # CP-ACT-004 - OCTAVO INGRESO RECHAZADO
    # =====================================================

    def test_CP_ACT_004_octavo_ingreso_rechazado(self):
        for _ in range(7):
            self.crear_registro()

        with self.assertRaisesMessage(
            ValidationError,
            "7 actividades",
        ):
            self.crear_registro()

        self.assertEqual(
            RegistroActividad.objects.count(),
            7,
        )

    # =====================================================
    # CP-ACT-005 - LUNES PERMITIDO
    # =====================================================

    def test_CP_ACT_005_lunes_aceptado(self):
        registro = self.crear_registro(
            fecha_actividad=VIERNES_ANTERIOR
        )

        self.assertTrue(registro.puntua)

    # =====================================================
    # CP-ACT-006 - MARTES RECHAZADO
    # =====================================================

    def test_CP_ACT_006_martes_rechazado(self):
        with patch(
            "actividadesAPP.models.timezone.now",
            return_value=MARTES,
        ):
            with self.assertRaisesMessage(
                ValidationError,
                "cerrada",
            ):
                self.crear_registro(
                    fecha_actividad=VIERNES_ANTERIOR
                )

        self.assertEqual(
            RegistroActividad.objects.count(),
            0,
        )

    # =====================================================
    # CP-ACT-007 - FECHA FUTURA
    # =====================================================

    def test_CP_ACT_007_fecha_futura_rechazada(self):
        with self.assertRaisesMessage(
            ValidationError,
            "fecha futura",
        ):
            self.crear_registro(
                fecha_actividad=date(2026, 11, 10)
            )

        self.assertEqual(
            RegistroActividad.objects.count(),
            0,
        )

    # =====================================================
    # CP-ACT-008 - ACTIVIDAD PREPARATORIA
    # =====================================================

    def test_CP_ACT_008_preparatoria_no_puntua(self):
        registro = self.crear_registro(
            actividad=self.preparatoria
        )

        self.assertFalse(registro.puntua)

        self.assertIn(
            "preparatoria",
            registro.motivo_sin_puntaje.lower(),
        )

    # =====================================================
    # CP-ACT-009 - EJECUCION CON CONTACTO COMPLETO
    # =====================================================

    def test_CP_ACT_009_ejecucion_si_puntua(self):
        registro = self.crear_registro()

        self.assertTrue(registro.puntua)
        self.assertEqual(
            registro.motivo_sin_puntaje,
            "",
        )

    # =====================================================
    # CP-ACT-010 - NO MANIPULAR PUNTAJE DESDE POST
    # =====================================================

    def test_CP_ACT_010_post_protegido(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("actividades:crear"),
            self.datos_formulario(
                telefono_usuario="",
                puntua="true",
                funcionario=str(
                    self.otro_funcionario.pk
                ),
                fecha_ingreso="2000-01-01T00:00:00Z",
            ),
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        registro = RegistroActividad.objects.get()

        self.assertFalse(registro.puntua)
        self.assertEqual(
            registro.funcionario_id,
            self.funcionario.pk,
        )
        self.assertEqual(
            registro.fecha_ingreso.date(),
            LUNES.date(),
        )

    # =====================================================
    # CP-ACT-011 - OCTAVO INGRESO DESDE FORMULARIO
    # =====================================================

    def test_CP_ACT_011_octavo_post_muestra_error(self):
        for _ in range(7):
            self.crear_registro()

        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("actividades:crear"),
            self.datos_formulario(),
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.assertContains(
            respuesta,
            "7 actividades",
        )

        self.assertEqual(
            RegistroActividad.objects.count(),
            7,
        )

    # =====================================================
    # CP-ACT-012 - CUPOS INDEPENDIENTES
    # =====================================================

    def test_CP_ACT_012_cupos_por_funcionario(self):
        for _ in range(7):
            self.crear_registro()

        otro = self.crear_registro(
            funcionario=self.otro_funcionario
        )

        self.assertEqual(
            otro.funcionario_id,
            self.otro_funcionario.pk,
        )

        self.assertEqual(
            RegistroActividad.objects.count(),
            8,
        )

    # =====================================================
    # CP-ACT-013 - EDICION FUERA DE PLAZO
    # =====================================================

    def test_CP_ACT_013_edicion_cerrada(self):
        registro = self.crear_registro(
            fecha_actividad=VIERNES_ANTERIOR
        )

        with patch(
            "actividadesAPP.models.timezone.now",
            return_value=MARTES,
        ):
            registro.detalle = "Cambio fuera de plazo"

            with self.assertRaisesMessage(
                ValidationError,
                "cerrada",
            ):
                registro.save(
                    update_fields=["detalle"]
                )

        registro.refresh_from_db()

        self.assertEqual(
            registro.detalle,
            "Atención realizada",
        )

    # =====================================================
    # CP-ACT-014 - AMBITO DEL FUNCIONARIO
    # =====================================================

    def test_CP_ACT_014_no_ver_registros_ajenos(self):
        registro = self.crear_registro()

        self.client.force_login(self.otro_usuario)

        respuesta = self.client.get(
            reverse("actividades:lista")
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        ids = [
            r.pk
            for r in respuesta.context["registros"]
        ]

        self.assertNotIn(
            registro.pk,
            ids,
        )

        respuesta = self.client.get(
            reverse(
                "actividades:editar",
                args=[registro.pk],
            )
        )

        self.assertEqual(
            respuesta.status_code,
            404,
        )

    # =====================================================
    # CP-ACT-015 - BAJA LOGICA
    # =====================================================

    def test_CP_ACT_015_baja_logica(self):
        registro = self.crear_registro()

        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse(
                "actividades:cambiar_estado",
                args=[registro.pk],
            )
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        registro.refresh_from_db()

        self.assertFalse(registro.activo)
        self.assertFalse(registro.puntua)

        self.assertEqual(
            RegistroActividad.objects.count(),
            1,
        )

    # =====================================================
    # CP-ACT-016 - BAJA SOLO MEDIANTE POST
    # =====================================================

    def test_CP_ACT_016_solo_post(self):
        registro = self.crear_registro()

        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse(
                "actividades:cambiar_estado",
                args=[registro.pk],
            )
        )

        self.assertEqual(
            respuesta.status_code,
            405,
        )

        registro.refresh_from_db()

        self.assertTrue(registro.activo)

    # =====================================================
    # CP-ACT-017 - SEGURIDAD DE ACCESO
    # =====================================================

    def test_CP_ACT_017_permisos(self):
        url = reverse("actividades:lista")

        # Sin sesión: redirige al login.
        respuesta = self.client.get(url)

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        # Usuario sin permiso: 403.
        self.client.force_login(self.sin_permiso)

        respuesta = self.client.get(url)

        self.assertEqual(
            respuesta.status_code,
            403,
        )

    # =====================================================
    # CP-ACT-018 - TELEFONO CON PREFIJO CHILENO
    # =====================================================

    def test_CP_ACT_018_telefono_chileno(self):
        registro = self.crear_registro(
            telefono_usuario="+56 9 1234 5678"
        )

        self.assertTrue(registro.puntua)
