"""
Evaluación 3 - Catálogo por tipo de gestión (R5) y metas por cargo.
Responsable: Ignacio Figueroa.

Cada regla tiene casos normales y casos de borde. El ID de cada prueba
se usa en la matriz de resultado esperado vs. obtenido del informe.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.urls import reverse

from seguridadAPP.models import Cargo
from tubo_gestionAPP.validadores import (
    TIPO_GESTION_EJECUCION,
    TIPO_GESTION_PREPARATORIA,
    tipo_gestion_puntua,
    validar_suma_ponderaciones_por_cargo,
)

from .forms import CatalogoActividadForm, MetaForm, PeriodoForm
from .models import CatalogoActividad, Meta
from .test_reglas_y_mantenedores import Base


# ============================================================
# REGLAS PURAS (sin base de datos)
# ============================================================

class PruebasReglasPuras(SimpleTestCase):

    def test_CP_CAT_003_ejecucion_suma_puntaje(self):
        """CP-CAT-003: una actividad de Ejecución suma puntaje."""
        self.assertTrue(tipo_gestion_puntua(TIPO_GESTION_EJECUCION))

    def test_CP_CAT_004_preparatoria_no_suma_puntaje(self):
        """CP-CAT-004: una actividad Preparatoria no suma puntaje."""
        self.assertFalse(tipo_gestion_puntua(TIPO_GESTION_PREPARATORIA))

    def test_CP_CAT_005_tipo_desconocido_se_rechaza(self):
        """CP-CAT-005 (borde): un tipo que no existe no se interpreta."""
        for valor in ("", None, "ejecucion", "OTRO"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    tipo_gestion_puntua(valor)

    def test_CP_MET_003_todos_los_cargos_suman_100(self):
        """CP-MET-003: dos cargos que suman 100% cada uno se aceptan."""
        self.assertTrue(validar_suma_ponderaciones_por_cargo({
            "Apoyo Administrativo": [20, 30, 25, 20, 5],
            "Gestor Social": [20, 20, 25, 20, 5, 10],
        }))

    def test_CP_MET_004_un_cargo_incompleto_se_rechaza(self):
        """
        CP-MET-004: con un cargo al 85% (caso real de Planificación en
        la matriz Excel) el período no se puede cerrar, y el mensaje
        indica qué cargo falla.
        """
        with self.assertRaises(ValidationError) as ctx:
            validar_suma_ponderaciones_por_cargo({
                "Apoyo Administrativo": [20, 30, 25, 20, 5],
                "Planificación y Gestión": [15, 30, 5, 35],
            })

        mensaje = ctx.exception.messages[0]
        self.assertIn("Planificación y Gestión: 85%", mensaje)
        self.assertNotIn("Apoyo Administrativo", mensaje)

    def test_CP_MET_005_bordes_de_la_suma(self):
        """CP-MET-005 (borde): 99,99% y 100,01% se rechazan; 33,33+33,33+33,34 se acepta."""
        for ponderaciones in (
            [Decimal("99.99")],
            [Decimal("100.01")],
            [Decimal("50"), Decimal("50"), Decimal("0.01")],
        ):
            with self.subTest(ponderaciones=ponderaciones):
                with self.assertRaises(ValidationError):
                    validar_suma_ponderaciones_por_cargo({"Cargo": ponderaciones})

        self.assertTrue(validar_suma_ponderaciones_por_cargo({
            "Cargo": [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
        }))


# ============================================================
# CATÁLOGO: TIPO DE GESTIÓN (R5)
# ============================================================

class PruebasTipoGestion(Base):

    def datos_catalogo(self, **cambios):
        datos = {
            "codigo": "ACT-TALLER",
            "nombre": "Realización de taller",
            "descripcion": "",
            "area": "Organizaciones",
            "activo": True,
        }
        datos.update(cambios)
        return datos

    def test_CP_CAT_006_por_defecto_es_ejecucion(self):
        """CP-CAT-006: sin indicar tipo, la actividad queda como Ejecución (también las ya existentes)."""
        self.assertEqual(self.actividad.tipo_gestion, TIPO_GESTION_EJECUCION)
        self.assertTrue(self.actividad.puntua)

        form = CatalogoActividadForm(self.datos_catalogo())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().tipo_gestion, TIPO_GESTION_EJECUCION)

    def test_CP_CAT_007_registrar_preparatoria(self):
        """CP-CAT-007: "Coordinación de taller" se registra como Preparatoria y no puntúa."""
        form = CatalogoActividadForm(self.datos_catalogo(
            codigo="ACT-COORD",
            nombre="Coordinación de taller",
            tipo_gestion=TIPO_GESTION_PREPARATORIA,
        ))
        self.assertTrue(form.is_valid(), form.errors)

        actividad = form.save()
        self.assertEqual(actividad.tipo_gestion, TIPO_GESTION_PREPARATORIA)
        self.assertFalse(actividad.puntua)

    def test_CP_CAT_008_tipo_invalido_en_el_post(self):
        """CP-CAT-008 (borde): un tipo fuera de las opciones se rechaza."""
        form = CatalogoActividadForm(self.datos_catalogo(tipo_gestion="OTRO"))
        self.assertFalse(form.is_valid())
        self.assertIn("tipo_gestion", form.errors)

    def test_CP_CAT_009_cambiar_tipo_al_editar(self):
        """CP-CAT-009: editar una actividad de Ejecución a Preparatoria se guarda."""
        form = CatalogoActividadForm(
            self.datos_catalogo(
                codigo=self.actividad.codigo,
                nombre=self.actividad.nombre,
                tipo_gestion=TIPO_GESTION_PREPARATORIA,
            ),
            instance=self.actividad,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.tipo_gestion, TIPO_GESTION_PREPARATORIA)

    def test_CP_CAT_010_listado_filtra_y_muestra_tipo(self):
        """CP-CAT-010: el listado filtra por tipo, muestra la columna e ignora filtros inválidos."""
        CatalogoActividad.objects.create(
            codigo="ACT-COORD", nombre="Coordinación de taller",
            tipo_gestion=TIPO_GESTION_PREPARATORIA,
        )
        self.client.force_login(self.admin)
        url = reverse("sgr_maestros:catalogo_lista")

        respuesta = self.client.get(url, {"tipo": TIPO_GESTION_PREPARATORIA})
        codigos = [a.codigo for a in respuesta.context["actividades"]]
        self.assertEqual(codigos, ["ACT-COORD"])
        self.assertContains(respuesta, "Tipo de gestión")

        respuesta = self.client.get(url, {"tipo": TIPO_GESTION_EJECUCION})
        codigos = [a.codigo for a in respuesta.context["actividades"]]
        self.assertEqual(codigos, ["ACT-001"])

        # Borde: un valor desconocido no filtra ni rompe la página.
        respuesta = self.client.get(url, {"tipo": "<script>"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["actividades"]), 2)
        self.assertEqual(respuesta.context["tipo"], "")


# ============================================================
# METAS POR CARGO
# ============================================================

class PruebasMetasPorCargo(Base):

    def setUp(self):
        super().setUp()
        self.apoyo = Cargo.objects.create(nombre="Apoyo Administrativo")
        self.gestor = Cargo.objects.create(nombre="Gestor Social")

    def meta(self, codigo, ponderacion, cargo=None, activo=True):
        return Meta.objects.create(
            codigo=codigo, nombre=f"Meta {codigo}", periodo=self.periodo,
            actividad=self.actividad, valor_objetivo=Decimal("10"),
            ponderacion=Decimal(ponderacion), cargo=cargo, activo=activo,
        )

    def test_CP_MET_006_cada_cargo_tiene_su_propio_100(self):
        """CP-MET-006: dos cargos pueden tener 100% cada uno en el mismo período."""
        self.meta("AP-1", "100", cargo=self.apoyo)

        form = MetaForm(self.datos_meta(
            codigo="GS-1", ponderacion="100", cargo=self.gestor.pk,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_CP_MET_007_un_cargo_no_supera_el_100(self):
        """CP-MET-007: dentro de un cargo, superar el 100% se rechaza e indica el disponible."""
        self.meta("AP-1", "60", cargo=self.apoyo)
        self.meta("AP-2", "30", cargo=self.apoyo)

        form = MetaForm(self.datos_meta(
            codigo="AP-3", ponderacion="10.01", cargo=self.apoyo.pk,
        ))
        self.assertFalse(form.is_valid())
        error = str(form.errors["ponderacion"])
        self.assertIn("Apoyo Administrativo", error)
        self.assertIn("disponible: 10", error)

        # Borde: exactamente lo disponible sí se acepta.
        form = MetaForm(self.datos_meta(
            codigo="AP-3", ponderacion="10", cargo=self.apoyo.pk,
        ))
        self.assertTrue(form.is_valid(), form.errors)

    def test_CP_MET_008_metas_generales_y_por_cargo_son_independientes(self):
        """CP-MET-008: las metas sin cargo no consumen el 100% de un cargo, ni al revés."""
        self.meta("GEN-1", "100")
        self.meta("AP-1", "100", cargo=self.apoyo)

        self.assertEqual(self.periodo.suma_ponderaciones(cargo=None), 100)
        self.assertEqual(self.periodo.suma_ponderaciones(cargo=self.apoyo), 100)
        self.assertEqual(self.periodo.suma_ponderaciones(cargo=self.gestor), 0)

        form = MetaForm(self.datos_meta(codigo="GEN-2", ponderacion="1"))
        self.assertFalse(form.is_valid())

    def test_CP_MET_009_cambiar_el_cargo_valida_contra_el_nuevo(self):
        """CP-MET-009 (borde): mover una meta a un cargo que ya está al 100% se rechaza."""
        self.meta("GS-1", "100", cargo=self.gestor)
        meta = self.meta("AP-1", "40", cargo=self.apoyo)

        form = MetaForm(
            self.datos_meta(codigo="AP-1", ponderacion="40", cargo=self.gestor.pk),
            instance=meta,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Gestor Social", str(form.errors["ponderacion"]))

    def test_CP_MET_010_cierre_exige_100_en_cada_cargo(self):
        """CP-MET-010: el período cierra solo si cada cargo suma 100%; el error nombra el cargo."""
        self.meta("AP-1", "100", cargo=self.apoyo)
        self.meta("GS-1", "85", cargo=self.gestor)
        datos = {
            "codigo": "PER-2026", "nombre": "Período 2026",
            "fecha_inicio": "2026-01-01", "fecha_fin": "2026-12-31",
            "cerrado": True,
        }

        form = PeriodoForm(datos, instance=self.periodo)
        self.assertFalse(form.is_valid())
        self.assertIn("Gestor Social: 85", str(form.errors["cerrado"]))

        self.meta("GS-2", "15", cargo=self.gestor)
        form = PeriodoForm(datos, instance=self.periodo)
        self.assertTrue(form.is_valid(), form.errors)

    def test_CP_MET_011_cargo_inactivo(self):
        """CP-MET-011 (borde): no se asignan metas a cargos inactivos, pero al editar se conserva el cargo actual."""
        meta = self.meta("AP-1", "50", cargo=self.apoyo)
        self.apoyo.activo = False
        self.apoyo.save()

        form = MetaForm(self.datos_meta(
            codigo="AP-2", ponderacion="10", cargo=self.apoyo.pk,
        ))
        self.assertFalse(form.is_valid())
        self.assertIn("cargo", form.errors)

        form = MetaForm(
            self.datos_meta(codigo="AP-1", ponderacion="50", cargo=self.apoyo.pk),
            instance=meta,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_CP_MET_012_reactivar_respeta_el_tope_del_cargo(self):
        """CP-MET-012: reactivar una meta que dejaría su cargo sobre 100% se bloquea."""
        self.meta("AP-1", "80", cargo=self.apoyo)
        inactiva = self.meta("AP-2", "30", cargo=self.apoyo, activo=False)
        # Otro cargo con espacio no debe influir.
        self.meta("GS-1", "10", cargo=self.gestor)
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("sgr_maestros:meta_cambiar_estado", args=[inactiva.pk]),
            follow=True,
        )

        inactiva.refresh_from_db()
        self.assertFalse(inactiva.activo)
        self.assertContains(respuesta, "Apoyo Administrativo")
        self.assertContains(respuesta, "disponible: 20")

    def test_CP_MET_013_listado_filtra_por_cargo(self):
        """CP-MET-013: el listado filtra por cargo, por "sin cargo" e ignora ids inválidos."""
        self.meta("AP-1", "50", cargo=self.apoyo)
        self.meta("GS-1", "50", cargo=self.gestor)
        self.meta("GEN-1", "50")
        self.client.force_login(self.admin)
        url = reverse("sgr_maestros:meta_lista")

        def codigos(params):
            respuesta = self.client.get(url, params)
            self.assertEqual(respuesta.status_code, 200)
            return sorted(m.codigo for m in respuesta.context["metas"])

        self.assertEqual(codigos({"cargo": self.apoyo.pk}), ["AP-1"])
        self.assertEqual(codigos({"cargo": "sin"}), ["GEN-1"])
        self.assertEqual(codigos({"q": "gestor social"}), ["GS-1"])
        self.assertEqual(codigos({"cargo": "abc"}), ["AP-1", "GEN-1", "GS-1"])
        self.assertEqual(codigos({"cargo": "99999"}), [])

    def test_CP_MET_014_listado_de_periodos_por_cargo(self):
        """CP-MET-014: el listado de períodos muestra la suma de cada cargo."""
        self.meta("AP-1", "100", cargo=self.apoyo)
        self.meta("GS-1", "85", cargo=self.gestor)
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse("sgr_maestros:periodo_lista"))
        self.assertContains(respuesta, "Apoyo Administrativo: 100%")
        self.assertContains(respuesta, "Gestor Social: 85% de 100%")

    def test_CP_CAR_003_cargo_con_metas_no_se_elimina(self):
        """CP-CAR-003: un cargo con metas no se elimina físicamente (sin error 500)."""
        self.meta("AP-1", "50", cargo=self.apoyo)
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:cargo_eliminar", args=[self.apoyo.pk]),
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(Cargo.objects.filter(pk=self.apoyo.pk).exists())
        self.assertContains(respuesta, "funcionarios o metas")


class PruebasCargoLlamadoSinCargo(Base):
    """
    CP-MET-015 (borde): las metas se agrupan por cargo y no por nombre. Un
    cargo llamado "Sin cargo" no se mezcla con las metas generales.
    """

    def setUp(self):
        super().setUp()
        self.homonimo = Cargo.objects.create(nombre="Sin cargo")

    def meta(self, codigo, ponderacion, cargo=None):
        return Meta.objects.create(
            codigo=codigo, nombre=f"Meta {codigo}", periodo=self.periodo,
            actividad=self.actividad, valor_objetivo=Decimal("10"),
            ponderacion=Decimal(ponderacion), cargo=cargo,
        )

    def datos_cierre(self):
        return {
            "codigo": "PER-2026", "nombre": "Período 2026",
            "fecha_inicio": "2026-01-01", "fecha_fin": "2026-12-31",
            "cerrado": True,
        }

    def test_CP_MET_015_no_se_suma_con_las_metas_generales(self):
        self.meta("GEN-1", "30")
        self.meta("SC-1", "70", cargo=self.homonimo)

        grupos = self.periodo.ponderaciones_por_cargo()
        self.assertEqual(grupos["Sin cargo"], [Decimal("30.00")])
        self.assertEqual(grupos["Sin cargo (cargo)"], [Decimal("70.00")])

        # 30% + 70% NO es un 100%: son dos grupos distintos e incompletos.
        form = PeriodoForm(self.datos_cierre(), instance=self.periodo)
        self.assertFalse(form.is_valid())
        self.assertIn("Sin cargo: 30", str(form.errors["cerrado"]))

    def test_CP_MET_016_cada_grupo_completo_permite_cerrar(self):
        self.meta("GEN-1", "100")
        self.meta("SC-1", "100", cargo=self.homonimo)

        form = PeriodoForm(self.datos_cierre(), instance=self.periodo)
        self.assertTrue(form.is_valid(), form.errors)

    def test_CP_MET_017_solo_el_cargo_homonimo_no_es_meta_general(self):
        # Solo metas de un cargo (aunque se llame "Sin cargo"): se valida
        # por cargo y el listado lo muestra como cargo, no como general.
        self.meta("SC-1", "40", cargo=self.homonimo)

        resumen = self.periodo.resumen_ponderaciones_por_cargo()
        self.assertEqual(len(resumen), 1)
        self.assertFalse(resumen[0]["general"])

        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("sgr_maestros:periodo_lista"))
        self.assertContains(respuesta, "Sin cargo (cargo): 40% de 100%")
