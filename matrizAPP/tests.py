"""
Evaluación 3 - Matriz SGR: ausencias (R9), felicitaciones y reclamos (R8)
y semáforo. Responsable: Camilo Villalobos.

Cada prueba tiene un ID que se usa en la matriz de resultado esperado vs.
obtenido del informe. "Borde" = caso límite.
"""

import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from seguridadAPP.roles import sincronizar_roles

from .models import AjusteDesempeno, Ausencia
from .reglas import (
    NARANJO, ROJO, VERDE,
    aplicar_ajustes, color_semaforo, interseccion, objetivo_al_dia,
    requiere_informe_rrhh, se_traslapan,
)
from .servicios import alerta_rrhh, contar_ajustes, cumplimiento_final, dias_ausencia


D = Decimal
CARPETA_MEDIA = tempfile.mkdtemp(prefix="sgr_matriz_tests_")


def tearDownModule():
    shutil.rmtree(CARPETA_MEDIA, ignore_errors=True)


# ============================================================
# 1. REGLAS PURAS (sin base de datos)
# ============================================================

class PruebasReglasFechas(SimpleTestCase):

    def test_CP_AUS_001_traslape_de_rangos(self):
        """CP-AUS-001 (borde): compartir un extremo es traslape; días contiguos no."""
        d = date
        self.assertTrue(se_traslapan(d(2026, 11, 2), d(2026, 11, 6), d(2026, 11, 4), d(2026, 11, 10)))
        self.assertTrue(se_traslapan(d(2026, 11, 2), d(2026, 11, 6), d(2026, 11, 6), d(2026, 11, 9)))
        self.assertFalse(se_traslapan(d(2026, 11, 2), d(2026, 11, 6), d(2026, 11, 7), d(2026, 11, 9)))
        self.assertTrue(se_traslapan(d(2026, 11, 1), d(2026, 11, 30), d(2026, 11, 10), d(2026, 11, 12)))

    def test_interseccion(self):
        """La parte común de dos rangos se usa para recortar ausencias al período."""
        d = date
        self.assertEqual(
            interseccion(d(2026, 9, 28), d(2026, 10, 3), d(2026, 7, 1), d(2026, 9, 30)),
            (d(2026, 9, 28), d(2026, 9, 30)),
        )
        self.assertIsNone(interseccion(d(2026, 10, 1), d(2026, 10, 3), d(2026, 7, 1), d(2026, 9, 30)))


class PruebasReglasAjustes(SimpleTestCase):

    def test_CP_AJU_001_suma_y_resta(self):
        """CP-AJU-001: 95% + 2 felicitaciones - 1 reclamo = 95%."""
        self.assertEqual(aplicar_ajustes(D("0.95"), 2, 1), D("0.95"))
        self.assertEqual(aplicar_ajustes(D("0.80"), 1, 0), D("0.90"))
        self.assertEqual(aplicar_ajustes(D("0.80"), 0, 1), D("0.60"))

    def test_CP_AJU_002_tope_de_120(self):
        """CP-AJU-002 (borde): el total nunca supera 120%, aunque haya más felicitaciones."""
        self.assertEqual(aplicar_ajustes(D("1.10"), 3, 0), D("1.20"))
        self.assertEqual(aplicar_ajustes(D("1.20"), 2, 0), D("1.20"))
        self.assertEqual(aplicar_ajustes(D("1.10"), 1, 0), D("1.20"))
        self.assertEqual(aplicar_ajustes(D("1.00"), 1, 0), D("1.10"))

    def test_CP_AJU_003_nunca_menor_que_cero(self):
        """CP-AJU-003 (borde): 10% con un reclamo queda en 0%, no en -10%."""
        self.assertEqual(aplicar_ajustes(D("0.10"), 0, 1), D("0"))
        self.assertEqual(aplicar_ajustes(D("0.20"), 0, 1), D("0"))
        with self.assertRaises(ValueError):
            aplicar_ajustes(D("0.50"), -1, 0)

    def test_CP_AJU_004_alerta_rrhh_por_trimestres_seguidos(self):
        """CP-AJU-004: reclamos en el trimestre actual y el anterior -> informar a RRHH."""
        hoy = date(2026, 11, 13)  # 4.º trimestre
        self.assertTrue(requiere_informe_rrhh([date(2026, 8, 5), date(2026, 11, 2)], hoy))
        # Solo el trimestre actual, o trimestres no seguidos: no.
        self.assertFalse(requiere_informe_rrhh([date(2026, 11, 2)], hoy))
        self.assertFalse(requiere_informe_rrhh([date(2026, 5, 2), date(2026, 11, 2)], hoy))
        # Borde: el cambio de año también cuenta como trimestres seguidos.
        self.assertTrue(requiere_informe_rrhh([date(2026, 12, 20), date(2027, 1, 10)], date(2027, 2, 1)))


class PruebasReglasSemaforo(SimpleTestCase):

    def test_CP_SEM_001_verde(self):
        """CP-SEM-001 (borde): avance igual al objetivo del día es verde."""
        self.assertEqual(color_semaforo(D("0.55"), D("0.50")), VERDE)
        self.assertEqual(color_semaforo(D("0.50"), D("0.50")), VERDE)

    def test_CP_SEM_002_naranjo(self):
        """CP-SEM-002 (borde): exactamente el 60% del objetivo es naranjo."""
        self.assertEqual(color_semaforo(D("0.35"), D("0.50")), NARANJO)
        self.assertEqual(color_semaforo(D("0.30"), D("0.50")), NARANJO)

    def test_CP_SEM_003_rojo(self):
        """CP-SEM-003 (borde): bajo el 60% del objetivo es rojo."""
        self.assertEqual(color_semaforo(D("0.2999"), D("0.50")), ROJO)
        self.assertEqual(color_semaforo(D("0"), D("0.50")), ROJO)

    def test_objetivo_al_dia(self):
        """Objetivo del día = días transcurridos / días totales (sin ausencias)."""
        self.assertEqual(objetivo_al_dia(30, 60), D("0.5"))
        self.assertEqual(objetivo_al_dia(70, 60), D("1"))
        self.assertEqual(objetivo_al_dia(5, 0), D("0"))


# ============================================================
# BASE PARA PRUEBAS CON BASE DE DATOS
# ============================================================

def crear_delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre, direccion="Dirección", encargado="Encargado",
        email=f"{nombre.lower()}@laserena.cl", telefono="512000000", celular="912345678",
    )


def crear_funcionario(rut, nombre, perfil, delegacion):
    usuario = User.objects.create_user(
        username=normalizar_rut(rut), password="Clave-Segura-2026",
        first_name=nombre, last_name="Prueba",
    )
    PerfilUsuario.objects.create(usuario=usuario, rut=normalizar_rut(rut), delegacion=delegacion)
    usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


@override_settings(MEDIA_ROOT=CARPETA_MEDIA)
class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = crear_delegacion("Centro")
        cls.pampa = crear_delegacion("Pampa")

        cls.admin = crear_funcionario("11.111.111-1", "Admin", ADMINISTRADOR, None)
        cls.delegado = crear_funcionario("12.345.678-5", "Delegado", SUPERVISOR, cls.centro)
        cls.maria = crear_funcionario("22.222.222-2", "María", ADMINISTRATIVO, cls.centro)
        cls.pedro = crear_funcionario("33.333.333-3", "Pedro", ADMINISTRATIVO, cls.centro)
        cls.delegado_pampa = crear_funcionario("44.444.444-4", "Delegada", SUPERVISOR, cls.pampa)
        cls.luis = crear_funcionario("55.555.555-5", "Luis", ADMINISTRATIVO, cls.pampa)

    def ausencia(self, funcionario, inicio, fin, activo=True, tipo="VACACIONES"):
        ausencia = Ausencia(
            funcionario=funcionario, tipo=tipo, fecha_inicio=inicio, fecha_fin=fin,
            registrado_por=self.delegado, activo=activo,
        )
        ausencia.full_clean()
        ausencia.save()
        return ausencia

    def archivo(self, nombre="captura.png", contenido=b"imagen de prueba"):
        return SimpleUploadedFile(nombre, contenido, content_type="image/png")

    def ajuste(self, funcionario, tipo, fecha=None, activo=True):
        return AjusteDesempeno.objects.create(
            tipo=tipo, funcionario=funcionario, fecha=fecha or date(2026, 8, 10),
            medio="CORREO_DELEGADO", remitente_nombre="Vecina", remitente_contacto="912345678",
            descripcion="Detalle", respaldo=self.archivo(), registrado_por=self.delegado,
            activo=activo,
        )

    def datos_ausencia(self, **cambios):
        datos = {
            "funcionario": self.maria.pk, "tipo": "LICENCIA",
            "fecha_inicio": "2026-11-02", "fecha_fin": "2026-11-06", "observacion": "",
        }
        datos.update(cambios)
        return datos

    def datos_ajuste(self, **cambios):
        datos = {
            "tipo": AjusteDesempeno.FELICITACION, "funcionario": self.maria.pk,
            "fecha": "2026-11-10", "medio": "WHATSAPP_DELEGADO",
            "remitente_nombre": "Juana Pérez", "remitente_contacto": "987654321",
            "descripcion": "Agradece la atención en la delegación.",
            "respaldo": self.archivo(),
        }
        datos.update(cambios)
        return datos


# ============================================================
# 2. MODELO Y SERVICIO DE AUSENCIAS
# ============================================================

class PruebasAusencias(Base):

    def test_CP_AUS_002_dias_habiles_automaticos(self):
        """CP-AUS-002: de lunes a viernes sin feriados son 5 días hábiles; el sábado y domingo no cuentan."""
        ausencia = self.ausencia(self.maria, date(2026, 11, 2), date(2026, 11, 6))
        self.assertEqual(ausencia.dias, 5)

        # De lunes a domingo siguen siendo 5.
        self.assertEqual(self.ausencia(self.pedro, date(2026, 9, 7), date(2026, 9, 13)).dias, 5)

    def test_CP_AUS_003_feriado_no_cuenta(self):
        """CP-AUS-003 (borde): del 14 al 18 de septiembre son 4 días, porque el 18 es feriado."""
        ausencia = self.ausencia(self.maria, date(2026, 9, 14), date(2026, 9, 18))
        self.assertEqual(ausencia.dias, 4)

    def test_CP_AUS_004_rango_sin_dias_habiles(self):
        """CP-AUS-004 (borde): una ausencia solo de sábado y domingo se rechaza."""
        with self.assertRaises(ValidationError) as ctx:
            self.ausencia(self.maria, date(2026, 11, 7), date(2026, 11, 8))
        self.assertIn("fecha_fin", ctx.exception.message_dict)

    def test_CP_AUS_005_fin_antes_del_inicio(self):
        """CP-AUS-005: la fecha de término anterior al inicio se rechaza."""
        with self.assertRaises(ValidationError):
            self.ausencia(self.maria, date(2026, 11, 6), date(2026, 11, 2))

    def test_CP_AUS_006_no_se_traslapan(self):
        """CP-AUS-006: dos ausencias vigentes del mismo funcionario no se cruzan; las anuladas no cuentan."""
        self.ausencia(self.maria, date(2026, 11, 2), date(2026, 11, 6))

        with self.assertRaises(ValidationError) as ctx:
            self.ausencia(self.maria, date(2026, 11, 6), date(2026, 11, 10))
        self.assertIn("Se cruza", str(ctx.exception))

        # Otro funcionario sí puede tener las mismas fechas.
        self.ausencia(self.pedro, date(2026, 11, 2), date(2026, 11, 6))

        # Una ausencia anulada no bloquea.
        Ausencia.objects.filter(funcionario=self.maria).update(activo=False)
        self.ausencia(self.maria, date(2026, 11, 4), date(2026, 11, 10))

    def test_CP_AUS_007_dias_ausencia_recorta_al_periodo(self):
        """CP-AUS-007: dias_ausencia() suma solo los días hábiles dentro del período."""
        # 28-sep (lun) al 2-oct (vie): 3 días en septiembre, 2 en octubre.
        self.ausencia(self.maria, date(2026, 9, 28), date(2026, 10, 2))
        self.ausencia(self.maria, date(2026, 8, 3), date(2026, 8, 4), tipo="ADMINISTRATIVO")
        # Anulada: no cuenta.
        self.ausencia(self.maria, date(2026, 7, 6), date(2026, 7, 10), activo=False)

        self.assertEqual(dias_ausencia(self.maria, date(2026, 7, 1), date(2026, 9, 30)), 5)
        self.assertEqual(dias_ausencia(self.maria, date(2026, 10, 1), date(2026, 12, 31)), 2)
        self.assertEqual(dias_ausencia(self.pedro, date(2026, 7, 1), date(2026, 9, 30)), 0)

    def test_CP_AUS_008_funcionario_sin_delegacion(self):
        """CP-AUS-008: no se registra una ausencia a un funcionario sin delegación."""
        with self.assertRaises(ValidationError) as ctx:
            self.ausencia(self.admin, date(2026, 11, 2), date(2026, 11, 6))
        self.assertIn("funcionario", ctx.exception.message_dict)


# ============================================================
# 3. MODELO Y SERVICIO DE FELICITACIONES Y RECLAMOS
# ============================================================

class PruebasAjustes(Base):

    def test_CP_AJU_005_cumplimiento_final_con_ajustes(self):
        """CP-AJU-005: cuenta solo los vigentes del período y aplica el tope."""
        self.ajuste(self.maria, AjusteDesempeno.FELICITACION)
        self.ajuste(self.maria, AjusteDesempeno.FELICITACION)
        self.ajuste(self.maria, AjusteDesempeno.RECLAMO)
        self.ajuste(self.maria, AjusteDesempeno.RECLAMO, activo=False)
        self.ajuste(self.maria, AjusteDesempeno.FELICITACION, fecha=date(2026, 10, 5))

        desde, hasta = date(2026, 7, 1), date(2026, 9, 30)
        self.assertEqual(contar_ajustes(self.maria, desde, hasta), (2, 1))
        # +20% (2 felicitaciones) - 20% (1 reclamo) = sin cambio.
        self.assertEqual(cumplimiento_final(self.maria, D("0.95"), desde, hasta), D("0.95"))
        # Borde: un total base sobre el tope queda en 120%.
        self.assertEqual(cumplimiento_final(self.maria, D("1.30"), desde, hasta), D("1.20"))

    def test_CP_AJU_006_alerta_rrhh(self):
        """CP-AJU-006: con reclamos en dos trimestres seguidos se marca la alerta."""
        self.ajuste(self.maria, AjusteDesempeno.RECLAMO, fecha=date(2026, 8, 10))
        self.assertFalse(alerta_rrhh(self.maria, hoy=date(2026, 11, 13)))

        self.ajuste(self.maria, AjusteDesempeno.RECLAMO, fecha=date(2026, 11, 3))
        self.assertTrue(alerta_rrhh(self.maria, hoy=date(2026, 11, 13)))

    def test_CP_AJU_007_fecha_futura(self):
        """CP-AJU-007 (borde): una felicitación con fecha futura se rechaza."""
        ajuste = AjusteDesempeno(
            tipo=AjusteDesempeno.FELICITACION, funcionario=self.maria,
            fecha=timezone.localdate() + timedelta(days=1), medio="CORREO_DELEGADO",
            remitente_nombre="Vecino", remitente_contacto="912345678",
            descripcion="Detalle", respaldo=self.archivo(), registrado_por=self.delegado,
        )
        with self.assertRaises(ValidationError) as ctx:
            ajuste.full_clean()
        self.assertIn("fecha", ctx.exception.message_dict)


# ============================================================
# 4. PANTALLAS Y SEGURIDAD (quién registra y quién ve)
# ============================================================

class PruebasPantallas(Base):

    def test_CP_AUS_009_delegado_registra_ausencia(self):
        """CP-AUS-009: el delegado registra una ausencia de su equipo y los días se calculan."""
        self.client.force_login(self.delegado)
        respuesta = self.client.post(reverse("matriz:ausencia_crear"), self.datos_ausencia())

        self.assertRedirects(respuesta, reverse("matriz:ausencia_lista"))
        ausencia = Ausencia.objects.get()
        self.assertEqual(ausencia.dias, 5)
        self.assertEqual(ausencia.registrado_por, self.delegado)
        self.assertEqual(ausencia.delegacion, self.centro)

    def test_CP_AUS_010_reactivar_respeta_el_traslape(self):
        """CP-AUS-010: no se reactiva una ausencia que se cruza con otra vigente."""
        anulada = self.ausencia(self.maria, date(2026, 11, 2), date(2026, 11, 6), activo=False)
        self.ausencia(self.maria, date(2026, 11, 4), date(2026, 11, 10))
        self.client.force_login(self.delegado)

        respuesta = self.client.post(
            reverse("matriz:ausencia_cambiar_estado", args=[anulada.pk]), follow=True,
        )
        anulada.refresh_from_db()
        self.assertFalse(anulada.activo)
        self.assertContains(respuesta, "No se puede reactivar")

    def test_CP_SEG_001_funcionario_no_registra_ausencias(self):
        """CP-SEG-001: un Administrativo no puede registrar ausencias (403)."""
        self.client.force_login(self.maria)
        respuesta = self.client.post(reverse("matriz:ausencia_crear"), self.datos_ausencia())

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Ausencia.objects.exists())

    def test_CP_SEG_002_funcionario_no_registra_felicitaciones(self):
        """CP-SEG-002: el funcionario no puede registrarse una felicitación (403)."""
        self.client.force_login(self.maria)
        respuesta = self.client.post(reverse("matriz:ajuste_crear"), self.datos_ajuste())

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(AjusteDesempeno.objects.exists())

    def test_CP_SEG_003_delegado_de_otra_delegacion(self):
        """CP-SEG-003: la delegada de Pampa no puede registrar a una funcionaria del Centro."""
        self.client.force_login(self.delegado_pampa)
        respuesta = self.client.post(reverse("matriz:ausencia_crear"), self.datos_ausencia())

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("funcionario", respuesta.context["form"].errors)
        self.assertFalse(Ausencia.objects.exists())

    def test_CP_SEG_004_editar_registro_de_otra_delegacion(self):
        """CP-SEG-004: editar o anular una ausencia de otra delegación responde 403."""
        ausencia = self.ausencia(self.maria, date(2026, 11, 2), date(2026, 11, 6))
        self.client.force_login(self.delegado_pampa)

        self.assertEqual(
            self.client.get(reverse("matriz:ausencia_editar", args=[ausencia.pk])).status_code, 403,
        )
        self.assertEqual(
            self.client.post(reverse("matriz:ausencia_cambiar_estado", args=[ausencia.pk])).status_code,
            403,
        )
        ausencia.refresh_from_db()
        self.assertTrue(ausencia.activo)

    def test_CP_SEG_005_nadie_se_registra_a_si_mismo(self):
        """CP-SEG-005 (borde): el delegado no aparece en su propia lista ni puede registrarse."""
        self.client.force_login(self.delegado)
        respuesta = self.client.post(
            reverse("matriz:ajuste_crear"), self.datos_ajuste(funcionario=self.delegado.pk),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("funcionario", respuesta.context["form"].errors)
        self.assertFalse(AjusteDesempeno.objects.exists())

    def test_CP_SEG_006_campos_del_sistema_no_se_alteran_por_post(self):
        """CP-SEG-006: agregar registrado_por, delegacion o dias al POST no tiene efecto."""
        self.client.force_login(self.delegado)
        self.client.post(reverse("matriz:ausencia_crear"), self.datos_ausencia(
            registrado_por=self.admin.pk, delegacion=self.pampa.pk, dias=99,
        ))

        ausencia = Ausencia.objects.get()
        self.assertEqual(ausencia.registrado_por, self.delegado)
        self.assertEqual(ausencia.delegacion, self.centro)
        self.assertEqual(ausencia.dias, 5)

    def test_CP_SEG_007_cada_uno_ve_lo_suyo(self):
        """CP-SEG-007: Admin ve todo; delegado, su delegación; funcionario, solo lo propio."""
        self.ausencia(self.maria, date(2026, 11, 2), date(2026, 11, 6))
        self.ausencia(self.pedro, date(2026, 11, 2), date(2026, 11, 6))
        self.ausencia(self.luis, date(2026, 11, 2), date(2026, 11, 6))
        url = reverse("matriz:ausencia_lista")

        def vistos(usuario):
            self.client.force_login(usuario)
            return sorted(a.funcionario.first_name for a in self.client.get(url).context["ausencias"])

        self.assertEqual(vistos(self.admin), ["Luis", "María", "Pedro"])
        self.assertEqual(vistos(self.delegado), ["María", "Pedro"])
        self.assertEqual(vistos(self.maria), ["María"])
        self.assertEqual(vistos(self.delegado_pampa), ["Luis"])

    def test_CP_SEG_008_descarga_protegida_del_respaldo(self):
        """CP-SEG-008: el respaldo lo descargan el delegado y la afectada; otro funcionario recibe 403."""
        ajuste = self.ajuste(self.maria, AjusteDesempeno.RECLAMO)
        url = reverse("matriz:ajuste_respaldo", args=[ajuste.pk])

        for usuario, esperado in (
            (self.delegado, 200), (self.maria, 200), (self.admin, 200),
            (self.pedro, 403), (self.delegado_pampa, 403),
        ):
            with self.subTest(usuario=usuario.first_name):
                self.client.force_login(usuario)
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, esperado)
                if esperado == 200:
                    self.assertIn("attachment", respuesta["Content-Disposition"])
                    self.assertIn("captura.png", respuesta["Content-Disposition"])
                    respuesta.close()

    def test_CP_AJU_008_delegado_registra_felicitacion(self):
        """CP-AJU-008: el delegado registra una felicitación con respaldo; se guarda el nombre original."""
        self.client.force_login(self.delegado)
        respuesta = self.client.post(reverse("matriz:ajuste_crear"), self.datos_ajuste())

        self.assertRedirects(respuesta, reverse("matriz:ajuste_lista"))
        ajuste = AjusteDesempeno.objects.get()
        self.assertEqual(ajuste.nombre_original, "captura.png")
        self.assertNotIn("captura", ajuste.respaldo.name)
        self.assertEqual(ajuste.registrado_por, self.delegado)

    def test_CP_AJU_009_respaldo_obligatorio(self):
        """CP-AJU-009: sin archivo de respaldo la felicitación no se guarda."""
        self.client.force_login(self.delegado)
        datos = self.datos_ajuste()
        datos.pop("respaldo")
        respuesta = self.client.post(reverse("matriz:ajuste_crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("respaldo", respuesta.context["form"].errors)
        self.assertFalse(AjusteDesempeno.objects.exists())

    def test_CP_AJU_010_respaldo_peligroso(self):
        """CP-AJU-010 (borde): un respaldo .exe o vacío se rechaza."""
        self.client.force_login(self.delegado)

        for archivo in (
            SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"),
            SimpleUploadedFile("vacio.png", b"", content_type="image/png"),
        ):
            with self.subTest(archivo=archivo.name):
                respuesta = self.client.post(
                    reverse("matriz:ajuste_crear"), self.datos_ajuste(respaldo=archivo),
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn("respaldo", respuesta.context["form"].errors)

        self.assertFalse(AjusteDesempeno.objects.exists())

    def test_CP_AJU_011_editar_no_cambia_el_funcionario(self):
        """CP-AJU-011 (borde): al editar no se puede "mover" un reclamo a otra persona."""
        ajuste = self.ajuste(self.maria, AjusteDesempeno.RECLAMO)
        self.client.force_login(self.delegado)

        datos = self.datos_ajuste(tipo=AjusteDesempeno.RECLAMO, funcionario=self.pedro.pk)
        datos.pop("respaldo")
        self.client.post(reverse("matriz:ajuste_editar", args=[ajuste.pk]), datos)

        ajuste.refresh_from_db()
        self.assertEqual(ajuste.funcionario, self.maria)

    def test_CP_SEG_009_menu_segun_perfil(self):
        """CP-SEG-009: el menú muestra "Registrar" solo a quien puede registrar."""
        url = reverse("matriz:ausencia_lista")

        self.client.force_login(self.delegado)
        self.assertContains(self.client.get(url), "Registrar ausencia")

        self.client.force_login(self.maria)
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Registrar ausencia")
