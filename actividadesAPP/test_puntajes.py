
"""
SGR - EVA 3
Pruebas del puntaje individual R7.

Responsable: José Villalobos.
Casos CP-PUN-001 a CP-PUN-010.

Cada prueba incluye su descripción como docstring
para incorporarla a la matriz del informe.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from seguridadAPP.models import Cargo, PerfilUsuario
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo

from .models import RegistroActividad
from .puntajes import (
    calcular_meta_ajustada,
    calcular_cumplimiento_item,
    calcular_puntaje_ponderado,
    obtener_mi_matriz,
)


FECHA_PRUEBA = datetime(
    2026, 11, 11, 12, 0,
    tzinfo=ZoneInfo("America/Santiago"),
)


# ============================================================
# PRUEBAS UNITARIAS DE FÓRMULAS
# ============================================================

class PruebasFormulasPuntaje(SimpleTestCase):

    def test_CP_PUN_001_tope_120(self):
        """CP-PUN-001: un avance superior al 120% queda limitado a 120%."""

        resultado = calcular_cumplimiento_item(
            avance=30,
            meta_ajustada=20,
        )

        self.assertEqual(
            resultado,
            Decimal("120.00"),
        )

    def test_CP_PUN_002_meta_ajustada(self):
        """CP-PUN-002: una ausencia reduce proporcionalmente la meta."""

        resultado = calcular_meta_ajustada(
            objetivo=20,
            dias_periodo=20,
            dias_ausencia=5,
        )

        self.assertEqual(
            resultado,
            Decimal("15"),
        )

    def test_CP_PUN_003_ponderacion(self):
        """CP-PUN-003: el puntaje corresponde al cumplimiento ponderado."""

        resultado = calcular_puntaje_ponderado(
            cumplimiento=80,
            ponderacion=25,
        )

        self.assertEqual(
            resultado,
            Decimal("20.00"),
        )

    def test_CP_PUN_004_ponderacion_con_tope(self):
        """CP-PUN-004: una ponderación de 25% aporta como máximo 30 puntos."""

        resultado = calcular_puntaje_ponderado(
            cumplimiento=160,
            ponderacion=25,
        )

        self.assertEqual(
            resultado,
            Decimal("30.00"),
        )

    def test_CP_PUN_005_valores_invalidos(self):
        """CP-PUN-005: los valores negativos se rechazan."""

        with self.assertRaises(ValueError):
            calcular_cumplimiento_item(
                avance=-1,
                meta_ajustada=20,
            )

        with self.assertRaises(ValueError):
            calcular_meta_ajustada(
                objetivo=20,
                dias_periodo=10,
                dias_ausencia=11,
            )

        with self.assertRaises(ValueError):
            calcular_puntaje_ponderado(
                cumplimiento=80,
                ponderacion=-5,
            )


# ============================================================
# PRUEBAS DE INTEGRACIÓN CON LOS MODELOS
# ============================================================

@override_settings(MAX_INGRESOS_DIARIOS=7)
class PruebasMiMatriz(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cargo = Cargo.objects.create(
            nombre="Gestor Social Prueba",
        )

        usuario_modelo = get_user_model()

        cls.usuario = usuario_modelo.objects.create_user(
            username="funcionario_puntaje",
            password="ClaveTemporalPrueba2026!",
        )

        cls.otro_usuario = usuario_modelo.objects.create_user(
            username="otro_funcionario_puntaje",
            password="ClaveTemporalPrueba2026!",
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
            codigo="PER-PUN-2026",
            nombre="Período de pruebas",
            fecha_inicio=date(2026, 11, 9),
            fecha_fin=date(2026, 11, 13),
        )

        cls.actividad_a = CatalogoActividad.objects.create(
            codigo="PUN-EJ-A",
            nombre="Realización de taller",
            tipo_gestion="EJECUCION",
        )

        cls.actividad_b = CatalogoActividad.objects.create(
            codigo="PUN-EJ-B",
            nombre="Visita comunitaria",
            tipo_gestion="EJECUCION",
        )

        cls.preparatoria = CatalogoActividad.objects.create(
            codigo="PUN-PREP",
            nombre="Coordinación de taller",
            tipo_gestion="PREPARATORIA",
        )

        cls.meta_a = Meta.objects.create(
            codigo="PUN-META-A",
            nombre="Meta de talleres",
            periodo=cls.periodo,
            actividad=cls.actividad_a,
            cargo=cls.cargo,
            valor_objetivo=Decimal("2.00"),
            ponderacion=Decimal("60.00"),
        )

        cls.meta_b = Meta.objects.create(
            codigo="PUN-META-B",
            nombre="Meta de visitas",
            periodo=cls.periodo,
            actividad=cls.actividad_b,
            cargo=cls.cargo,
            valor_objetivo=Decimal("4.00"),
            ponderacion=Decimal("40.00"),
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
            "actividad": self.actividad_a,
            "fecha_actividad": date(2026, 11, 10),
            "solicitante_tipo": "VECINO",
            "nombre_usuario": "Vecino Prueba",
            "telefono_usuario": "912345678",
            "detalle": "Gestión realizada",
        }

        datos.update(cambios)

        return RegistroActividad.objects.create(
            **datos
        )

    def test_CP_PUN_006_matriz_individual(self):
        """CP-PUN-006: Mi matriz calcula las metas y el total ponderado."""

        for _ in range(3):
            self.registrar()

        for _ in range(2):
            self.registrar(
                actividad=self.actividad_b,
            )

        matriz = obtener_mi_matriz(
            self.funcionario,
            self.periodo,
        )

        items = {
            item["actividad"].pk: item
            for item in matriz["items"]
        }

        # Meta A: 3/2 = 150%, limitada al 120%.
        self.assertEqual(
            items[self.actividad_a.pk]["cumplimiento"],
            Decimal("120.00"),
        )

        # Meta B: 2/4 = 50%.
        self.assertEqual(
            items[self.actividad_b.pk]["cumplimiento"],
            Decimal("50.00"),
        )

        # A: 72 puntos. B: 20 puntos.
        self.assertEqual(
            matriz["puntaje_total"],
            Decimal("92.00"),
        )

    def test_CP_PUN_007_preparatoria_excluida(self):
        """CP-PUN-007: una actividad preparatoria no aumenta el avance."""

        self.registrar(
            actividad=self.preparatoria,
        )

        matriz = obtener_mi_matriz(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            matriz["puntaje_total"],
            Decimal("0.00"),
        )

    def test_CP_PUN_008_inactivos_excluidos(self):
        """CP-PUN-008: los registros inactivos no aportan al puntaje."""

        self.registrar(
            activo=False,
        )

        matriz = obtener_mi_matriz(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            matriz["puntaje_total"],
            Decimal("0.00"),
        )

    def test_CP_PUN_009_funcionarios_separados(self):
        """CP-PUN-009: las actividades de otro funcionario no se suman."""

        self.registrar(
            funcionario=self.otro_funcionario,
        )

        matriz = obtener_mi_matriz(
            self.funcionario,
            self.periodo,
        )

        self.assertEqual(
            matriz["puntaje_total"],
            Decimal("0.00"),
        )

    def test_CP_PUN_010_meta_con_ausencia(self):
        """CP-PUN-010: los días de ausencia reducen la meta ajustada."""

        self.registrar()
        self.registrar()

        matriz = obtener_mi_matriz(
            self.funcionario,
            self.periodo,
            dias_ausencia=1,
        )

        items = {
            item["actividad"].pk: item
            for item in matriz["items"]
        }

        # El período tiene 5 días hábiles.
        # Meta A: 2 * (5 - 1) / 5 = 1.6.
        self.assertEqual(
            items[self.actividad_a.pk]["objetivo_ajustado"],
            Decimal("1.60"),
        )

        self.assertEqual(
            items[self.actividad_a.pk]["cumplimiento"],
            Decimal("120.00"),
        )

        self.assertEqual(
            matriz["dias_ausencia"],
            1,
        )
