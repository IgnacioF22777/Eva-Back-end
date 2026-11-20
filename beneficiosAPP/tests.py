"""
Evaluación 3 - Regalos para niños. Responsable: Camilo Villalobos.

Respuestas del profesor: se piden RUT, nombre, apellido, sexo y fecha de
nacimiento; los inscribe el funcionario; un RUT no se repite en la misma
campaña entre delegaciones; cada delegación ve solo lo suyo.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .models import CampanaRegalo, NinoInscrito, edad_en


def rut_con_dv(numero):
    """RUT válido (Módulo 11) a partir del número, para las pruebas."""
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    dv = 11 - suma % 11
    dv = "0" if dv == 11 else "K" if dv == 10 else str(dv)
    return f"{numero}-{dv}"


def crear_delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre, direccion="Dirección", encargado="Encargado",
        email=f"{nombre.lower().replace(' ', '')}@laserena.cl",
        telefono="512000000", celular="912345678",
    )


def crear_funcionario(rut, nombre, perfil, delegacion):
    usuario = User.objects.create_user(
        username=normalizar_rut(rut), password="Clave-Segura-2026",
        first_name=nombre, last_name="Prueba",
    )
    PerfilUsuario.objects.create(usuario=usuario, rut=normalizar_rut(rut), delegacion=delegacion)
    usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = crear_delegacion("Delegación Centro")
        cls.pampa = crear_delegacion("Delegación La Pampa")

        cls.admin = crear_funcionario("11.111.111-1", "Admin", ADMINISTRADOR, None)
        cls.delegado = crear_funcionario("12.345.678-5", "Delegado", SUPERVISOR, cls.centro)
        cls.maria = crear_funcionario("22.222.222-2", "María", ADMINISTRATIVO, cls.centro)
        cls.pedro = crear_funcionario("33.333.333-3", "Pedro", ADMINISTRATIVO, cls.centro)
        cls.luis = crear_funcionario("55.555.555-5", "Luis", ADMINISTRATIVO, cls.pampa)

        hoy = timezone.localdate()
        cls.navidad = CampanaRegalo.objects.create(
            tipo=CampanaRegalo.NAVIDAD, anio=hoy.year,
            fecha_inicio=hoy - timedelta(days=10), fecha_fin=hoy + timedelta(days=20),
            edad_maxima=12,
        )
        cls.rut_nino = rut_con_dv(25123456)

    def inscribir(self, usuario, campana=None, rut=None, **cambios):
        nino = NinoInscrito(
            campana=campana or self.navidad, rut=rut or self.rut_nino,
            nombre="Sofía", apellido="Rojas", sexo=NinoInscrito.FEMENINO,
            fecha_nacimiento=date(2018, 5, 10),
            delegacion=usuario.perfil.delegacion, registrado_por=usuario,
        )
        for campo, valor in cambios.items():
            setattr(nino, campo, valor)
        nino.full_clean()
        nino.save()
        return nino

    def datos(self, **cambios):
        datos = {
            "campana": self.navidad.pk, "rut": self.rut_nino, "nombre": "Sofía",
            "apellido": "Rojas", "sexo": "F", "fecha_nacimiento": "2018-05-10",
        }
        datos.update(cambios)
        return datos


class PruebasModelo(Base):

    def test_CP_REG_001_inscripcion_valida_normaliza_el_rut(self):
        """CP-REG-001: el RUT con puntos se guarda normalizado."""
        nino = self.inscribir(self.maria, rut="25.123.456-" + self.rut_nino[-1])
        self.assertEqual(nino.rut, self.rut_nino)
        self.assertEqual(nino.delegacion, self.centro)

    def test_CP_REG_002_rut_invalido(self):
        """CP-REG-002: un dígito verificador incorrecto se rechaza."""
        malo = self.rut_nino[:-1] + ("1" if self.rut_nino[-1] != "1" else "2")
        with self.assertRaises(ValidationError) as error:
            self.inscribir(self.maria, rut=malo)
        self.assertIn("rut", error.exception.message_dict)

    def test_CP_REG_003_rut_repetido_en_otra_delegacion(self):
        """CP-REG-003: el mensaje dice qué delegación ya lo inscribió."""
        self.inscribir(self.maria)
        with self.assertRaises(ValidationError) as error:
            self.inscribir(self.luis)
        mensaje = " ".join(error.exception.message_dict["rut"])
        self.assertIn("RUT ya ingresado por Delegación Centro", mensaje)

    def test_CP_REG_004_mismo_rut_en_otra_campana(self):
        """CP-REG-004: el mismo niño puede estar en Navidad y en el Día del Niño."""
        hoy = timezone.localdate()
        dia_nino = CampanaRegalo.objects.create(
            tipo=CampanaRegalo.DIA_NINO, anio=hoy.year,
            fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=5),
        )
        self.inscribir(self.maria)
        self.inscribir(self.luis, campana=dia_nino)
        self.assertEqual(NinoInscrito.objects.count(), 2)

    def test_CP_REG_005_anulado_libera_el_rut(self):
        """CP-REG-005: si se anula la inscripción, otra delegación puede inscribirlo."""
        nino = self.inscribir(self.maria)
        nino.activo = False
        nino.save()
        self.inscribir(self.luis)

    def test_CP_REG_006_edad_maxima(self):
        """CP-REG-006 (borde): 12 años al cierre se acepta; 13 se rechaza."""
        cierre = self.navidad.fecha_fin
        doce = date(cierre.year - 12, cierre.month, cierre.day)
        self.inscribir(self.maria, fecha_nacimiento=doce)

        trece = date(cierre.year - 13, cierre.month, cierre.day)
        with self.assertRaises(ValidationError) as error:
            self.inscribir(self.maria, rut=rut_con_dv(25999888), fecha_nacimiento=trece)
        self.assertIn("fecha_nacimiento", error.exception.message_dict)

    def test_CP_REG_007_fecha_de_nacimiento_futura(self):
        """CP-REG-007: no se acepta una fecha de nacimiento futura."""
        with self.assertRaises(ValidationError) as error:
            self.inscribir(self.maria, fecha_nacimiento=timezone.localdate() + timedelta(days=1))
        self.assertIn("fecha_nacimiento", error.exception.message_dict)

    def test_CP_REG_008_campana_cerrada_o_fuera_de_fecha(self):
        """CP-REG-008: no se inscribe en una campaña cerrada ni vencida."""
        hoy = timezone.localdate()
        vencida = CampanaRegalo.objects.create(
            tipo=CampanaRegalo.ANIVERSARIO, anio=hoy.year,
            fecha_inicio=hoy - timedelta(days=30), fecha_fin=hoy - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as error:
            self.inscribir(self.maria, campana=vencida)
        self.assertIn("campana", error.exception.message_dict)

        self.navidad.activo = False
        self.navidad.save()
        with self.assertRaises(ValidationError):
            self.inscribir(self.maria)

    def test_CP_REG_009_edad_calculada(self):
        """CP-REG-009: la edad se calcula con años cumplidos."""
        self.assertEqual(edad_en(date(2018, 12, 25), date(2026, 12, 24)), 7)
        self.assertEqual(edad_en(date(2018, 12, 25), date(2026, 12, 25)), 8)


class PruebasPantallas(Base):

    def test_CP_REG_010_funcionario_inscribe_por_pantalla(self):
        """CP-REG-010: el funcionario inscribe; la delegación la pone el sistema."""
        self.client.force_login(self.maria)
        respuesta = self.client.post(reverse("beneficios:nino_crear"), self.datos())
        self.assertRedirects(respuesta, reverse("beneficios:nino_lista"))

        nino = NinoInscrito.objects.get()
        self.assertEqual(nino.delegacion, self.centro)
        self.assertEqual(nino.registrado_por, self.maria)

    def test_CP_REG_011_pantalla_muestra_rut_duplicado(self):
        """CP-REG-011: otra delegación ve el aviso y no se guarda."""
        self.inscribir(self.maria)
        self.client.force_login(self.luis)
        respuesta = self.client.post(reverse("beneficios:nino_crear"), self.datos())
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "RUT ya ingresado por Delegación Centro")
        self.assertEqual(NinoInscrito.objects.count(), 1)

    def test_CP_REG_012_cada_delegacion_ve_solo_lo_suyo(self):
        """CP-REG-012 (seguridad): La Pampa no ve los niños de Centro; el Admin ve todo."""
        self.inscribir(self.maria)
        self.inscribir(self.luis, rut=rut_con_dv(26111222), nombre="Tomás")

        self.client.force_login(self.luis)
        respuesta = self.client.get(reverse("beneficios:nino_lista"))
        self.assertContains(respuesta, "Tomás")
        self.assertNotContains(respuesta, "Sofía")

        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("beneficios:nino_lista"))
        self.assertContains(respuesta, "Tomás")
        self.assertContains(respuesta, "Sofía")

    def test_CP_REG_013_no_modifica_ninos_de_otra_delegacion(self):
        """CP-REG-013 (seguridad): editar o anular un niño ajeno da 403."""
        nino = self.inscribir(self.maria)
        delegada_pampa = crear_funcionario("44.444.444-4", "Delegada", SUPERVISOR, self.pampa)
        self.client.force_login(delegada_pampa)

        respuesta = self.client.post(
            reverse("beneficios:nino_editar", args=[nino.pk]), self.datos(nombre="Otro")
        )
        self.assertEqual(respuesta.status_code, 403)
        respuesta = self.client.post(reverse("beneficios:nino_cambiar_estado", args=[nino.pk]))
        self.assertEqual(respuesta.status_code, 403)

        nino.refresh_from_db()
        self.assertEqual(nino.nombre, "Sofía")
        self.assertTrue(nino.activo)

    def test_CP_REG_014_funcionario_corrige_solo_lo_suyo(self):
        """CP-REG-014: Pedro no corrige lo que inscribió María; el delegado sí."""
        nino = self.inscribir(self.maria)

        self.client.force_login(self.pedro)
        respuesta = self.client.post(
            reverse("beneficios:nino_editar", args=[nino.pk]), self.datos(nombre="Otro")
        )
        self.assertEqual(respuesta.status_code, 403)

        self.client.force_login(self.delegado)
        respuesta = self.client.post(
            reverse("beneficios:nino_editar", args=[nino.pk]), self.datos(nombre="Sofía Ignacia")
        )
        self.assertRedirects(respuesta, reverse("beneficios:nino_lista"))
        nino.refresh_from_db()
        self.assertEqual(nino.nombre, "Sofía Ignacia")

    def test_CP_REG_015_funcionario_no_anula(self):
        """CP-REG-015: anular es del delegado; el funcionario recibe 403."""
        nino = self.inscribir(self.maria)
        self.client.force_login(self.maria)
        respuesta = self.client.post(reverse("beneficios:nino_cambiar_estado", args=[nino.pk]))
        self.assertEqual(respuesta.status_code, 403)

        self.client.force_login(self.delegado)
        self.client.post(reverse("beneficios:nino_cambiar_estado", args=[nino.pk]))
        nino.refresh_from_db()
        self.assertFalse(nino.activo)

    def test_CP_REG_016_no_reactiva_si_otra_delegacion_lo_inscribio(self):
        """CP-REG-016: reactivar una inscripción anulada respeta el RUT único."""
        nino = self.inscribir(self.maria)
        nino.activo = False
        nino.save()
        self.inscribir(self.luis)

        self.client.force_login(self.delegado)
        self.client.post(reverse("beneficios:nino_cambiar_estado", args=[nino.pk]))
        nino.refresh_from_db()
        self.assertFalse(nino.activo)

    def test_CP_REG_017_campanas_solo_administrador(self):
        """CP-REG-017 (seguridad): el delegado no crea campañas; el Admin sí."""
        hoy = timezone.localdate()
        datos = {
            "tipo": CampanaRegalo.DIA_NINO, "anio": hoy.year,
            "fecha_inicio": hoy.isoformat(), "fecha_fin": (hoy + timedelta(days=5)).isoformat(),
            "edad_maxima": 12,
        }
        self.client.force_login(self.delegado)
        self.assertEqual(self.client.post(reverse("beneficios:campana_crear"), datos).status_code, 403)

        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("beneficios:campana_crear"), datos)
        self.assertRedirects(respuesta, reverse("beneficios:campana_lista"))
        self.assertTrue(CampanaRegalo.objects.filter(tipo=CampanaRegalo.DIA_NINO).exists())
        self.assertContains(self.client.get(reverse("beneficios:campana_lista")), "Día del Niño")

    def test_CP_REG_018_campana_no_se_repite_en_el_anio(self):
        """CP-REG-018: no puede haber dos campañas de Navidad el mismo año."""
        hoy = timezone.localdate()
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("beneficios:campana_crear"), {
            "tipo": CampanaRegalo.NAVIDAD, "anio": hoy.year,
            "fecha_inicio": hoy.isoformat(), "fecha_fin": hoy.isoformat(), "edad_maxima": 12,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(CampanaRegalo.objects.filter(tipo=CampanaRegalo.NAVIDAD).count(), 1)

    def test_CP_REG_019_excel_respeta_la_delegacion(self):
        """CP-REG-019 (seguridad): la planilla de La Pampa no trae niños de Centro."""
        from io import BytesIO
        from openpyxl import load_workbook

        self.inscribir(self.maria)
        self.client.force_login(self.luis)
        respuesta = self.client.get(reverse("beneficios:nino_exportar_excel"))
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.content))
        texto = " ".join(str(c.value) for fila in libro.active.iter_rows() for c in fila if c.value)
        self.assertNotIn("Sofía", texto)

    def test_CP_REG_020_sin_sesion_no_entra(self):
        """CP-REG-020: sin iniciar sesión se redirige al login."""
        respuesta = self.client.get(reverse("beneficios:nino_lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])
