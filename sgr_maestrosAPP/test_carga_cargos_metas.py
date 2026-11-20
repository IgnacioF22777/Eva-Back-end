"""
Evaluación 3 - Carga de los 8 cargos del descriptor y sus metas reales.
Responsable: Ignacio Figueroa.

Cada prueba tiene un ID CP-CGO-xxx para la matriz de resultado esperado
vs. obtenido del informe. Se incluyen casos normales y de borde.
"""

import json
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from seguridadAPP.models import Cargo
from tubo_gestionAPP.validadores import TIPO_GESTION_PREPARATORIA

from .forms import PeriodoForm
from .management.commands.cargar_cargos_metas import ARCHIVO_POR_DEFECTO
from .models import CatalogoActividad, Meta, Periodo


def cargar(*argumentos):
    salida = StringIO()
    call_command("cargar_cargos_metas", *argumentos, stdout=salida)
    return salida.getvalue()


SUMAS_ESPERADAS = {
    "Apoyo Administrativo": Decimal("100"),
    "Coordinador de Servicios Comunitarios": Decimal("100"),
    "Gestión y Planificación": Decimal("85"),
    "Gestor Social": Decimal("100"),
    "Gestor de Seguridad": Decimal("100"),
    "Territorial OO.CC. (Organizaciones Comunitarias)": Decimal("100"),
}


class PruebasCargaCargosMetas(TestCase):

    def periodo(self):
        return Periodo.objects.get(codigo="2026-T3")

    # --- CASOS NORMALES ---
    def test_CP_CGO_001_carga_los_8_cargos_y_sus_metas(self):
        """CP-CGO-001: la carga crea 8 cargos, 28 actividades, el período y 37 metas con las sumas de la matriz."""
        cargar()

        self.assertEqual(Cargo.objects.count(), 8)
        self.assertEqual(CatalogoActividad.objects.count(), 28)
        self.assertEqual(Meta.objects.filter(activo=True).count(), 37)

        periodo = self.periodo()
        self.assertEqual(periodo.fecha_inicio, date(2026, 7, 1))
        self.assertEqual(periodo.fecha_fin, date(2026, 9, 30))

        sumas = {
            nombre: sum(ponderaciones)
            for nombre, ponderaciones in periodo.ponderaciones_por_cargo().items()
        }
        self.assertEqual(sumas, SUMAS_ESPERADAS)

    def test_CP_CGO_002_correrla_dos_veces_no_duplica(self):
        """CP-CGO-002: la segunda carga no crea ni modifica nada e informa «sin cambios»."""
        cargar()
        salida = cargar()

        self.assertEqual(Cargo.objects.count(), 8)
        self.assertEqual(CatalogoActividad.objects.count(), 28)
        self.assertEqual(Meta.objects.count(), 37)
        self.assertEqual(Periodo.objects.count(), 1)
        self.assertIn("Metas: 0 creados, 0 actualizados, 37 sin cambios", salida)
        self.assertIn("Cargos: 0 creados, 0 actualizados, 8 sin cambios", salida)

    def test_CP_CGO_003_simulacion_no_guarda_nada(self):
        """CP-CGO-003: con --dry-run se informa el resultado pero la base queda vacía."""
        salida = cargar("--dry-run")

        self.assertIn("SIMULACIÓN", salida)
        self.assertIn("Metas: 37 creados", salida)
        self.assertFalse(Cargo.objects.exists())
        self.assertFalse(Meta.objects.exists())
        self.assertFalse(Periodo.objects.exists())

    def test_CP_CGO_004_actividades_compartidas_no_se_duplican(self):
        """CP-CGO-004: «Emergencia» es una sola actividad usada por los 5 cargos que la tienen."""
        cargar()

        emergencia = CatalogoActividad.objects.get(codigo="SGR-EMERGENCIA")
        self.assertEqual(emergencia.metas.count(), 5)
        self.assertEqual(CatalogoActividad.objects.filter(nombre="Emergencia").count(), 1)

    def test_CP_CGO_005_metas_automaticas(self):
        """CP-CGO-005: las 2 metas automáticas quedan con su valor y explicación."""
        cargar()

        emergencia = Meta.objects.filter(actividad__codigo="SGR-EMERGENCIA").first()
        self.assertEqual(emergencia.valor_objetivo, Decimal("1"))
        self.assertIn("igual al avance", emergencia.actividad.descripcion)

        for meta in Meta.objects.filter(actividad__codigo="SGR-SOLUCIONES-TUBO"):
            self.assertEqual(meta.valor_objetivo, Decimal("0.80"))

    def test_CP_CGO_006_avisos_de_la_matriz(self):
        """CP-CGO-006: informa los cargos sin metas, el 85 % de Planificación y las diferencias por persona."""
        salida = cargar()

        self.assertIn("Delegado no tiene metas", salida)
        self.assertIn("Gestor de Compras y Proyectos no tiene metas", salida)
        self.assertIn("Gestión y Planificación suman 85%", salida)
        self.assertIn("G SOC5", salida)
        self.assertIn("T OC 3", salida)

    def test_CP_CGO_007_el_periodo_cargado_no_cierra_por_el_85(self):
        """CP-CGO-007: con los datos reales, el período no se puede cerrar y el error nombra a Planificación."""
        cargar()
        periodo = self.periodo()

        form = PeriodoForm({
            "codigo": periodo.codigo, "nombre": periodo.nombre,
            "fecha_inicio": "2026-07-01", "fecha_fin": "2026-09-30",
            "cerrado": True,
        }, instance=periodo)

        self.assertFalse(form.is_valid())
        self.assertIn("Gestión y Planificación: 85", str(form.errors["cerrado"]))

    def test_CP_CGO_008_carga_en_un_periodo_existente(self):
        """CP-CGO-008: con --periodo las metas se cargan en ese período, con códigos propios."""
        Periodo.objects.create(
            codigo="PER-2026", nombre="Año 2026",
            fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31),
        )
        cargar("--periodo", "PER-2026")

        self.assertFalse(Periodo.objects.filter(codigo="2026-T3").exists())
        self.assertEqual(Meta.objects.filter(periodo__codigo="PER-2026").count(), 37)
        self.assertTrue(Meta.objects.filter(codigo="PER-2026-GSO-01").exists())

    # --- CASOS DE BORDE ---
    def test_CP_CGO_009_restaura_una_meta_editada(self):
        """CP-CGO-009 (borde): si alguien cambió una meta cargada, la recarga vuelve al valor de la matriz."""
        cargar()
        meta = Meta.objects.get(codigo="2026-T3-GSO-01")
        Meta.objects.filter(pk=meta.pk).update(ponderacion=Decimal("10"), activo=False)

        salida = cargar()

        meta.refresh_from_db()
        self.assertEqual(meta.ponderacion, Decimal("20"))
        self.assertTrue(meta.activo)
        self.assertIn("Metas: 0 creados, 1 actualizados, 36 sin cambios", salida)

    def test_CP_CGO_010_reutiliza_cargos_existentes(self):
        """CP-CGO-010 (borde): un cargo ya creado con otras mayúsculas se reutiliza y se reactiva, sin duplicar."""
        existente = Cargo.objects.create(
            nombre="gestor social", descripcion="Descripción propia", activo=False
        )
        cargar()

        self.assertEqual(Cargo.objects.filter(nombre__iexact="gestor social").count(), 1)
        existente.refresh_from_db()
        self.assertTrue(existente.activo)
        self.assertEqual(existente.descripcion, "Descripción propia")
        self.assertEqual(existente.metas.count(), 6)

    def test_CP_CGO_011_respeta_actividades_existentes(self):
        """CP-CGO-011 (borde): una actividad inactiva se reactiva, pero su tipo de gestión editado no se pisa."""
        CatalogoActividad.objects.create(
            codigo="sgr-talleres", nombre="Talleres",
            tipo_gestion=TIPO_GESTION_PREPARATORIA, activo=False,
        )
        cargar()

        actividad = CatalogoActividad.objects.get(codigo__iexact="SGR-TALLERES")
        self.assertTrue(actividad.activo)
        self.assertEqual(actividad.tipo_gestion, TIPO_GESTION_PREPARATORIA)
        self.assertEqual(CatalogoActividad.objects.count(), 28)

    def test_CP_CGO_012_periodo_cerrado_no_se_toca(self):
        """CP-CGO-012 (borde): si el período está cerrado se detiene sin guardar nada."""
        Periodo.objects.create(
            codigo="2026-T3", nombre="Cerrado",
            fecha_inicio=date(2026, 7, 1), fecha_fin=date(2026, 9, 30), cerrado=True,
        )

        with self.assertRaisesMessage(CommandError, "está cerrado"):
            cargar()

        self.assertFalse(Cargo.objects.exists())
        self.assertFalse(CatalogoActividad.objects.exists())

    def test_CP_CGO_013_conflicto_con_metas_previas_revierte_todo(self):
        """CP-CGO-013 (borde): si un cargo ya tiene otras metas que harían superar el 100 %, no se guarda nada."""
        periodo = Periodo.objects.create(
            codigo="2026-T3", nombre="T3",
            fecha_inicio=date(2026, 7, 1), fecha_fin=date(2026, 9, 30),
        )
        cargo = Cargo.objects.create(nombre="Gestor de Seguridad")
        actividad = CatalogoActividad.objects.create(codigo="OTRA", nombre="Otra actividad")
        Meta.objects.create(
            codigo="MANUAL-1", nombre="Meta manual", periodo=periodo,
            actividad=actividad, cargo=cargo,
            valor_objetivo=Decimal("1"), ponderacion=Decimal("90"),
        )

        with self.assertRaisesMessage(CommandError, "No se guardó ningún cambio"):
            cargar()

        self.assertEqual(Meta.objects.count(), 1)
        self.assertEqual(Cargo.objects.count(), 1)
        self.assertEqual(CatalogoActividad.objects.count(), 1)

    def test_CP_CGO_014_periodo_elegido_inexistente(self):
        """CP-CGO-014 (borde): --periodo con un código que no existe se rechaza."""
        with self.assertRaisesMessage(CommandError, "No existe el período NO-EXISTE"):
            cargar("--periodo", "NO-EXISTE")

        self.assertFalse(Meta.objects.exists())

    def test_CP_CGO_015_archivos_invalidos(self):
        """CP-CGO-015 (borde): archivo inexistente, JSON mal formado o meta con actividad desconocida se rechazan."""
        import tempfile
        from pathlib import Path

        with self.assertRaisesMessage(CommandError, "No existe el archivo"):
            cargar("--archivo", "no-existe.json")

        with tempfile.TemporaryDirectory() as carpeta:
            malo = Path(carpeta) / "malo.json"
            malo.write_text("{ esto no es json", encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "no es un JSON válido"):
                cargar("--archivo", str(malo))

            datos = json.loads(Path(ARCHIVO_POR_DEFECTO).read_text(encoding="utf-8"))
            datos["cargos"][1]["metas"][0]["actividad"] = "NO-EXISTE"
            incoherente = Path(carpeta) / "incoherente.json"
            incoherente.write_text(json.dumps(datos), encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "NO-EXISTE"):
                cargar("--archivo", str(incoherente))

        self.assertFalse(Cargo.objects.exists())

    def test_CP_CGO_016_restaura_aunque_otra_meta_este_inflada(self):
        """CP-CGO-016 (borde): si la última meta de un cargo se infló a 80 %, la recarga igual cuadra el 100 % sin error."""
        cargar()
        Meta.objects.filter(codigo="2026-T3-GSO-06").update(ponderacion=Decimal("80"))

        cargar()

        periodo = self.periodo()
        self.assertEqual(
            sum(periodo.ponderaciones_activas(cargo=Cargo.objects.get(nombre="Gestor Social"))),
            Decimal("100"),
        )
