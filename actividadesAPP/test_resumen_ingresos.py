
"""
SGR - EVA 3
Pruebas del resumen de ingresos.

Responsable: José Villalobos.
Casos CP-RES-001 a CP-RES-011.

Cada caso tiene su descripción como docstring
para incorporarla a la matriz de pruebas del informe.
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)

from seguridadAPP.models import PerfilUsuario
from sgr_maestrosAPP.models import CatalogoActividad

from .models import RegistroActividad
from .resumen_ingresos import (
    calcular_promedio_diario,
    obtener_resumen_ingresos,
)


ZONA_CHILE = ZoneInfo("America/Santiago")

FECHA_PRUEBA = datetime(
    2026, 11, 11, 12, 0,
    tzinfo=ZONA_CHILE,
)


# ============================================================
# PRUEBAS DE LA FÓRMULA
# ============================================================

class PruebasPromedioDiario(SimpleTestCase):

    def test_CP_RES_001_promedio_diario(self):
        """CP-RES-001: calcula y redondea el promedio diario."""

        self.assertEqual(
            calcular_promedio_diario(5, 2),
            Decimal("2.50"),
        )

        self.assertEqual(
            calcular_promedio_diario(1, 3),
            Decimal("0.33"),
        )

    def test_CP_RES_002_sin_dias_computables(self):
        """CP-RES-002: devuelve cero si no hay días computables."""

        resultado = calcular_promedio_diario(
            total_ingresos=5,
            dias_computables=0,
        )

        self.assertEqual(
            resultado,
            Decimal("0.00"),
        )

    def test_CP_RES_003_valores_negativos(self):
        """CP-RES-003: rechaza totales y días negativos."""

        with self.assertRaises(ValueError):
            calcular_promedio_diario(-1, 5)

        with self.assertRaises(ValueError):
            calcular_promedio_diario(5, -1)


# ============================================================
# PRUEBAS DE INTEGRACIÓN
# ============================================================

@override_settings(MAX_INGRESOS_DIARIOS=7)
class PruebasResumenIngresos(TestCase):

    @classmethod
    def setUpTestData(cls):

        modelo_usuario = get_user_model()

        cls.usuario = modelo_usuario.objects.create_user(
            username="resumen_funcionario",
            password="ClaveTemporalPruebas2026!",
        )

        cls.otro_usuario = modelo_usuario.objects.create_user(
            username="resumen_otro_funcionario",
            password="ClaveTemporalPruebas2026!",
        )

        cls.funcionario = PerfilUsuario.objects.create(
            usuario=cls.usuario,
            rut="12345678-5",
        )

        cls.otro_funcionario = PerfilUsuario.objects.create(
            usuario=cls.otro_usuario,
            rut="22222222-2",
        )

        cls.actividad = CatalogoActividad.objects.create(
            codigo="RES-EJECUCION",
            nombre="Actividad de ejecución",
            tipo_gestion="EJECUCION",
        )

        cls.preparatoria = CatalogoActividad.objects.create(
            codigo="RES-PREPARATORIA",
            nombre="Actividad preparatoria",
            tipo_gestion="PREPARATORIA",
        )

        cls.periodo = SimpleNamespace(
            fecha_inicio=date(2026, 11, 9),
            fecha_fin=date(2026, 11, 15),
        )

    def setUp(self):

        reloj = patch(
            "actividadesAPP.models.timezone.now",
            return_value=FECHA_PRUEBA,
        )

        reloj.start()
        self.addCleanup(reloj.stop)

    def registrar(self, **cambios):

        datos = {
            "funcionario": self.funcionario,
            "actividad": self.actividad,
            "fecha_actividad": date(2026, 11, 10),
            "solicitante_tipo": "VECINO",
            "nombre_usuario": "Vecino de prueba",
            "telefono_usuario": "912345678",
            "detalle": "Actividad registrada",
        }

        datos.update(cambios)

        return RegistroActividad.objects.create(
            **datos
        )

    def test_CP_RES_004_contadores(self):
        """CP-RES-004: cuenta ingresos con y sin puntaje."""

        self.registrar()

        self.registrar(
            actividad=self.preparatoria,
        )

        ultimo = self.registrar(
            solicitante_tipo="DELEGADO",
        )

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            resumen["total_ingresos"],
            3,
        )

        self.assertEqual(
            resumen["ingresos_con_puntaje"],
            1,
        )

        self.assertEqual(
            resumen["ingresos_sin_puntaje"],
            2,
        )

        self.assertEqual(
            resumen["promedio_diario"],
            Decimal("1.00"),
        )

        self.assertEqual(
            resumen["ultimo_ingreso"].pk,
            ultimo.pk,
        )

    def test_CP_RES_005_baja_logica(self):
        """CP-RES-005: un registro inactivo no suma al resumen."""

        self.registrar()

        inactivo = self.registrar(
            activo=False,
        )

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            resumen["total_ingresos"],
            1,
        )

        self.assertEqual(
            resumen["ingresos_hoy"],
            1,
        )

        self.assertNotEqual(
            resumen["ultimo_ingreso"].pk,
            inactivo.pk,
        )

    def test_CP_RES_006_ambito_funcionario(self):
        """CP-RES-006: no mezcla ingresos de funcionarios diferentes."""

        self.registrar()

        self.registrar(
            funcionario=self.otro_funcionario,
        )

        self.registrar(
            funcionario=self.otro_funcionario,
        )

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            resumen["total_ingresos"],
            1,
        )

        self.assertEqual(
            resumen["ingresos_hoy"],
            1,
        )

    def test_CP_RES_007_cupos_diarios(self):
        """CP-RES-007: calcula siete cupos usados y cero disponibles."""

        for _ in range(7):
            self.registrar()

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            resumen["ingresos_hoy"],
            7,
        )

        self.assertEqual(
            resumen["limite_diario"],
            7,
        )

        self.assertEqual(
            resumen["disponibles_hoy"],
            0,
        )

    def test_CP_RES_008_limite_periodo(self):
        """CP-RES-008: excluye ingresos posteriores al fin del período."""

        registro_dentro = self.registrar()

        # Se ajusta únicamente la marca temporal del fixture.
        # No modifica la lógica del modelo de producción.
        RegistroActividad.objects.filter(
            pk=registro_dentro.pk,
        ).update(
            fecha_ingreso=datetime(
                2026, 11, 10, 23, 59,
                tzinfo=ZONA_CHILE,
            )
        )

        registro_fuera = self.registrar()

        periodo_corto = SimpleNamespace(
            fecha_inicio=date(2026, 11, 9),
            fecha_fin=date(2026, 11, 10),
        )

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            periodo_corto,
        )

        self.assertEqual(
            resumen["total_ingresos"],
            1,
        )

        self.assertEqual(
            resumen["ultimo_ingreso_periodo"].pk,
            registro_dentro.pk,
        )

        self.assertEqual(
            resumen["ultimo_ingreso"].pk,
            registro_fuera.pk,
        )

    def test_CP_RES_009_semana_actual(self):
        """CP-RES-009: sin período usa la semana actual de Chile."""

        self.registrar()

        resumen = obtener_resumen_ingresos(
            self.funcionario,
        )

        self.assertEqual(
            resumen["fecha_inicio"],
            date(2026, 11, 9),
        )

        self.assertEqual(
            resumen["fecha_fin"],
            date(2026, 11, 15),
        )

        self.assertEqual(
            resumen["fecha_corte"],
            date(2026, 11, 11),
        )

        self.assertEqual(
            resumen["dias_computables"],
            3,
        )

        self.assertEqual(
            resumen["promedio_diario"],
            Decimal("0.33"),
        )

    def test_CP_RES_010_periodo_futuro(self):
        """CP-RES-010: un período futuro aún no tiene días transcurridos."""

        futuro = SimpleNamespace(
            fecha_inicio=date(2026, 11, 16),
            fecha_fin=date(2026, 11, 20),
        )

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            futuro,
        )

        self.assertEqual(
            resumen["dias_computables"],
            0,
        )

        self.assertEqual(
            resumen["total_ingresos"],
            0,
        )

        self.assertEqual(
            resumen["promedio_diario"],
            Decimal("0.00"),
        )

    def test_CP_RES_011_feriados(self):
        """CP-RES-011: excluye feriados y fines de semana del promedio."""

        periodo_feriado = SimpleNamespace(
            fecha_inicio=date(2026, 4, 30),
            fecha_fin=date(2026, 5, 2),
        )

        resumen = obtener_resumen_ingresos(
            self.funcionario,
            periodo_feriado,
            fecha_referencia=date(2026, 5, 2),
        )

        # 30 abril: jueves hábil.
        # 1 mayo: feriado.
        # 2 mayo: sábado.
        self.assertEqual(
            resumen["dias_computables"],
            1,
        )
