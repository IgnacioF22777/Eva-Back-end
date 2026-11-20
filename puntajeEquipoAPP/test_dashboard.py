"""Pruebas Eva 3: dashboard de la delegación (CP-DSH-001 a CP-DSH-005)."""

from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from actividadesAPP.models import ZONA_CHILE, RegistroActividad
from delegacionesAPP.models import Delegacion
from seguridadAPP.models import Cargo, PerfilUsuario
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo

User = get_user_model()
AHORA = datetime(2026, 11, 9, 12, 0, tzinfo=ZONA_CHILE)


def delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre, direccion="Calle", encargado="Delegado",
        email=f"{nombre.lower()}@laserena.cl", telefono="512111111", celular="911111111",
    )


def funcionario(username, rut, perfil, deleg, cargo=None):
    usuario = User.objects.create_user(username, password="Clave-Segura-2026", first_name=username.capitalize())
    usuario.groups.add(Group.objects.get(name=perfil))
    PerfilUsuario.objects.create(usuario=usuario, rut=rut, delegacion=deleg, cargo=cargo)
    return usuario


class PruebasDashboard(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = delegacion("Centro")
        cls.antena = delegacion("Antena")
        cargo = Cargo.objects.create(nombre="Gestor Social")
        cls.delegada = funcionario("delegada", "11111111-1", "Supervisor", cls.centro)
        cls.ana = funcionario("ana", "12345678-5", "Administrativo", cls.centro, cargo)
        cls.luis = funcionario("luis", "44444444-4", "Administrativo", cls.antena, cargo)
        cls.periodo = Periodo.objects.create(
            codigo="2026-T4", nombre="T4", fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 12, 31),
        )
        visita = CatalogoActividad.objects.create(codigo="VIS", nombre="Visita")
        Meta.objects.create(codigo="M", nombre="Visitas", periodo=cls.periodo, actividad=visita,
                            cargo=cargo, valor_objetivo=10, ponderacion=100)
        cls.visita = visita

    def setUp(self):
        reloj = patch("django.utils.timezone.now", return_value=AHORA)
        reloj.start()
        self.addCleanup(reloj.stop)

    def registrar(self, usuario, **cambios):
        datos = dict(funcionario=usuario.perfil, actividad=self.visita, fecha_actividad=date(2026, 11, 9),
                     nombre_usuario="Vecina", telefono_usuario="912345678")
        datos.update(cambios)
        return RegistroActividad.objects.create(**datos)

    def test_CP_DSH_001_acceso_por_perfil(self):
        """CP-DSH-001 (permisos): sin sesión → login; Administrativo → 403; delegada → 200."""
        url = reverse("puntaje_equipo:dashboard")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.delegada)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_CP_DSH_002_indicadores_y_graficos(self):
        """CP-DSH-002: muestra registros, aprobados, pendientes y los gráficos."""
        aprobado = self.registrar(self.ana)
        self.registrar(self.ana, ingresa_tubo=True, estado_tubo="SOLUCIONADO")
        aprobado.verificar(self.delegada, RegistroActividad.APROBADA)

        self.client.force_login(self.delegada)
        respuesta = self.client.get(reverse("puntaje_equipo:dashboard"))
        kpi = respuesta.context["kpi"]
        self.assertEqual((kpi["registros"], kpi["aprobados"], kpi["pendientes"]), (2, 1, 1))
        self.assertEqual(respuesta.context["tubo"]["soluciones"], 100.0)
        self.assertContains(respuesta, "conic-gradient")
        self.assertContains(respuesta, "Cumplimiento por funcionario")

    def test_CP_DSH_003_supervisor_no_cambia_de_delegacion(self):
        """CP-DSH-003 (ámbito): la delegada no ve otra delegación cambiando la URL."""
        self.registrar(self.luis)
        self.client.force_login(self.delegada)
        respuesta = self.client.get(reverse("puntaje_equipo:dashboard"), {"delegacion": self.antena.pk})
        self.assertEqual(respuesta.context["delegacion"], self.centro)
        self.assertEqual(respuesta.context["kpi"]["registros"], 0)

    def test_CP_DSH_004_filtros_funcionario_y_fechas(self):
        """CP-DSH-004: filtros por funcionario y rango de fechas."""
        self.registrar(self.ana, fecha_actividad=date(2026, 11, 2))
        self.registrar(self.ana)
        self.client.force_login(self.delegada)
        url = reverse("puntaje_equipo:dashboard")
        respuesta = self.client.get(url, {"desde": "2026-11-05", "hasta": "2026-11-09"})
        self.assertEqual(respuesta.context["kpi"]["registros"], 1)
        respuesta = self.client.get(url, {"funcionario": self.delegada.perfil.pk})
        self.assertEqual(respuesta.context["kpi"]["registros"], 0)

    def test_CP_DSH_005_tendencia_semanal(self):
        """CP-DSH-005: la tendencia agrupa por semana (lunes a domingo)."""
        self.registrar(self.ana, fecha_actividad=date(2026, 11, 2))
        self.registrar(self.ana, fecha_actividad=date(2026, 11, 3))
        self.registrar(self.ana)
        self.client.force_login(self.delegada)
        tendencia = self.client.get(reverse("puntaje_equipo:dashboard")).context["tendencia"]
        por_semana = {c["lunes"]: c["total"] for c in tendencia}
        self.assertEqual(por_semana[date(2026, 11, 2)], 2)
        self.assertEqual(por_semana[date(2026, 11, 9)], 1)
