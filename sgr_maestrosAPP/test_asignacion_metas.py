"""
Evaluación 3 - Asignación de metas por funcionario y trimestre.

Pauta, Actividad 1: «Asignación de metas por funcionario y trimestre,
incluyendo cantidad exigida, ponderación individual y tope máximo de
cumplimiento de 120%. Solo deben contabilizarse registros aprobados».
Pauta, Actividad 2: «Separación entre catálogo de metas y asignación de
metas por funcionario y trimestre, con cantidad y ponderación propias».

Casos CP-AMT-001 a CP-AMT-016.
"""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from actividadesAPP.models import RegistroActividad
from actividadesAPP.puntajes import obtener_mi_matriz
from delegacionesAPP.models import Delegacion
from seguridadAPP.models import Cargo
from seguridadAPP.perfiles import ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles
from tubo_gestionAPP.tests import crear_usuario

from .models import AsignacionMeta, CatalogoActividad, Meta, Periodo, metas_del_funcionario


FECHA_PRUEBA = datetime(2026, 11, 11, 12, 0, tzinfo=ZoneInfo("America/Santiago"))


class BaseAsignaciones(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro", direccion="Dir", encargado="Enc",
            email="centro@laserena.cl", telefono="512000001", celular="912000001",
        )
        cls.pampa = Delegacion.objects.create(
            nombre="Delegación La Pampa", direccion="Dir", encargado="Enc",
            email="pampa@laserena.cl", telefono="512000002", celular="912000002",
        )
        cls.cargo = Cargo.objects.create(nombre="Gestor Social AMT")
        cls.otro_cargo = Cargo.objects.create(nombre="Apoyo Administrativo AMT")

        cls.supervisor = crear_usuario("21.345.678-4", "sup@laserena.cl", SUPERVISOR, cls.centro)
        cls.usuario = crear_usuario("22.456.789-8", "fun@laserena.cl", ADMINISTRATIVO, cls.centro)
        cls.usuario_2 = crear_usuario("12.345.678-5", "fun2@laserena.cl", ADMINISTRATIVO, cls.centro)
        cls.usuario_pampa = crear_usuario("11.111.111-1", "pampa@laserena.cl", ADMINISTRATIVO, cls.pampa)

        cls.funcionario = cls.usuario.perfil
        cls.funcionario_2 = cls.usuario_2.perfil
        cls.funcionario_pampa = cls.usuario_pampa.perfil
        for perfil in (cls.funcionario, cls.funcionario_2, cls.funcionario_pampa):
            perfil.cargo = cls.cargo
            perfil.save()

        cls.periodo = Periodo.objects.create(
            codigo="2026-T4-AMT", nombre="Cuarto trimestre",
            fecha_inicio=date(2026, 11, 9), fecha_fin=date(2026, 11, 13),
        )
        cls.actividad_a = CatalogoActividad.objects.create(codigo="AMT-A", nombre="Taller", tipo_gestion="EJECUCION")
        cls.actividad_b = CatalogoActividad.objects.create(codigo="AMT-B", nombre="Visita", tipo_gestion="EJECUCION")
        cls.actividad_c = CatalogoActividad.objects.create(codigo="AMT-C", nombre="Operativo", tipo_gestion="EJECUCION")

        cls.meta_a = Meta.objects.create(
            codigo="AMT-META-A", nombre="Talleres", periodo=cls.periodo, actividad=cls.actividad_a,
            cargo=cls.cargo, valor_objetivo=Decimal("2.00"), ponderacion=Decimal("60.00"),
        )
        cls.meta_b = Meta.objects.create(
            codigo="AMT-META-B", nombre="Visitas", periodo=cls.periodo, actividad=cls.actividad_b,
            cargo=cls.cargo, valor_objetivo=Decimal("4.00"), ponderacion=Decimal("40.00"),
        )

    def setUp(self):
        reloj = patch("actividadesAPP.models.timezone.now", return_value=FECHA_PRUEBA)
        reloj.start()
        self.addCleanup(reloj.stop)

    def registrar(self, funcionario=None, actividad=None, aprobada=True):
        registro = RegistroActividad.objects.create(
            funcionario=funcionario or self.funcionario,
            actividad=actividad or self.actividad_a,
            fecha_actividad=date(2026, 11, 10),
            solicitante_tipo="VECINO",
            nombre_usuario="Vecino Prueba",
            telefono_usuario="987654321",
            detalle="Gestión realizada",
        )
        if aprobada:
            RegistroActividad.objects.filter(pk=registro.pk).update(
                estado_verificacion=RegistroActividad.APROBADA
            )
        return registro

    def asignar(self, meta=None, funcionario=None, cantidad="3.00", ponderacion="60.00", **extra):
        asignacion = AsignacionMeta(
            meta=meta or self.meta_a,
            funcionario=funcionario or self.funcionario,
            cantidad_exigida=Decimal(cantidad),
            ponderacion=Decimal(ponderacion),
            **extra,
        )
        asignacion.full_clean()
        asignacion.save()
        return asignacion

    @staticmethod
    def item(matriz, actividad):
        return next(i for i in matriz["items"] if i["actividad"].pk == actividad.pk)


class PruebasCalculoConAsignacion(BaseAsignaciones):

    def test_cp_amt_001_matriz_usa_cantidad_y_ponderacion_individual(self):
        """Con cantidad exigida 3 y 3 registros aprobados, cumple 100% (no 120%)."""
        self.asignar(cantidad="3.00", ponderacion="60.00")
        for _ in range(3):
            self.registrar()
        item = self.item(obtener_mi_matriz(self.funcionario, self.periodo), self.actividad_a)
        self.assertEqual(item["objetivo_original"], Decimal("3.00"))
        self.assertEqual(item["cumplimiento"], Decimal("100.00"))
        self.assertEqual(item["puntaje"], Decimal("60.00"))
        self.assertTrue(item["individual"])

    def test_cp_amt_002_sin_asignacion_se_usa_la_meta_del_cargo(self):
        """Control: el otro funcionario sigue con objetivo 2 (3/2 = 150% -> 120%)."""
        self.asignar(cantidad="3.00")
        for _ in range(3):
            self.registrar(funcionario=self.funcionario_2)
        item = self.item(obtener_mi_matriz(self.funcionario_2, self.periodo), self.actividad_a)
        self.assertEqual(item["objetivo_original"], Decimal("2.00"))
        self.assertEqual(item["cumplimiento"], Decimal("120.00"))
        self.assertFalse(item["individual"])

    def test_cp_amt_003_tope_de_120_tambien_con_asignacion(self):
        self.asignar(cantidad="1.00", ponderacion="50.00")
        for _ in range(5):
            self.registrar()
        item = self.item(obtener_mi_matriz(self.funcionario, self.periodo), self.actividad_a)
        self.assertEqual(item["cumplimiento"], Decimal("120.00"))
        self.assertEqual(item["puntaje"], Decimal("60.00"))

    def test_cp_amt_004_solo_cuentan_registros_aprobados(self):
        self.asignar(cantidad="2.00")
        self.registrar(aprobada=True)
        self.registrar(aprobada=False)
        item = self.item(obtener_mi_matriz(self.funcionario, self.periodo), self.actividad_a)
        self.assertEqual(item["avance"], 1)
        self.assertEqual(item["cumplimiento"], Decimal("50.00"))

    def test_cp_amt_005_meta_general_asignada_se_suma_a_la_matriz(self):
        Meta.objects.filter(pk=self.meta_b.pk).update(ponderacion=Decimal("20.00"))
        general = Meta.objects.create(
            codigo="AMT-GENERAL", nombre="Operativos", periodo=self.periodo,
            actividad=self.actividad_c, valor_objetivo=Decimal("1.00"), ponderacion=Decimal("20.00"),
        )
        self.asignar(meta=general, cantidad="1.00", ponderacion="20.00")
        metas = [m.meta.codigo for m in metas_del_funcionario(self.funcionario, self.periodo)]
        self.assertEqual(metas, ["AMT-GENERAL", "AMT-META-A", "AMT-META-B"])
        self.assertEqual(obtener_mi_matriz(self.funcionario, self.periodo)["ponderacion_total"], Decimal("100.00"))

    def test_cp_amt_006_asignacion_de_baja_vuelve_a_la_meta_del_cargo(self):
        asignacion = self.asignar(cantidad="5.00")
        asignacion.activo = False
        asignacion.save()
        item = self.item(obtener_mi_matriz(self.funcionario, self.periodo), self.actividad_a)
        self.assertEqual(item["objetivo_original"], Decimal("2.00"))


class PruebasValidacionAsignacion(BaseAsignaciones):

    def test_cp_amt_007_ponderacion_individual_no_supera_100(self):
        """Meta B pesa 40%: asignar 70% a la meta A sumaría 110%."""
        with self.assertRaises(ValidationError) as error:
            self.asignar(ponderacion="70.00")
        self.assertIn("ponderacion", error.exception.message_dict)
        self.assertIn("60.00%", str(error.exception))

    def test_cp_amt_008_cargo_distinto_se_rechaza(self):
        meta_otro = Meta.objects.create(
            codigo="AMT-OTRO", nombre="Cartas", periodo=self.periodo, actividad=self.actividad_c,
            cargo=self.otro_cargo, valor_objetivo=Decimal("1.00"), ponderacion=Decimal("100.00"),
        )
        with self.assertRaises(ValidationError) as error:
            self.asignar(meta=meta_otro)
        self.assertIn("funcionario", error.exception.message_dict)

    def test_cp_amt_009_periodo_cerrado_se_rechaza(self):
        Periodo.objects.filter(pk=self.periodo.pk).update(cerrado=True)
        with self.assertRaises(ValidationError) as error:
            self.asignar()
        self.assertIn("meta", error.exception.message_dict)

    def test_cp_amt_010_no_duplica_asignacion_vigente(self):
        self.asignar(ponderacion="30.00")
        with self.assertRaises(ValidationError):
            self.asignar(ponderacion="30.00")

    def test_cp_amt_011_cantidad_exigida_debe_ser_positiva(self):
        with self.assertRaises(ValidationError) as error:
            self.asignar(cantidad="0.00")
        self.assertIn("cantidad_exigida", error.exception.message_dict)


class PruebasPantallaAsignaciones(BaseAsignaciones):

    def datos(self, funcionario=None, **cambios):
        datos = {
            "meta": self.meta_a.pk,
            "funcionario": (funcionario or self.funcionario).pk,
            "cantidad_exigida": "3",
            "ponderacion": "60",
            "observacion": "",
        }
        datos.update(cambios)
        return datos

    def test_cp_amt_012_supervisor_asigna_a_su_equipo(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(reverse("sgr_maestros:asignacion_crear"), self.datos())
        self.assertRedirects(respuesta, reverse("sgr_maestros:asignacion_lista"))
        self.assertTrue(AsignacionMeta.objects.filter(funcionario=self.funcionario, activo=True).exists())

    def test_cp_amt_013_supervisor_no_asigna_a_otra_delegacion(self):
        self.client.force_login(self.supervisor)
        self.client.post(reverse("sgr_maestros:asignacion_crear"), self.datos(funcionario=self.funcionario_pampa))
        self.assertFalse(AsignacionMeta.objects.filter(funcionario=self.funcionario_pampa).exists())

    def test_cp_amt_014_administrativo_no_accede(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("sgr_maestros:asignacion_lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sgr_maestros:asignacion_crear")).status_code, 403)

    def test_cp_amt_015_resumen_muestra_ponderacion_total(self):
        self.asignar(ponderacion="60.00")
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("sgr_maestros:asignacion_lista"), {"periodo": self.periodo.pk})
        resumen = {fila["funcionario"]: fila for fila in respuesta.context["resumen"]}
        self.assertEqual(len(resumen), 2)
        fila = next(f for f in resumen.values() if f["individuales"] == 1)
        self.assertEqual(fila["total"], Decimal("100.00"))
        self.assertTrue(fila["completo"])

    def test_cp_amt_016_baja_y_reactivacion_valida_el_100(self):
        asignacion = self.asignar(ponderacion="60.00")
        self.client.force_login(self.supervisor)
        url = reverse("sgr_maestros:asignacion_cambiar_estado", args=[asignacion.pk])
        self.client.post(url)
        asignacion.refresh_from_db()
        self.assertFalse(asignacion.activo)
        # Mientras está de baja, la meta B sube a 60%: reactivar sumaría 120%.
        Meta.objects.filter(pk=self.meta_b.pk).update(ponderacion=Decimal("60.00"))
        self.client.post(url)
        asignacion.refresh_from_db()
        self.assertFalse(asignacion.activo)
