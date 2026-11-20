"""
SGR - EVA 3
Pruebas de la pantalla de puntaje del equipo (R10).

Responsable: Ignacio Figueroa.
Casos CP-PEQ-001 a CP-PEQ-015 (normales y de borde). Cada prueba lleva su
descripción como docstring para la matriz de resultado esperado vs.
obtenido del informe.

Período de prueba: lunes 09-11-2026 a viernes 13-11-2026 (5 días hábiles).
«Hoy» se fija en el miércoles 11-11-2026: van 3 de 5 días, así que el
objetivo al día es 60 %.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from actividadesAPP.models import RegistroActividad
from actividadesAPP.puntajes import obtener_mi_matriz
from delegacionesAPP.models import Delegacion
from seguridadAPP.models import Cargo, PerfilUsuario
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo
from tubo_gestionAPP.tests import CLAVE

from .calculo import (
    NARANJO,
    ROJO,
    SIN_METAS,
    VERDE,
    calcular_objetivo_al_dia,
    calcular_resumen_equipo,
    calcular_semaforo,
)


HOY = datetime(2026, 11, 11, 12, 0, tzinfo=ZoneInfo("America/Santiago"))
URL = reverse("puntaje_equipo:equipo")


def rut_valido(numero):
    """RUT con su dígito verificador (módulo 11)."""
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    dv = {11: "0", 10: "K"}.get(resto, str(resto))
    return f"{numero}-{dv}"


# ============================================================
# FÓRMULAS (SIN BASE DE DATOS)
# ============================================================

class PruebasFormulasEquipo(SimpleTestCase):

    def test_CP_PEQ_001_objetivo_al_dia(self):
        """CP-PEQ-001: con 3 de 5 días hábiles transcurridos el objetivo al día es 60 %."""
        self.assertEqual(calcular_objetivo_al_dia(3, 5), Decimal("60.00"))
        self.assertEqual(calcular_objetivo_al_dia(5, 5), Decimal("100.00"))

    def test_CP_PEQ_002_objetivo_bordes(self):
        """CP-PEQ-002: antes del inicio es 0 %, después del término no pasa de 100 % y un período sin días hábiles da 0 %."""
        self.assertEqual(calcular_objetivo_al_dia(0, 5), Decimal("0.00"))
        self.assertEqual(calcular_objetivo_al_dia(9, 5), Decimal("100.00"))
        self.assertEqual(calcular_objetivo_al_dia(0, 0), Decimal("0.00"))

    def test_CP_PEQ_003_objetivo_con_ausencias(self):
        """CP-PEQ-003: las ausencias descuentan días (3 − 1 de 5 = 40 %) y nunca dejan el objetivo bajo 0 %."""
        self.assertEqual(calcular_objetivo_al_dia(3, 5, dias_ausencia=1), Decimal("40.00"))
        self.assertEqual(calcular_objetivo_al_dia(2, 5, dias_ausencia=4), Decimal("0.00"))
        with self.assertRaises(ValueError):
            calcular_objetivo_al_dia(-1, 5)

    def test_CP_PEQ_004_semaforo_limites(self):
        """CP-PEQ-004: verde si alcanza el objetivo; naranjo desde el 60 % del objetivo; rojo bajo eso."""
        self.assertEqual(calcular_semaforo(60, 60), VERDE)
        self.assertEqual(calcular_semaforo(120, 60), VERDE)
        self.assertEqual(calcular_semaforo(Decimal("59.99"), 60), NARANJO)
        self.assertEqual(calcular_semaforo(36, 60), NARANJO)
        self.assertEqual(calcular_semaforo(Decimal("35.99"), 60), ROJO)
        self.assertEqual(calcular_semaforo(0, 0), VERDE)
        with self.assertRaises(ValueError):
            calcular_semaforo(-1, 60)


# ============================================================
# DATOS COMUNES
# ============================================================

class BaseEquipo(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro", direccion="Dir", encargado="Delegado Centro",
            email="centro@laserena.cl", telefono="512000001", celular="912000001",
        )
        cls.pampa = Delegacion.objects.create(
            nombre="Delegación La Pampa", direccion="Dir", encargado="Delegado Pampa",
            email="pampa@laserena.cl", telefono="512000002", celular="912000002",
        )

        cls.cargo = Cargo.objects.create(nombre="Gestor Social Equipo")
        cls.cargo_incompleto = Cargo.objects.create(nombre="Cargo con metas incompletas")

        cls.periodo = Periodo.objects.create(
            codigo="PER-PEQ-2026", nombre="Semana de prueba",
            fecha_inicio=date(2026, 11, 9), fecha_fin=date(2026, 11, 13),
        )

        cls.taller = CatalogoActividad.objects.create(
            codigo="PEQ-TALLER", nombre="Taller", tipo_gestion="EJECUCION",
        )
        cls.visita = CatalogoActividad.objects.create(
            codigo="PEQ-VISITA", nombre="Visita", tipo_gestion="EJECUCION",
        )

        Meta.objects.create(
            codigo="PEQ-M1", nombre="Talleres", periodo=cls.periodo, actividad=cls.taller,
            cargo=cls.cargo, valor_objetivo=Decimal("2.00"), ponderacion=Decimal("60.00"),
        )
        Meta.objects.create(
            codigo="PEQ-M2", nombre="Visitas", periodo=cls.periodo, actividad=cls.visita,
            cargo=cls.cargo, valor_objetivo=Decimal("4.00"), ponderacion=Decimal("40.00"),
        )
        Meta.objects.create(
            codigo="PEQ-M3", nombre="Talleres (incompleta)", periodo=cls.periodo, actividad=cls.taller,
            cargo=cls.cargo_incompleto, valor_objetivo=Decimal("2.00"), ponderacion=Decimal("60.00"),
        )

        cls.numero = 15000000
        cls.ana = cls.crear("ana", "Ana", "Alfa", ADMINISTRATIVO, cls.centro, cls.cargo)
        cls.beto = cls.crear("beto", "Beto", "Beta", ADMINISTRATIVO, cls.centro, cls.cargo)
        cls.carla = cls.crear("carla", "Carla", "Sin Cargo", ADMINISTRATIVO, cls.centro, None)
        cls.delegado = cls.crear("delegado", "Delia", "Delegada", SUPERVISOR, cls.centro, None)
        cls.pedro = cls.crear("pedro", "Pedro", "Pampa", ADMINISTRATIVO, cls.pampa, cls.cargo)
        cls.admin = cls.crear("admin", "Adela", "Admin", ADMINISTRADOR, None, None)

    @classmethod
    def crear(cls, usuario, nombre, apellido, rol, delegacion, cargo):
        from django.contrib.auth import get_user_model

        cls.numero += 1
        user = get_user_model().objects.create_user(
            username=usuario, first_name=nombre, last_name=apellido, password=CLAVE,
        )
        user.groups.add(Group.objects.get(name=rol))
        return PerfilUsuario.objects.create(
            usuario=user, rut=rut_valido(cls.numero), delegacion=delegacion, cargo=cargo,
        )

    def setUp(self):
        reloj = patch("django.utils.timezone.now", return_value=HOY)
        reloj.start()
        self.addCleanup(reloj.stop)

    def registrar(self, funcionario, actividad, veces=1):
        for _ in range(veces):
            RegistroActividad.objects.create(
                funcionario=funcionario, actividad=actividad,
                fecha_actividad=date(2026, 11, 10), solicitante_tipo="VECINO",
                nombre_usuario="Vecina de prueba", telefono_usuario="987654321",
            )

    def cargar_actividades(self):
        # Ana: talleres 2/2 = 100 % (60 pts) y visitas 2/4 = 50 % (20 pts) -> 80.
        self.registrar(self.ana, self.taller, 2)
        self.registrar(self.ana, self.visita, 2)
        # Beto: talleres 1/2 = 50 % (30 pts) y visitas 2/4 = 50 % (20 pts) -> 50.
        self.registrar(self.beto, self.taller, 1)
        self.registrar(self.beto, self.visita, 2)

    def equipo_centro(self):
        return PerfilUsuario.objects.filter(
            delegacion=self.centro, usuario__is_active=True,
        ).select_related("usuario", "cargo")

    def ver(self, perfil, **parametros):
        self.client.force_login(perfil.usuario)
        return self.client.get(URL, parametros)


# ============================================================
# CÁLCULO DEL EQUIPO
# ============================================================

class PruebasResumenEquipo(BaseEquipo):

    def test_CP_PEQ_005_puntaje_igual_a_mi_matriz(self):
        """CP-PEQ-005: el puntaje de cada fila es exactamente el de «Mi matriz» del funcionario."""
        self.cargar_actividades()
        resumen = calcular_resumen_equipo(self.equipo_centro(), self.periodo, HOY.date())
        filas = {fila.funcionario.pk: fila for fila in resumen.filas}

        for perfil in (self.ana, self.beto):
            esperado = obtener_mi_matriz(perfil, self.periodo)["puntaje_total"]
            self.assertEqual(filas[perfil.pk].puntaje, esperado)

        self.assertEqual(filas[self.ana.pk].puntaje, Decimal("80.00"))
        self.assertEqual(filas[self.beto.pk].puntaje, Decimal("50.00"))

    def test_CP_PEQ_006_semaforo_y_orden(self):
        """CP-PEQ-006: con objetivo 60 %, 80 pts es verde y 50 pts naranjo; el equipo se ordena de mayor a menor y los sin metas van al final."""
        self.cargar_actividades()
        resumen = calcular_resumen_equipo(self.equipo_centro(), self.periodo, HOY.date())

        self.assertEqual(resumen.objetivo, Decimal("60.00"))
        self.assertEqual(
            [fila.funcionario.pk for fila in resumen.filas[:2]],
            [self.ana.pk, self.beto.pk],
        )
        self.assertEqual(resumen.filas[0].semaforo, VERDE)
        self.assertEqual(resumen.filas[1].semaforo, NARANJO)
        self.assertTrue(all(fila.semaforo == SIN_METAS for fila in resumen.filas[2:]))

    def test_CP_PEQ_007_promedio_sin_contar_sin_metas(self):
        """CP-PEQ-007: el promedio del equipo solo considera a quienes tienen metas: (80 + 50) / 2 = 65 %, verde."""
        self.cargar_actividades()
        resumen = calcular_resumen_equipo(self.equipo_centro(), self.periodo, HOY.date())

        self.assertEqual(resumen.puntaje_promedio, Decimal("65.00"))
        self.assertEqual(resumen.semaforo, VERDE)
        conteo = {item["clave"]: item["total"] for item in resumen.conteo_semaforo}
        self.assertEqual(conteo, {VERDE: 1, NARANJO: 1, ROJO: 0, SIN_METAS: 2})

    def test_CP_PEQ_008_ingresos_del_equipo(self):
        """CP-PEQ-008: suma los ingresos del período (7) y los ingresos diarios de la delegación (4/3 + 3/3 = 2,33)."""
        self.cargar_actividades()
        resumen = calcular_resumen_equipo(self.equipo_centro(), self.periodo, HOY.date())

        self.assertEqual(resumen.total_ingresos, 7)
        self.assertEqual(resumen.ingresos_diarios, Decimal("2.33"))

    def test_CP_PEQ_009_ultimo_ingreso(self):
        """CP-PEQ-009: muestra el último ingreso y los días transcurridos; sin ingresos queda vacío."""
        self.registrar(self.ana, self.taller)
        RegistroActividad.objects.filter(funcionario=self.ana).update(
            fecha_ingreso=datetime(2026, 11, 2, 10, 0, tzinfo=ZoneInfo("America/Santiago")),
        )
        resumen = calcular_resumen_equipo(self.equipo_centro(), self.periodo, HOY.date())
        filas = {fila.funcionario.pk: fila for fila in resumen.filas}

        self.assertEqual(filas[self.ana.pk].dias_sin_ingresar, 9)
        self.assertIsNone(filas[self.beto.pk].ultimo_ingreso)
        self.assertIsNone(filas[self.beto.pk].dias_sin_ingresar)

    def test_CP_PEQ_010_equipo_sin_metas_y_ponderacion_incompleta(self):
        """CP-PEQ-010: un equipo sin metas queda «Sin metas» con promedio 0 y se avisa cuando las ponderaciones del cargo no suman 100 %."""
        resumen = calcular_resumen_equipo(
            PerfilUsuario.objects.filter(pk=self.carla.pk), self.periodo, HOY.date(),
        )
        self.assertEqual(resumen.semaforo, SIN_METAS)
        self.assertEqual(resumen.puntaje_promedio, Decimal("0.00"))

        self.beto.cargo = self.cargo_incompleto
        self.beto.save()
        resumen = calcular_resumen_equipo(
            PerfilUsuario.objects.filter(pk=self.beto.pk), self.periodo, HOY.date(),
        )
        self.assertTrue(resumen.filas[0].ponderacion_incompleta)
        self.assertEqual(resumen.filas[0].ponderacion_total, Decimal("60.00"))


# ============================================================
# PANTALLA, PERMISOS Y ÁMBITO
# ============================================================

class PruebasPantallaEquipo(BaseEquipo):

    def test_CP_PEQ_011_supervisor_ve_su_equipo(self):
        """CP-PEQ-011: el delegado (Supervisor) ve a los funcionarios de su delegación con su puntaje y semáforo."""
        self.cargar_actividades()
        respuesta = self.ver(self.delegado)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ana Alfa")
        self.assertContains(respuesta, "80,00%")
        self.assertEqual(
            [fila.semaforo for fila in respuesta.context["resumen"].filas[:2]],
            [VERDE, NARANJO],
        )
        self.assertNotContains(respuesta, "Pedro Pampa")

    def test_CP_PEQ_012_supervisor_no_cambia_de_delegacion(self):
        """CP-PEQ-012: un Supervisor que cambia ?delegacion= en la URL sigue viendo solo su delegación."""
        respuesta = self.ver(self.delegado, delegacion=self.pampa.pk)

        self.assertEqual(respuesta.context["delegacion"], self.centro)
        self.assertNotContains(respuesta, "Pedro Pampa")
        self.assertIsNone(respuesta.context["delegaciones"])

    def test_CP_PEQ_013_administrador_elige_delegacion(self):
        """CP-PEQ-013: el Administrador puede consultar cualquier delegación."""
        respuesta = self.ver(self.admin, delegacion=self.pampa.pk)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pedro Pampa")
        self.assertNotContains(respuesta, "Ana Alfa")

    def test_CP_PEQ_014_accesos_denegados(self):
        """CP-PEQ-014: el Administrativo y el Supervisor sin delegación reciben 403; sin sesión se pide iniciar sesión; parámetros inválidos dan 404."""
        self.assertEqual(self.ver(self.ana).status_code, 403)

        self.delegado.delegacion = None
        self.delegado.save()
        self.assertEqual(self.ver(self.delegado).status_code, 403)

        self.client.logout()
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("login", respuesta.url)

        self.assertEqual(self.ver(self.admin, periodo="abc").status_code, 404)
        self.assertEqual(self.ver(self.admin, delegacion="9999").status_code, 404)

    def test_CP_PEQ_015_inactivos_y_menu(self):
        """CP-PEQ-015: los funcionarios desactivados no aparecen y el enlace del menú solo se muestra a Administrador y Supervisor."""
        self.beto.usuario.is_active = False
        self.beto.usuario.save()

        respuesta = self.ver(self.delegado)
        self.assertNotContains(respuesta, "Beto Beta")
        self.assertContains(respuesta, "Puntaje del Equipo")

        self.client.force_login(self.ana.usuario)
        inicio = self.client.get(reverse("seguridad:panel"), follow=True)
        self.assertEqual(inicio.status_code, 200)
        self.assertNotContains(inicio, "Puntaje del Equipo")
