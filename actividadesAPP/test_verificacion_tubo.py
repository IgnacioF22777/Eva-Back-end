"""Pruebas Eva 3: verificación, bloqueo tras aprobar, tubo, evidencias,
código automático, metas automáticas y ausencias en «Mi matriz».

Los ID (CP-VER, CP-BLQ, CP-TUB, CP-EVI, CP-COD, CP-AUT, CP-AUS) se
registran en la matriz de resultado esperado vs. obtenido del informe.
"""

import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from matrizAPP.models import Ausencia
from seguridadAPP.models import Cargo, PerfilUsuario
from seguridadAPP.roles import sincronizar_roles
from sgr_maestrosAPP.models import CatalogoActividad, Meta, Periodo

from .models import RegistroActividad, ZONA_CHILE
from .puntajes import cumplimiento_soluciones_tubo, obtener_mi_matriz

User = get_user_model()

# Lunes 9 de noviembre de 2026, 12:00 en Chile.
AHORA = datetime(2026, 11, 9, 12, 0, tzinfo=ZONA_CHILE)
CARPETA_MEDIA = tempfile.mkdtemp(prefix="sgr_evidencias_")
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def crear_delegacion(nombre):
    return Delegacion.objects.create(
        nombre=nombre, direccion="Calle 1", encargado=f"Delegado {nombre}",
        email=f"{nombre.lower()}@laserena.cl", telefono="512111111", celular="911111111",
    )


def crear_funcionario(username, rut, perfil, delegacion, cargo=None):
    usuario = User.objects.create_user(
        username=username, password="Clave-Segura-2026",
        first_name=username.capitalize(), last_name="Prueba",
    )
    usuario.groups.add(Group.objects.get(name=perfil))
    PerfilUsuario.objects.create(usuario=usuario, rut=rut, delegacion=delegacion, cargo=cargo)
    return usuario


@override_settings(MEDIA_ROOT=CARPETA_MEDIA, MAX_INGRESOS_DIARIOS=7)
class BaseSeguimiento(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        cls.centro = crear_delegacion("Centro")
        cls.antena = crear_delegacion("Antena")
        cls.cargo = Cargo.objects.create(nombre="Gestor Social")

        cls.delegada = crear_funcionario("delegada", "11111111-1", "Supervisor", cls.centro)
        cls.ana = crear_funcionario("ana", "12345678-5", "Administrativo", cls.centro, cls.cargo)
        cls.beto = crear_funcionario("beto", "22222222-2", "Administrativo", cls.centro, cls.cargo)
        cls.delegado_antena = crear_funcionario("antena", "33333333-3", "Supervisor", cls.antena)
        cls.luis = crear_funcionario("luis", "44444444-4", "Administrativo", cls.antena)
        cls.admin = User.objects.create_superuser("admin", "admin@laserena.cl", "Clave-Segura-2026")

        cls.visita = CatalogoActividad.objects.create(
            codigo="VIS", nombre="Visita a terreno", tipo_gestion="EJECUCION",
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(CARPETA_MEDIA, ignore_errors=True)

    def setUp(self):
        reloj = patch("django.utils.timezone.now", return_value=AHORA)
        reloj.start()
        self.addCleanup(reloj.stop)

    def registro(self, usuario=None, **cambios):
        datos = {
            "funcionario": (usuario or self.ana).perfil,
            "actividad": self.visita,
            "fecha_actividad": date(2026, 11, 9),
            "nombre_usuario": "María González",
            "telefono_usuario": "912345678",
            "detalle": "Visita a vecina de Las Compañías",
        }
        datos.update(cambios)
        return RegistroActividad.objects.create(**datos)


# ============================================================
# CÓDIGO AUTOMÁTICO
# ============================================================

class PruebasCodigo(BaseSeguimiento):

    def test_CP_COD_001_codigo_generado_por_el_servidor(self):
        """CP-COD-001: cada registro recibe ACT-AAAA-000000 y es único."""
        a = self.registro()
        b = self.registro()
        self.assertEqual(a.codigo, f"ACT-2026-{a.pk:06d}")
        self.assertNotEqual(a.codigo, b.codigo)
        a.refresh_from_db()
        self.assertEqual(a.codigo, f"ACT-2026-{a.pk:06d}")

    def test_CP_COD_002_codigo_no_se_envia_por_post(self):
        """CP-COD-002 (seguridad): un código enviado en el POST se ignora."""
        self.client.force_login(self.ana)
        self.client.post(reverse("actividades:crear"), {
            "actividad": self.visita.pk, "fecha_actividad": "2026-11-09",
            "solicitante_tipo": "VECINO", "nombre_usuario": "Pedro", "telefono_usuario": "912345678",
            "codigo": "ACT-FALSO-1", "estado_verificacion": "APROBADA",
        })
        registro = RegistroActividad.objects.get()
        self.assertTrue(registro.codigo.startswith("ACT-2026-"))
        self.assertEqual(registro.estado_verificacion, RegistroActividad.PENDIENTE)


# ============================================================
# VERIFICACIÓN Y BLOQUEO POSTERIOR A LA APROBACIÓN
# ============================================================

class PruebasVerificacion(BaseSeguimiento):

    def test_CP_VER_001_nuevo_registro_queda_pendiente(self):
        """CP-VER-001: todo registro nuevo queda pendiente de verificación."""
        self.assertEqual(self.registro().estado_verificacion, RegistroActividad.PENDIENTE)

    def test_CP_VER_002_delegada_aprueba(self):
        """CP-VER-002: la delegada aprueba un registro de su equipo."""
        registro = self.registro()
        self.client.force_login(self.delegada)
        self.client.post(reverse("actividades:verificar", args=[registro.pk]), {"estado": "APROBADA"})
        registro.refresh_from_db()
        self.assertEqual(registro.estado_verificacion, RegistroActividad.APROBADA)
        self.assertEqual(registro.verificado_por, self.delegada)
        self.assertIsNotNone(registro.fecha_verificacion)

    def test_CP_VER_003_rechazo_exige_observacion(self):
        """CP-VER-003 (borde): rechazar o pedir antecedentes sin observación se rechaza."""
        registro = self.registro()
        for estado in ("RECHAZADA", "ANTECEDENTES"):
            with self.subTest(estado=estado):
                with self.assertRaises(ValidationError):
                    registro.verificar(self.delegada, estado, "   ")
        registro.refresh_from_db()
        self.assertEqual(registro.estado_verificacion, RegistroActividad.PENDIENTE)

    def test_CP_VER_004_estado_invalido(self):
        """CP-VER-004 (borde): un estado inexistente se rechaza."""
        with self.assertRaises(ValidationError):
            self.registro().verificar(self.delegada, "SUPERAPROBADA")

    def test_CP_VER_005_funcionario_no_verifica(self):
        """CP-VER-005 (permisos): un Administrativo no accede a la verificación (403)."""
        registro = self.registro(self.beto)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(reverse("actividades:verificacion")).status_code, 403)
        respuesta = self.client.post(
            reverse("actividades:verificar", args=[registro.pk]), {"estado": "APROBADA"},
        )
        self.assertEqual(respuesta.status_code, 403)
        registro.refresh_from_db()
        self.assertEqual(registro.estado_verificacion, RegistroActividad.PENDIENTE)

    def test_CP_VER_006_delegado_de_otra_delegacion(self):
        """CP-VER-006 (permisos): el delegado de otra delegación recibe 404 y no verifica."""
        registro = self.registro()
        self.client.force_login(self.delegado_antena)
        respuesta = self.client.post(
            reverse("actividades:verificar", args=[registro.pk]), {"estado": "APROBADA"},
        )
        self.assertEqual(respuesta.status_code, 404)
        registro.refresh_from_db()
        self.assertEqual(registro.estado_verificacion, RegistroActividad.PENDIENTE)

    def test_CP_VER_007_nadie_se_verifica_a_si_mismo(self):
        """CP-VER-007 (borde): la delegada no aprueba sus propios registros."""
        propio = self.registro(self.delegada)
        with self.assertRaises(ValidationError):
            propio.verificar(self.delegada, RegistroActividad.APROBADA)
        self.client.force_login(self.delegada)
        respuesta = self.client.get(reverse("actividades:verificacion") + "?estado=TODOS")
        self.assertNotIn(propio, list(respuesta.context["registros"]))

    def test_CP_VER_008_antecedentes_y_correccion(self):
        """CP-VER-008: tras pedir antecedentes, la corrección vuelve a pendiente."""
        registro = self.registro()
        registro.verificar(self.delegada, RegistroActividad.ANTECEDENTES, "Falta el teléfono correcto")
        self.client.force_login(self.ana)
        self.client.post(reverse("actividades:editar", args=[registro.pk]), {
            "actividad": self.visita.pk, "fecha_actividad": "2026-11-09",
            "solicitante_tipo": "VECINO", "nombre_usuario": "María González",
            "telefono_usuario": "987654321", "detalle": "Se corrigió el teléfono",
        })
        registro.refresh_from_db()
        self.assertEqual(registro.estado_verificacion, RegistroActividad.PENDIENTE)
        self.assertEqual(registro.telefono_usuario, "987654321")

    def test_CP_VER_009_verifica_aunque_la_semana_este_cerrada(self):
        """CP-VER-009 (borde): el cierre semanal no impide que el delegado verifique."""
        registro = self.registro()
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 25, 9, 0, tzinfo=ZONA_CHILE)):
            registro.verificar(self.delegada, RegistroActividad.APROBADA)
        registro.refresh_from_db()
        self.assertTrue(registro.esta_aprobado)

    def test_CP_BLQ_001_aprobado_no_se_modifica(self):
        """CP-BLQ-001: un registro aprobado no se puede editar (modelo y vista)."""
        registro = self.registro()
        registro.verificar(self.delegada, RegistroActividad.APROBADA)

        registro.detalle = "Cambio posterior"
        with self.assertRaisesMessage(ValidationError, "aprobado no se puede modificar"):
            registro.save()

        self.client.force_login(self.ana)
        respuesta = self.client.post(reverse("actividades:editar", args=[registro.pk]), {
            "actividad": self.visita.pk, "fecha_actividad": "2026-11-09",
            "solicitante_tipo": "VECINO", "nombre_usuario": "Otro", "telefono_usuario": "912345678",
        })
        self.assertRedirects(respuesta, reverse("actividades:lista"))
        registro.refresh_from_db()
        self.assertEqual(registro.nombre_usuario, "María González")

    def test_CP_BLQ_002_aprobado_no_se_da_de_baja(self):
        """CP-BLQ-002: un registro aprobado no se puede dar de baja."""
        registro = self.registro()
        registro.verificar(self.delegada, RegistroActividad.APROBADA)
        self.client.force_login(self.ana)
        self.client.post(reverse("actividades:cambiar_estado", args=[registro.pk]))
        registro.refresh_from_db()
        self.assertTrue(registro.activo)

    def test_CP_BLQ_003_aprobado_no_se_vuelve_a_verificar(self):
        """CP-BLQ-003 (borde): un aprobado no puede pasar a rechazado."""
        registro = self.registro()
        registro.verificar(self.delegada, RegistroActividad.APROBADA)
        with self.assertRaises(ValidationError):
            registro.verificar(self.admin, RegistroActividad.RECHAZADA, "Revisión tardía")

    def test_CP_VER_010_solo_aprobados_suman(self):
        """CP-VER-010: en «Mi matriz» solo cuentan los registros aprobados."""
        periodo = Periodo.objects.create(
            codigo="2026-T4", nombre="Cuarto trimestre",
            fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 12, 31),
        )
        Meta.objects.create(
            codigo="M-VIS", nombre="Visitas", periodo=periodo, actividad=self.visita,
            cargo=self.cargo, valor_objetivo=4, ponderacion=100,
        )
        aprobado = self.registro()
        self.registro()  # pendiente: no suma
        aprobado.verificar(self.delegada, RegistroActividad.APROBADA)

        matriz = obtener_mi_matriz(self.ana.perfil, periodo)
        self.assertEqual(matriz["items"][0]["avance"], 1)
        self.assertEqual(matriz["items"][0]["cumplimiento"], Decimal("25.00"))


# ============================================================
# TUBO DE SEGUIMIENTO
# ============================================================

class PruebasTubo(BaseSeguimiento):

    def test_CP_TUB_001_todo_el_equipo_consulta(self):
        """CP-TUB-001: Ana ve en el tubo el caso de Beto (misma delegación)."""
        caso = self.registro(self.beto, ingresa_tubo=True, nombre_usuario="Juan Pérez")
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("actividades:tubo"))
        self.assertContains(respuesta, caso.codigo)

    def test_CP_TUB_002_otra_delegacion_no_ve(self):
        """CP-TUB-002 (ámbito): Luis (Antena) no ve casos del Centro."""
        caso = self.registro(ingresa_tubo=True)
        self.client.force_login(self.luis)
        self.assertNotContains(self.client.get(reverse("actividades:tubo")), caso.codigo)

    def test_CP_TUB_003_actividad_puede_no_ingresar(self):
        """CP-TUB-003: una actividad sin «ingresa al tubo» no aparece en el tubo."""
        caso = self.registro(ingresa_tubo=False)
        self.client.force_login(self.ana)
        self.assertNotContains(self.client.get(reverse("actividades:tubo")), caso.codigo)

    def test_CP_TUB_004_busqueda_dinamica(self):
        """CP-TUB-004: la búsqueda parcial filtra por código, RUT y nombre."""
        juan = self.registro(ingresa_tubo=True, nombre_usuario="Juan Pérez", rut_usuario="12.345.678-5")
        rosa = self.registro(ingresa_tubo=True, nombre_usuario="Rosa Araya", rut_usuario="")
        self.client.force_login(self.ana)
        url = reverse("actividades:tubo")

        for texto, esperado, excluido in (
            ("juan", juan, rosa),
            ("12345678", juan, rosa),
            ("12.345.678-5", juan, rosa),
            (rosa.codigo, rosa, juan),
        ):
            with self.subTest(texto=texto):
                respuesta = self.client.get(url, {"q": texto, "parcial": "1"})
                self.assertTemplateUsed(respuesta, "actividades/_tubo_filas.html")
                self.assertTemplateNotUsed(respuesta, "base.html")
                self.assertContains(respuesta, esperado.codigo)
                self.assertNotContains(respuesta, excluido.codigo)

    def test_CP_TUB_005_filtros_funcionario_fecha_estado(self):
        """CP-TUB-005: filtros por funcionario, rango de fechas y estado."""
        a = self.registro(ingresa_tubo=True, fecha_actividad=date(2026, 11, 2))
        b = self.registro(self.beto, ingresa_tubo=True, estado_tubo="SOLUCIONADO")
        self.client.force_login(self.ana)
        url = reverse("actividades:tubo")

        r = self.client.get(url, {"funcionario": self.beto.perfil.pk})
        self.assertContains(r, b.codigo)
        self.assertNotContains(r, a.codigo)

        r = self.client.get(url, {"desde": "2026-11-05", "hasta": "2026-11-09"})
        self.assertContains(r, b.codigo)
        self.assertNotContains(r, a.codigo)

        r = self.client.get(url, {"estado": "SOLUCIONADO"})
        self.assertContains(r, b.codigo)
        self.assertNotContains(r, a.codigo)

    def test_CP_TUB_006_solo_el_dueno_actualiza(self):
        """CP-TUB-006 (permisos): Ana no cambia el estado del caso de Beto (403)."""
        caso = self.registro(self.beto, ingresa_tubo=True)
        self.client.force_login(self.ana)
        respuesta = self.client.post(
            reverse("actividades:tubo_estado", args=[caso.pk]), {"estado_tubo": "SOLUCIONADO"},
        )
        self.assertEqual(respuesta.status_code, 403)
        caso.refresh_from_db()
        self.assertEqual(caso.estado_tubo, RegistroActividad.TUBO_EN_PROCESO)

    def test_CP_TUB_007_dueno_soluciona_y_fecha_automatica(self):
        """CP-TUB-007: al solucionar se fija la fecha; al reabrir se borra."""
        caso = self.registro(ingresa_tubo=True)
        self.client.force_login(self.ana)
        self.client.post(reverse("actividades:tubo_estado", args=[caso.pk]), {"estado_tubo": "SOLUCIONADO"})
        caso.refresh_from_db()
        self.assertEqual(caso.fecha_solucion, date(2026, 11, 9))
        self.client.post(reverse("actividades:tubo_estado", args=[caso.pk]), {"estado_tubo": "EN_PROCESO"})
        caso.refresh_from_db()
        self.assertIsNone(caso.fecha_solucion)

    def test_CP_TUB_008_aprobado_no_cambia_en_tubo(self):
        """CP-TUB-008: un caso aprobado ya no cambia de estado en el tubo."""
        caso = self.registro(ingresa_tubo=True, estado_tubo="SOLUCIONADO")
        caso.verificar(self.delegada, RegistroActividad.APROBADA)
        with self.assertRaises(ValidationError):
            caso.cambiar_estado_tubo(RegistroActividad.TUBO_EN_PROCESO)

    def test_CP_TUB_009_rut_invalido(self):
        """CP-TUB-009 (validación): un RUT con dígito verificador erróneo se rechaza."""
        with self.assertRaises(ValidationError):
            self.registro(ingresa_tubo=True, rut_usuario="12.345.678-9")


# ============================================================
# EVIDENCIAS
# ============================================================

class PruebasEvidencia(BaseSeguimiento):

    def subir(self, usuario, archivo):
        self.client.force_login(usuario)
        return self.client.post(reverse("actividades:crear"), {
            "actividad": self.visita.pk, "fecha_actividad": "2026-11-09",
            "solicitante_tipo": "VECINO", "nombre_usuario": "Pedro Rojas",
            "telefono_usuario": "912345678", "evidencia": archivo,
        })

    def test_CP_EVI_001_evidencia_y_acceso(self):
        """CP-EVI-001: la ven la dueña, su delegada y el admin; otro funcionario o delegado, 403."""
        self.subir(self.ana, SimpleUploadedFile("acta.png", PNG, content_type="image/png"))
        registro = RegistroActividad.objects.get()
        self.assertEqual(registro.evidencia_nombre, "acta.png")
        self.assertNotIn("acta", registro.evidencia.name)
        url = reverse("actividades:evidencia", args=[registro.pk])

        for usuario, esperado in (
            (self.ana, 200), (self.delegada, 200), (self.admin, 200),
            (self.beto, 403), (self.delegado_antena, 403),
        ):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, esperado)
                if esperado == 200:
                    self.assertIn("acta.png", respuesta["Content-Disposition"])
                    # Se consume el archivo (no se llama a close(): ver CP-SEG-008).
                    self.assertTrue(b"".join(respuesta.streaming_content))

    def test_CP_EVI_002_archivo_peligroso_o_vacio(self):
        """CP-EVI-002 (seguridad): .exe o archivo vacío se rechazan."""
        for archivo in (
            SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"),
            SimpleUploadedFile("vacio.png", b"", content_type="image/png"),
        ):
            with self.subTest(archivo=archivo.name):
                respuesta = self.subir(self.ana, archivo)
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn("evidencia", respuesta.context["form"].errors)
        self.assertFalse(RegistroActividad.objects.exists())


# ============================================================
# METAS AUTOMÁTICAS Y AUSENCIAS
# ============================================================

class PruebasMetasAutomaticas(BaseSeguimiento):

    def test_CP_AUT_001_formula_soluciones_tubo(self):
        """CP-AUT-001 (borde): 8/10 con meta 80 % = 100 %; sin ingresos = 0 %; tope 120 %."""
        self.assertEqual(cumplimiento_soluciones_tubo(10, 8, "0.80"), Decimal("100.00"))
        self.assertEqual(cumplimiento_soluciones_tubo(10, 4, "0.80"), Decimal("50.00"))
        self.assertEqual(cumplimiento_soluciones_tubo(0, 0, "0.80"), Decimal("0.00"))
        self.assertEqual(cumplimiento_soluciones_tubo(5, 5, "0.80"), Decimal("120.00"))

    def test_CP_AUT_002_matriz_con_metas_automaticas(self):
        """CP-AUT-002: «Mi matriz» calcula «Soluciones de ingresos al tubo» y «Emergencia»."""
        periodo = Periodo.objects.create(
            codigo="2026-T4", nombre="T4", fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 12, 31),
        )
        soluciones = CatalogoActividad.objects.create(codigo="SGR-SOLUCIONES-TUBO", nombre="Soluciones")
        emergencia = CatalogoActividad.objects.create(codigo="SGR-EMERGENCIA", nombre="Emergencia")
        Meta.objects.create(codigo="M1", nombre="Sol", periodo=periodo, actividad=soluciones,
                            cargo=self.cargo, valor_objetivo=Decimal("0.80"), ponderacion=50)
        Meta.objects.create(codigo="M2", nombre="Eme", periodo=periodo, actividad=emergencia,
                            cargo=self.cargo, valor_objetivo=0, ponderacion=50)

        for estado in ("SOLUCIONADO", "SOLUCIONADO", "EN_PROCESO", "SOLUCIONADO"):
            self.registro(ingresa_tubo=True, estado_tubo=estado)

        matriz = obtener_mi_matriz(self.ana.perfil, periodo)
        items = {i["actividad"].codigo: i for i in matriz["items"]}
        # 3 de 4 = 75 % ; 75 / 80 = 93,75 %
        self.assertEqual(items["SGR-SOLUCIONES-TUBO"]["cumplimiento"], Decimal("93.75"))
        self.assertTrue(items["SGR-SOLUCIONES-TUBO"]["automatica"])
        self.assertEqual(items["SGR-EMERGENCIA"]["cumplimiento"], Decimal("100.00"))

    def test_CP_AUS_INT_001_ausencia_ajusta_mi_matriz(self):
        """CP-AUS-INT-001: la ausencia registrada por la delegada baja la meta en «Mi matriz»."""
        periodo = Periodo.objects.create(
            codigo="2026-NOV", nombre="Noviembre", fecha_inicio=date(2026, 11, 2), fecha_fin=date(2026, 11, 13),
        )
        Meta.objects.create(codigo="M-V", nombre="Visitas", periodo=periodo, actividad=self.visita,
                            cargo=self.cargo, valor_objetivo=10, ponderacion=100)
        Ausencia.objects.create(
            funcionario=self.ana, delegacion=self.centro, tipo=Ausencia.TIPOS[0][0],
            fecha_inicio=date(2026, 11, 2), fecha_fin=date(2026, 11, 6),
            registrado_por=self.delegada,
        )
        self.client.force_login(self.ana)
        respuesta = self.client.get(reverse("actividades:matriz"), {"periodo": periodo.pk})
        matriz = respuesta.context["matriz"]
        self.assertEqual(matriz["dias_ausencia"], 5)
        self.assertEqual(matriz["items"][0]["objetivo_ajustado"], Decimal("5.00"))
        self.assertTrue(respuesta.context["ausencias_integradas"])
