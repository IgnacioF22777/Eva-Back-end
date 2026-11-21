"""
SGR - EVA 3
Pruebas de las alertas de registros sospechosos (R6).

Casos CP-ALE-001 a CP-ALE-020 (normales y de borde). Cada prueba lleva su
descripción como docstring para la matriz de resultado esperado vs.
obtenido del informe.

Semana de prueba: lunes 9 a domingo 15 de noviembre de 2026.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from actividadesAPP.models import RegistroActividad, ZONA_CHILE
from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.models import CatalogoActividad

from .indicadores import (
    CONTACTO_REPETIDO,
    CUPO_MAXIMO,
    DETALLE_COPIADO,
    RAFAGA,
    Umbrales,
    detectar,
)

User = get_user_model()
LUNES = date(2026, 11, 9)
U = Umbrales()  # 3 contactos, 5 ingresos en 10 min, 3 detalles, 3 días al máximo de 7


def momento(dia, hora, minuto=0):
    return datetime(2026, 11, dia, hora, minuto, tzinfo=ZONA_CHILE)


class Fabrica:
    """Registros en memoria con los campos que usan los indicadores."""

    def __init__(self):
        self.pk = 0
        self.ana = SimpleNamespace(pk=1, nombre="Ana")
        self.beto = SimpleNamespace(pk=2, nombre="Beto")

    def __call__(self, funcionario=None, dia=9, hora=10, minuto=0, telefono="912345678",
                 rut="", detalle="", puntua=True, fecha_actividad=None, nombre="María González"):
        self.pk += 1
        funcionario = funcionario or self.ana
        return SimpleNamespace(
            pk=self.pk, funcionario=funcionario, funcionario_id=funcionario.pk,
            fecha_actividad=fecha_actividad or date(2026, 11, dia),
            fecha_ingreso=momento(dia, hora, minuto), puntua=puntua,
            telefono_usuario=telefono, rut_usuario=rut, nombre_usuario=nombre, detalle=detalle,
        )


def indicadores(alertas):
    return sorted(a.indicador for a in alertas)


# ============================================================
# INDICADORES (FUNCIONES PURAS)
# ============================================================

class PruebasContactoRepetido(SimpleTestCase):

    def setUp(self):
        self.r = Fabrica()

    def test_CP_ALE_001_tres_registros_mismo_telefono(self):
        """CP-ALE-001: 3 registros que suman con el mismo teléfono en la semana generan una alerta con los 3 registros."""
        registros = [self.r(dia=9 + i, hora=10, telefono="+56 9 1234 5678") for i in range(3)]
        alertas = detectar(registros, U, [CONTACTO_REPETIDO])
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0].cantidad, 3)
        self.assertEqual(alertas[0].semana, LUNES)

    def test_CP_ALE_002_borde_dos_registros_no_alertan(self):
        """CP-ALE-002 (borde): con 2 registros del mismo contacto (bajo el umbral de 3) no hay alerta."""
        registros = [self.r(dia=9 + i) for i in range(2)]
        self.assertEqual(detectar(registros, U, [CONTACTO_REPETIDO]), [])

    def test_CP_ALE_003_borde_semanas_distintas_y_sin_puntaje(self):
        """CP-ALE-003 (borde): el mismo contacto repartido en dos semanas, o en registros que no suman, no alerta."""
        registros = [self.r(dia=13), self.r(dia=14), self.r(dia=16)]  # vie, sáb y el lunes siguiente
        self.assertEqual(detectar(registros, U, [CONTACTO_REPETIDO]), [])
        sin_puntaje = [self.r(dia=10 + i, puntua=False) for i in range(4)]
        self.assertEqual(detectar(sin_puntaje, U, [CONTACTO_REPETIDO]), [])

    def test_CP_ALE_004_rut_prima_sobre_telefono_y_sin_contacto_no_compara(self):
        """CP-ALE-004: con RUT se compara por RUT aunque cambie el teléfono; sin RUT ni teléfono no se compara."""
        con_rut = [self.r(dia=9 + i, rut="12.345.678-5", telefono=f"91111111{i}") for i in range(3)]
        self.assertEqual(len(detectar(con_rut, U, [CONTACTO_REPETIDO])), 1)
        sin_contacto = [self.r(dia=9 + i, telefono="", rut="") for i in range(5)]
        self.assertEqual(detectar(sin_contacto, U, [CONTACTO_REPETIDO]), [])

    def test_CP_ALE_005_cada_funcionario_por_separado(self):
        """CP-ALE-005: dos funcionarios que atienden al mismo vecino no se suman entre sí."""
        registros = [self.r(dia=9), self.r(dia=10), self.r(funcionario=self.r.beto, dia=11)]
        self.assertEqual(detectar(registros, U, [CONTACTO_REPETIDO]), [])


class PruebasRafaga(SimpleTestCase):

    def setUp(self):
        self.r = Fabrica()

    def test_CP_ALE_006_cinco_ingresos_en_diez_minutos(self):
        """CP-ALE-006: 5 ingresos entre las 10:00 y las 10:10 forman una ráfaga."""
        registros = [self.r(hora=10, minuto=m, telefono=f"9123456{m:02d}") for m in (0, 2, 5, 8, 10)]
        alertas = detectar(registros, U, [RAFAGA])
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0].cantidad, 5)

    def test_CP_ALE_007_borde_once_minutos_no_alerta(self):
        """CP-ALE-007 (borde): 5 ingresos repartidos en 11 minutos no son ráfaga; 4 ingresos en 1 minuto tampoco."""
        repartidos = [self.r(hora=10, minuto=m) for m in (0, 3, 6, 9, 11)]
        self.assertEqual(detectar(repartidos, U, [RAFAGA]), [])
        cuatro = [self.r(hora=12, minuto=1) for _ in range(4)]
        self.assertEqual(detectar(cuatro, U, [RAFAGA]), [])

    def test_CP_ALE_008_dos_rafagas_separadas(self):
        """CP-ALE-008: dos bloques de 5 ingresos separados por una hora son dos ráfagas, no una."""
        registros = [self.r(hora=10, minuto=m) for m in range(5)] + [self.r(hora=11, minuto=m) for m in range(5)]
        alertas = detectar(registros, U, [RAFAGA])
        self.assertEqual([a.cantidad for a in alertas], [5, 5])

    def test_CP_ALE_009_rafaga_larga_es_una_sola_alerta(self):
        """CP-ALE-009: 8 ingresos seguidos, uno por minuto, son una sola ráfaga de 8."""
        registros = [self.r(hora=15, minuto=m) for m in range(8)]
        alertas = detectar(registros, U, [RAFAGA])
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0].cantidad, 8)


class PruebasDetalleYCupo(SimpleTestCase):

    def setUp(self):
        self.r = Fabrica()

    def test_CP_ALE_010_detalle_copiado_ignora_mayusculas_y_espacios(self):
        """CP-ALE-010: el mismo detalle con distinta capitalización o espacios cuenta como copiado."""
        textos = ["Visita a vecina por luminaria", "visita a  vecina por luminaria", "VISITA A VECINA POR LUMINARIA "]
        registros = [self.r(dia=9 + i, detalle=t, telefono=f"91234567{i}") for i, t in enumerate(textos)]
        alertas = detectar(registros, U, [DETALLE_COPIADO])
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0].cantidad, 3)

    def test_CP_ALE_011_borde_detalles_cortos_o_vacios_no_alertan(self):
        """CP-ALE-011 (borde): detalles vacíos o cortos («visita», menos de 15 letras) no se comparan."""
        registros = [self.r(dia=9 + i, detalle=d, telefono=f"91234567{i}") for i, d in enumerate(["", "visita", "", "visita"])]
        self.assertEqual(detectar(registros, U, [DETALLE_COPIADO]), [])

    def test_CP_ALE_012_cupo_maximo_tres_dias(self):
        """CP-ALE-012: 7 ingresos en 3 días de la misma semana generan la alerta de cupo al máximo."""
        registros = [self.r(dia=d, hora=9 + i, telefono=f"9{d}{i}000000") for d in (9, 10, 11) for i in range(7)]
        alertas = detectar(registros, U, [CUPO_MAXIMO])
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0].cantidad, 21)
        self.assertIn("09-11, 10-11, 11-11", alertas[0].descripcion)

    def test_CP_ALE_013_borde_dos_dias_o_seis_ingresos_no_alertan(self):
        """CP-ALE-013 (borde): 2 días con 7 ingresos, o 3 días con 6, no alertan."""
        dos_dias = [self.r(dia=d, hora=9 + i) for d in (9, 10) for i in range(7)]
        self.assertEqual(detectar(dos_dias, U, [CUPO_MAXIMO]), [])
        seis = [self.r(dia=d, hora=9 + i) for d in (9, 10, 11) for i in range(6)]
        self.assertEqual(detectar(seis, U, [CUPO_MAXIMO]), [])

    def test_CP_ALE_014_umbrales_configurables_y_validos(self):
        """CP-ALE-014: los umbrales se pueden cambiar (2 contactos alertan con umbral 2) y un umbral 0 se rechaza."""
        registros = [self.r(dia=9), self.r(dia=10)]
        self.assertEqual(len(detectar(registros, Umbrales(contacto=2), [CONTACTO_REPETIDO])), 1)
        with self.assertRaises(ValueError):
            Umbrales(rafaga=0)

    def test_CP_ALE_015_registro_normal_no_genera_alertas(self):
        """CP-ALE-015: una semana normal (vecinos distintos, horas espaciadas, detalles distintos) no genera ninguna alerta."""
        registros = [
            self.r(dia=9 + i % 5, hora=9 + i, telefono=f"98765{i:04d}", detalle=f"Atención número {i} a vecino del sector")
            for i in range(10)
        ]
        self.assertEqual(detectar(registros, U), [])


# ============================================================
# PANTALLA, PERMISOS Y ÁMBITO
# ============================================================

@override_settings(MAX_INGRESOS_DIARIOS=7, SGR_ALERTA_CONTACTO=3)
class PruebasPantallaAlertas(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        def delegacion(nombre):
            return Delegacion.objects.create(
                nombre=nombre, direccion="Calle 1", encargado=f"Delegado {nombre}",
                email=f"{nombre.lower()}@laserena.cl", telefono="512111111", celular="911111111",
            )

        def persona(username, rut, perfil, deleg):
            usuario = User.objects.create_user(username=username, password="Clave-Segura-2026",
                                               first_name=username.capitalize(), last_name="Prueba")
            usuario.groups.add(Group.objects.get(name=perfil))
            PerfilUsuario.objects.create(usuario=usuario, rut=rut, delegacion=deleg)
            return usuario

        cls.centro = delegacion("Centro")
        cls.antena = delegacion("Antena")
        cls.delegada = persona("delegada", "11111111-1", "Supervisor", cls.centro)
        cls.ana = persona("ana", "12345678-5", "Administrativo", cls.centro)
        cls.luis = persona("luis", "22222222-2", "Administrativo", cls.antena)
        cls.sin_deleg = persona("sindeleg", "33333333-3", "Supervisor", None)
        cls.admin = User.objects.create_superuser("admin", "admin@laserena.cl", "Clave-Segura-2026")
        cls.visita = CatalogoActividad.objects.create(codigo="VIS", nombre="Visita", tipo_gestion="EJECUCION")

    def setUp(self):
        reloj = patch("django.utils.timezone.now", return_value=momento(11, 12))
        reloj.start()
        self.addCleanup(reloj.stop)

    def repetir_contacto(self, usuario, veces=3, telefono="912345678"):
        return [
            RegistroActividad.objects.create(
                funcionario=usuario.perfil, actividad=self.visita, fecha_actividad=date(2026, 11, 9 + i % 3),
                nombre_usuario="María González", telefono_usuario=telefono, detalle=f"Gestión {i}",
            )
            for i in range(veces)
        ]

    def ver(self, usuario, **parametros):
        self.client.force_login(usuario)
        return self.client.get(reverse("alertas:lista"), parametros)

    def test_CP_ALE_016_delegado_ve_alertas_de_su_delegacion(self):
        """CP-ALE-016: el delegado ve la alerta de contacto repetido de su funcionaria y no la de otra delegación."""
        self.repetir_contacto(self.ana)
        self.repetir_contacto(self.luis, telefono="987654321")
        respuesta = self.ver(self.delegada)
        self.assertEqual(respuesta.status_code, 200)
        alertas = respuesta.context["alertas"]
        self.assertEqual([a.funcionario.usuario for a in alertas], [self.ana])
        self.assertContains(respuesta, "Contacto repetido")
        self.assertContains(respuesta, alertas[0].registros[0].codigo)

    def test_CP_ALE_017_administrador_ve_todas_y_filtra(self):
        """CP-ALE-017: el Administrador ve las alertas de todas las delegaciones y puede filtrar por delegación e indicador."""
        self.repetir_contacto(self.ana)
        self.repetir_contacto(self.luis, telefono="987654321")
        self.assertEqual(len(self.ver(self.admin).context["alertas"]), 2)
        filtrada = self.ver(self.admin, delegacion=self.antena.pk)
        self.assertEqual([a.funcionario.usuario for a in filtrada.context["alertas"]], [self.luis])
        self.assertEqual(self.ver(self.admin, indicador=RAFAGA).context["alertas"], [])

    def test_CP_ALE_018_accesos_denegados(self):
        """CP-ALE-018: el Administrativo recibe 403, el Supervisor sin delegación 403 y sin sesión se pide iniciar sesión."""
        self.assertEqual(self.ver(self.ana).status_code, 403)
        self.assertEqual(self.ver(self.sin_deleg).status_code, 403)
        self.client.logout()
        respuesta = self.client.get(reverse("alertas:lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("login", respuesta.url)

    def test_CP_ALE_019_rechazados_y_anulados_no_cuentan(self):
        """CP-ALE-019 (borde): si uno de los 3 registros se rechaza o se anula, la alerta desaparece."""
        registros = self.repetir_contacto(self.ana)
        self.assertEqual(len(self.ver(self.delegada).context["alertas"]), 1)
        RegistroActividad.objects.filter(pk=registros[0].pk).update(estado_verificacion=RegistroActividad.RECHAZADA)
        self.assertEqual(self.ver(self.delegada).context["alertas"], [])
        RegistroActividad.objects.filter(pk=registros[0].pk).update(
            estado_verificacion=RegistroActividad.PENDIENTE, activo=False)
        self.assertEqual(self.ver(self.delegada).context["alertas"], [])

    def test_CP_ALE_020_rango_de_fechas(self):
        """CP-ALE-020 (borde): fuera del rango no hay alertas; fechas invertidas se corrigen y el rango se limita a 92 días."""
        self.repetir_contacto(self.ana)
        fuera = self.ver(self.delegada, desde="2026-10-01", hasta="2026-10-31")
        self.assertEqual(fuera.context["alertas"], [])
        invertido = self.ver(self.delegada, desde="2026-11-11", hasta="2026-11-01")
        self.assertEqual(invertido.context["filtros"]["desde"], date(2026, 11, 1))
        self.assertEqual(len(invertido.context["alertas"]), 1)
        largo = self.ver(self.delegada, desde="2026-01-01", hasta="2026-11-11")
        self.assertEqual(largo.context["filtros"]["desde"], date(2026, 11, 11) - timedelta(days=91))
