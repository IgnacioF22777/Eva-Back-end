from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from seguridadAPP.models import Cargo, PerfilUsuario
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .feriados import domingo_de_resurreccion, feriados_entre
from .forms import DetallePeriodoForm, MetaForm, PeriodoForm
from .models import CatalogoActividad, DetallePeriodo, Meta, Periodo
from .tests import crear_usuario


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", ADMINISTRADOR
        )
        cls.supervisor = crear_usuario(
            "12.345.678-5", "supervisor@laserena.cl", SUPERVISOR
        )
        cls.actividad = CatalogoActividad.objects.create(
            codigo="ACT-001", nombre="Aseo y ornato"
        )

    def setUp(self):
        self.periodo = Periodo.objects.create(
            codigo="PER-2026",
            nombre="Período 2026",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )

    def crear_meta(self, codigo, ponderacion, activo=True, periodo=None):
        return Meta.objects.create(
            codigo=codigo,
            nombre=f"Meta {codigo}",
            periodo=periodo or self.periodo,
            actividad=self.actividad,
            valor_objetivo=Decimal("10"),
            ponderacion=Decimal(ponderacion),
            activo=activo,
        )

    def datos_meta(self, **cambios):
        datos = {
            "codigo": "META-NUEVA",
            "nombre": "Meta nueva",
            "periodo": self.periodo.pk,
            "actividad": self.actividad.pk,
            "valor_objetivo": "10",
            "ponderacion": "30",
            "activo": True,
        }
        datos.update(cambios)
        return datos


# ============================================================
# PONDERACIONES (validar_suma_ponderaciones, CP-MET-001/002)
# ============================================================

class PruebasPonderaciones(Base):

    def test_las_metas_activas_no_superan_el_100(self):
        self.crear_meta("M1", "60")
        self.crear_meta("M2", "30")

        form = MetaForm(self.datos_meta(ponderacion="20"))
        self.assertFalse(form.is_valid())
        self.assertIn("disponible: 10", str(form.errors["ponderacion"]))

        self.assertTrue(MetaForm(self.datos_meta(ponderacion="10")).is_valid())

    def test_las_metas_inactivas_no_cuentan(self):
        self.crear_meta("M1", "90", activo=False)

        self.assertTrue(MetaForm(self.datos_meta(ponderacion="100")).is_valid())

    def test_editar_una_meta_no_se_cuenta_a_si_misma(self):
        meta = self.crear_meta("M1", "60")
        self.crear_meta("M2", "40")

        datos = self.datos_meta(codigo="M1", ponderacion="60")
        self.assertTrue(MetaForm(datos, instance=meta).is_valid())

        datos = self.datos_meta(codigo="M1", ponderacion="61")
        self.assertFalse(MetaForm(datos, instance=meta).is_valid())

    def test_el_modelo_tambien_aplica_el_tope(self):
        self.crear_meta("M1", "80")
        meta = Meta(
            codigo="M2", nombre="Meta M2", periodo=self.periodo,
            actividad=self.actividad, valor_objetivo=Decimal("1"),
            ponderacion=Decimal("30"),
        )

        with self.assertRaises(ValidationError):
            meta.full_clean()

    def test_reactivar_meta_respeta_el_tope(self):
        self.crear_meta("M1", "80")
        inactiva = self.crear_meta("M2", "30", activo=False)
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("sgr_maestros:meta_cambiar_estado", args=[inactiva.pk]),
            follow=True,
        )

        inactiva.refresh_from_db()
        self.assertFalse(inactiva.activo)
        self.assertContains(respuesta, "superaría el 100%")

    def test_no_se_cierra_un_periodo_que_no_suma_100(self):
        self.crear_meta("M1", "60")
        self.crear_meta("M2", "30")

        form = PeriodoForm({
            "codigo": "PER-2026", "nombre": "Período 2026",
            "fecha_inicio": "2026-01-01", "fecha_fin": "2026-12-31",
            "cerrado": True,
        }, instance=self.periodo)

        self.assertFalse(form.is_valid())
        self.assertIn("suman 90", str(form.errors["cerrado"]))

        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.cerrado)

    def test_se_cierra_un_periodo_que_suma_100(self):
        self.crear_meta("M1", "60")
        self.crear_meta("M2", "40")
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("sgr_maestros:periodo_editar", args=[self.periodo.pk]),
            {
                "codigo": "PER-2026", "nombre": "Período 2026",
                "fecha_inicio": "2026-01-01", "fecha_fin": "2026-12-31",
                "cerrado": "on",
            },
        )

        self.assertRedirects(respuesta, reverse("sgr_maestros:periodo_lista"))
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.cerrado)

    def test_listado_muestra_la_suma_de_ponderaciones(self):
        self.crear_meta("M1", "60")
        self.crear_meta("M2", "15")
        self.crear_meta("M3", "20", activo=False)
        DetallePeriodo.objects.create(
            periodo=self.periodo, nombre="Semestre 1",
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 6, 30),
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse("sgr_maestros:periodo_lista"))
        periodo = respuesta.context["periodos"].get(pk=self.periodo.pk)

        # La subconsulta no se multiplica por los detalles del período.
        self.assertEqual(periodo.suma_ponderaciones, Decimal("75"))
        self.assertContains(respuesta, "75% de 100%")


# ============================================================
# DÍAS COMPUTABLES (calcular_dias_computables, CP-PER-003)
# ============================================================

class PruebasDiasComputables(Base):

    def test_pascua_y_feriados(self):
        self.assertEqual(domingo_de_resurreccion(2026), date(2026, 4, 5))
        self.assertEqual(
            feriados_entre(date(2026, 4, 1), date(2026, 4, 30)),
            [date(2026, 4, 3), date(2026, 4, 4)],
        )

    def test_descuenta_fines_de_semana_y_fiestas_patrias(self):
        # Lunes 14 a domingo 20 de septiembre de 2026: 5 días hábiles,
        # menos el viernes 18 (feriado) = 4.
        detalle = DetallePeriodo.objects.create(
            periodo=self.periodo, nombre="Semana 38",
            fecha_inicio=date(2026, 9, 14), fecha_fin=date(2026, 9, 20),
        )
        self.assertEqual(detalle.dias_computables, 4)

    def test_descuenta_viernes_santo(self):
        # Lunes 30 de marzo a domingo 5 de abril de 2026: 5 hábiles menos
        # el Viernes Santo (3 de abril) = 4.
        detalle = DetallePeriodo.objects.create(
            periodo=self.periodo, nombre="Semana Santa",
            fecha_inicio=date(2026, 3, 30), fecha_fin=date(2026, 4, 5),
        )
        self.assertEqual(detalle.dias_computables, 4)

    def test_el_valor_no_se_escribe_a_mano(self):
        self.assertNotIn("dias_computables", DetallePeriodoForm().fields)

        self.client.force_login(self.admin)
        self.client.post(
            reverse("sgr_maestros:detalle_periodo_crear"),
            {
                "periodo": self.periodo.pk, "nombre": "Enero",
                "fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31",
                "dias_computables": 999,
            },
        )

        detalle = DetallePeriodo.objects.get(nombre="Enero")
        # Enero 2026: 22 días hábiles menos el 1 de enero = 21.
        self.assertEqual(detalle.dias_computables, 21)

    def test_se_recalcula_al_cambiar_las_fechas(self):
        detalle = DetallePeriodo.objects.create(
            periodo=self.periodo, nombre="Tramo",
            fecha_inicio=date(2026, 9, 14), fecha_fin=date(2026, 9, 20),
        )
        detalle.fecha_fin = date(2026, 9, 16)
        detalle.save(update_fields=["fecha_fin"])

        detalle.refresh_from_db()
        self.assertEqual(detalle.dias_computables, 3)


# ============================================================
# MANTENEDOR DE PERÍODOS: BÚSQUEDA Y ELIMINACIÓN
# ============================================================

class PruebasMantenedorPeriodos(Base):

    def test_busqueda_y_filtro_por_estado(self):
        Periodo.objects.create(
            codigo="PER-2025", nombre="Evaluación 2025", cerrado=True,
            fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31),
        )
        self.client.force_login(self.admin)
        url = reverse("sgr_maestros:periodo_lista")

        respuesta = self.client.get(url, {"q": "2025"})
        self.assertContains(respuesta, "PER-2025")
        self.assertNotContains(respuesta, "PER-2026")

        respuesta = self.client.get(url, {"estado": "abiertos"})
        self.assertContains(respuesta, "PER-2026")
        self.assertNotContains(respuesta, "PER-2025")

    def test_elimina_periodo_sin_dependencias(self):
        self.client.force_login(self.admin)
        url = reverse("sgr_maestros:periodo_eliminar", args=[self.periodo.pk])

        self.assertContains(self.client.get(url), "PER-2026")
        self.assertTrue(Periodo.objects.filter(pk=self.periodo.pk).exists())

        respuesta = self.client.post(url)
        self.assertRedirects(respuesta, reverse("sgr_maestros:periodo_lista"))
        self.assertFalse(Periodo.objects.filter(pk=self.periodo.pk).exists())

    def test_no_elimina_periodo_con_metas_o_detalles(self):
        self.crear_meta("M1", "50")
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("sgr_maestros:periodo_eliminar", args=[self.periodo.pk]),
            follow=True,
        )

        self.assertTrue(Periodo.objects.filter(pk=self.periodo.pk).exists())
        self.assertContains(respuesta, "no puede eliminarse")

    def test_supervisor_no_elimina_periodos(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("sgr_maestros:periodo_eliminar", args=[self.periodo.pk])
        )
        self.assertEqual(respuesta.status_code, 403)


# ============================================================
# MANTENEDOR DE CARGOS (CP-CAR-001/002)
# ============================================================

class PruebasMantenedorCargos(Base):

    def test_crear_buscar_y_editar(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:cargo_crear"),
            {"nombre": "  Encargado   territorial ", "activo": "on"},
        )
        self.assertRedirects(respuesta, reverse("seguridad:cargo_lista"))

        cargo = Cargo.objects.get()
        self.assertEqual(cargo.nombre, "Encargado territorial")

        Cargo.objects.create(nombre="Director de obras")
        respuesta = self.client.get(
            reverse("seguridad:cargo_lista"), {"q": "territorial"}
        )
        self.assertContains(respuesta, "Encargado territorial")
        self.assertNotContains(respuesta, "Director de obras")

        self.client.post(
            reverse("seguridad:cargo_editar", args=[cargo.pk]),
            {"nombre": "Coordinador territorial", "activo": "on"},
        )
        cargo.refresh_from_db()
        self.assertEqual(cargo.nombre, "Coordinador territorial")

    def test_no_duplica_nombres(self):
        Cargo.objects.create(nombre="Encargado territorial")
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:cargo_crear"),
            {"nombre": "ENCARGADO TERRITORIAL", "activo": "on"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Cargo.objects.count(), 1)

    def test_elimina_cargo_sin_funcionarios(self):
        cargo = Cargo.objects.create(nombre="Cargo libre")
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:cargo_eliminar", args=[cargo.pk])
        )
        self.assertRedirects(respuesta, reverse("seguridad:cargo_lista"))
        self.assertFalse(Cargo.objects.filter(pk=cargo.pk).exists())

    def test_no_elimina_cargo_con_funcionarios(self):
        cargo = Cargo.objects.create(nombre="Cargo ocupado")
        perfil = PerfilUsuario.objects.get(usuario=self.supervisor)
        perfil.cargo = cargo
        perfil.save()
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:cargo_eliminar", args=[cargo.pk]), follow=True
        )
        self.assertTrue(Cargo.objects.filter(pk=cargo.pk).exists())
        self.assertContains(respuesta, "funcionarios asociados")

    def test_baja_logica_y_reactivacion(self):
        cargo = Cargo.objects.create(nombre="Cargo temporal")
        self.client.force_login(self.admin)
        url = reverse("seguridad:cargo_cambiar_estado", args=[cargo.pk])

        self.client.post(url)
        cargo.refresh_from_db()
        self.assertFalse(cargo.activo)

        self.client.post(url)
        cargo.refresh_from_db()
        self.assertTrue(cargo.activo)

    def test_cargo_inactivo_no_se_ofrece_a_usuarios_nuevos(self):
        activo = Cargo.objects.create(nombre="Cargo vigente")
        inactivo = Cargo.objects.create(nombre="Cargo antiguo", activo=False)
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse("seguridad:usuario_crear"))
        cargos = respuesta.context["form"].fields["cargo"].queryset

        self.assertIn(activo, cargos)
        self.assertNotIn(inactivo, cargos)

    def test_solo_el_administrador_gestiona_cargos(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(reverse("seguridad:cargo_lista"))
        self.assertEqual(respuesta.status_code, 403)

        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("seguridad:cargo_lista"))
        self.assertEqual(respuesta.status_code, 200)
