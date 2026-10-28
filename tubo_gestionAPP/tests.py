from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import (
    ADMINISTRADOR,
    ADMINISTRATIVO,
    SUPERVISOR,
)
from seguridadAPP.roles import sincronizar_roles

from .models import Compromiso

from .validadores import (
    validar_credenciales,
    validar_rut_chileno,
    verificar_ambito_delegacion,
    validar_suma_ponderaciones,
    validar_rango_fechas,
    calcular_dias_computables,
    validar_codigo_unico_catalogo,
    verificar_eliminacion_cargo,
    desactivar_cargo
)

class PlanPruebasUnitariasSGR(SimpleTestCase):

    # --- AUTENTICACIÓN / LOGIN (Camilo) ---
    def test_CP_LOG_001_login_exitoso(self):
        """CP-LOG-001: Inicio de sesión con credenciales correctas"""
        self.assertTrue(validar_credenciales(usuario_registrado=True, clave_correcta=True, esta_activo=True))

    def test_CP_LOG_002_login_clave_incorrecta(self):
        """CP-LOG-002: Rechazo por contraseña errónea"""
        with self.assertRaises(ValidationError):
            validar_credenciales(usuario_registrado=True, clave_correcta=False, esta_activo=True)

    def test_CP_LOG_003_login_usuario_inactivo(self):
        """CP-LOG-003: Bloqueo de inicio de sesión a cuenta deshabilitada"""
        with self.assertRaises(ValidationError):
            validar_credenciales(usuario_registrado=True, clave_correcta=True, esta_activo=False)

    # --- USUARIOS Y RUT (Camilo) ---
    def test_CP_USR_001_rut_valido(self):
        """CP-USR-001: RUT chileno válido mediante algoritmo Módulo 11"""
        self.assertTrue(validar_rut_chileno("12.345.678-5"))

    def test_CP_USR_002_rut_dv_invalido(self):
        """CP-USR-002: Rechazo de RUT con dígito verificador alterado"""
        with self.assertRaises(ValidationError):
            validar_rut_chileno("12.345.678-9")

    # --- ROLES Y ÁMBITO TERRITORIAL (Camilo) ---
    def test_CP_ROL_001_ambito_compatible(self):
        """CP-ROL-001: Acceso autorizado a la delegación asignada"""
        self.assertTrue(verificar_ambito_delegacion(id_delegacion_usuario=1, id_delegacion_destino=1))

    def test_CP_ROL_002_ambito_incompatible(self):
        """CP-ROL-002: Acceso denegado al operar en delegación no asignada"""
        with self.assertRaises(PermissionDenied):
            verificar_ambito_delegacion(id_delegacion_usuario=1, id_delegacion_destino=2)

    # --- METAS (José) ---
    def test_CP_MET_001_suma_ponderaciones_100(self):
        """CP-MET-001: Validación exitosa de ponderaciones que suman 100%"""
        self.assertTrue(validar_suma_ponderaciones([40.0, 35.0, 25.0]))

    def test_CP_MET_002_suma_ponderaciones_invalida(self):
        """CP-MET-002: Rechazo cuando las ponderaciones suman 90%"""
        with self.assertRaises(ValidationError):
            validar_suma_ponderaciones([30.0, 30.0, 30.0])

    # --- PERÍODOS DE MEDICIÓN (José) ---
    def test_CP_PER_001_rango_fechas_valido(self):
        """CP-PER-001: Rango de fechas con término posterior al inicio"""
        inicio = date(2026, 10, 1)
        termino = date(2026, 12, 31)
        self.assertTrue(validar_rango_fechas(inicio, termino))

    def test_CP_PER_002_rango_fechas_invalido(self):
        """CP-PER-002: Rechazo cuando el término es anterior al inicio"""
        inicio = date(2026, 11, 1)
        termino = date(2026, 10, 15)
        with self.assertRaises(ValidationError):
            validar_rango_fechas(inicio, termino)

    def test_CP_PER_003_calculo_dias_computables(self):
        """CP-PER-003: Desglose de días hábiles descontando feriados"""
        inicio = date(2026, 10, 12)
        termino = date(2026, 10, 16)
        feriados = [date(2026, 10, 12)]
        dias = calcular_dias_computables(inicio, termino, feriados)
        self.assertEqual(dias, 4)

    # --- CATÁLOGO DE ACTIVIDADES (José) ---
    def test_CP_CAT_001_codigo_catalogo_unico(self):
        """CP-CAT-001: Registro exitoso con código único"""
        existentes = ["ACT-01", "ACT-02"]
        self.assertTrue(validar_codigo_unico_catalogo("ACT-03", existentes))

    def test_CP_CAT_002_codigo_catalogo_duplicado(self):
        """CP-CAT-002: Rechazo por duplicidad de código"""
        existentes = ["ACT-01", "ACT-02"]
        with self.assertRaises(ValidationError):
            validar_codigo_unico_catalogo("ACT-01", existentes)

    # --- CARGOS (Orlando) ---
    def test_CP_CAR_001_eliminar_cargo_con_dependencias(self):
        """CP-CAR-001: Bloqueo de eliminación física de cargo con usuarios/metas"""
        with self.assertRaises(ProtectedError):
            verificar_eliminacion_cargo(usuarios_asociados=3, metas_asociadas=2)

    def test_CP_CAR_002_baja_logica_cargo(self):
        """CP-CAR-002: Aplicación de baja lógica (activo=False) preservando registro"""
        estado_nuevo = desactivar_cargo(estado_actual=True)
        self.assertFalse(estado_nuevo)


CLAVE = "ClaveSegura#2026"


def crear_usuario(rut, email, rol):
    from django.contrib.auth import get_user_model

    User = get_user_model()

    usuario = User.objects.create_user(
        username=normalizar_rut(rut),
        email=email,
        password=CLAVE,
    )
    PerfilUsuario.objects.create(usuario=usuario, rut=normalizar_rut(rut))
    usuario.groups.add(Group.objects.get(name=rol))

    return usuario


class PruebasSemaforo(SimpleTestCase):
    """Regla del semáforo: 90+ verde, 60-89 amarillo, menos de 60 rojo."""

    def test_limite_verde(self):
        self.assertEqual(Compromiso.calcular_estado(100), "verde")
        self.assertEqual(Compromiso.calcular_estado(90), "verde")

    def test_limite_amarillo(self):
        self.assertEqual(Compromiso.calcular_estado(89), "amarillo")
        self.assertEqual(Compromiso.calcular_estado(60), "amarillo")

    def test_limite_rojo(self):
        self.assertEqual(Compromiso.calcular_estado(59), "rojo")
        self.assertEqual(Compromiso.calcular_estado(0), "rojo")


class PruebasCompromisos(TestCase):
    """Mantenedor de Compromisos: CRUD, búsqueda y baja lógica."""

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", ADMINISTRADOR
        )
        cls.supervisor = crear_usuario(
            "12.345.678-5", "supervisor@laserena.cl", SUPERVISOR
        )
        cls.administrativo = crear_usuario(
            "22.222.222-2", "administrativo@laserena.cl", ADMINISTRATIVO
        )
        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro",
            direccion="Av. Principal 123",
            encargado="Ana Rojas",
            email="centro@laserena.cl",
            telefono="51 2 000 000",
            celular="+56 9 0000 0000",
        )
        cls.rural = Delegacion.objects.create(
            nombre="Delegación Rural",
            direccion="Camino Rural km 5",
            encargado="Pedro Soto",
            email="rural@laserena.cl",
            telefono="51 2 000 001",
            celular="",
        )

    def crear_compromiso(self, tarea="Mejorar luminarias", **cambios):
        datos = {
            "tarea": tarea,
            "cumplimiento": 95,
            "delegacion": self.centro,
        }
        datos.update(cambios)

        return Compromiso.objects.create(**datos)

    # --- MODELO ---
    def test_el_estado_se_calcula_al_guardar(self):
        compromiso = self.crear_compromiso(cumplimiento=30)
        self.assertEqual(compromiso.estado, "rojo")

        compromiso.cumplimiento = 95
        compromiso.save()
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, "verde")

    # --- ACCESO ---
    def test_lista_requiere_sesion(self):
        respuesta = self.client.get(reverse("compromiso_lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])

    def test_administrativo_puede_crear_pero_no_editar_ni_bajar(self):
        compromiso = self.crear_compromiso()
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(reverse("compromiso_lista"))
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(reverse("compromiso_crear"))
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(
            reverse("compromiso_editar", args=[compromiso.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

        respuesta = self.client.post(
            reverse("compromiso_cambiar_estado", args=[compromiso.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

        compromiso.refresh_from_db()
        self.assertTrue(compromiso.activo)

    # --- CREAR ---
    def test_crear_compromiso_calcula_estado(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_crear"),
            {
                "tarea": "Mejorar iluminación del sector",
                "cumplimiento": 92,
                "delegacion": self.centro.pk,
            },
        )

        self.assertRedirects(respuesta, reverse("compromiso_lista"))

        compromiso = Compromiso.objects.get(
            tarea="Mejorar iluminación del sector"
        )
        self.assertEqual(compromiso.estado, "verde")
        self.assertEqual(compromiso.delegacion, self.centro)
        self.assertTrue(compromiso.activo)

    def test_crear_sin_delegacion_es_valido(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_crear"),
            {"tarea": "Compromiso transversal", "cumplimiento": 70},
        )

        self.assertRedirects(respuesta, reverse("compromiso_lista"))
        self.assertTrue(
            Compromiso.objects.filter(
                tarea="Compromiso transversal",
                delegacion__isnull=True,
            ).exists()
        )

    def test_cumplimiento_fuera_de_rango_es_rechazado(self):
        self.client.force_login(self.supervisor)

        for valor in (101, -1):
            respuesta = self.client.post(
                reverse("compromiso_crear"),
                {
                    "tarea": f"Compromiso {valor}",
                    "cumplimiento": valor,
                    "delegacion": self.centro.pk,
                },
            )
            self.assertEqual(respuesta.status_code, 200, valor)

        self.assertFalse(
            Compromiso.objects.filter(tarea__startswith="Compromiso ").exists()
        )

    def test_tarea_vacia_es_rechazada(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_crear"),
            {"tarea": "   ", "cumplimiento": 50},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Compromiso.objects.exists())

    # --- BUSCAR Y FILTRAR ---
    def test_busqueda_por_tarea_y_delegacion(self):
        self.crear_compromiso(tarea="Mejorar luminarias")
        self.crear_compromiso(
            tarea="Ampliar sede vecinal", delegacion=self.rural
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("compromiso_lista"), {"q": "luminarias"}
        )
        self.assertContains(respuesta, "Mejorar luminarias")
        self.assertNotContains(respuesta, "Ampliar sede vecinal")

        respuesta = self.client.get(
            reverse("compromiso_lista"), {"q": "Rural"}
        )
        self.assertContains(respuesta, "Ampliar sede vecinal")
        self.assertNotContains(respuesta, "Mejorar luminarias")

    def test_filtro_por_semaforo_y_situacion(self):
        self.crear_compromiso(tarea="Compromiso verde", cumplimiento=95)
        self.crear_compromiso(tarea="Compromiso rojo", cumplimiento=10)
        self.crear_compromiso(
            tarea="Compromiso inactivo", cumplimiento=95, activo=False
        )
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("compromiso_lista"), {"estado": "verde"}
        )
        self.assertContains(respuesta, "Compromiso verde")
        self.assertNotContains(respuesta, "Compromiso rojo")

        respuesta = self.client.get(
            reverse("compromiso_lista"),
            {"estado": "verde", "situacion": "inactivos"},
        )
        self.assertContains(respuesta, "Compromiso inactivo")
        self.assertNotContains(respuesta, "Compromiso verde")

    # --- EDITAR ---
    def test_editar_actualiza_el_semaforo(self):
        compromiso = self.crear_compromiso(cumplimiento=95)
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_editar", args=[compromiso.pk]),
            {
                "tarea": compromiso.tarea,
                "cumplimiento": 40,
                "delegacion": self.centro.pk,
            },
        )

        self.assertRedirects(respuesta, reverse("compromiso_lista"))

        compromiso.refresh_from_db()
        self.assertEqual(compromiso.cumplimiento, 40)
        self.assertEqual(compromiso.estado, "rojo")

    # --- BAJA Y REACTIVACIÓN ---
    def test_baja_logica_conserva_el_registro(self):
        compromiso = self.crear_compromiso()
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_cambiar_estado", args=[compromiso.pk])
        )

        self.assertRedirects(respuesta, reverse("compromiso_lista"))

        compromiso.refresh_from_db()
        self.assertFalse(compromiso.activo)
        self.assertTrue(Compromiso.objects.filter(pk=compromiso.pk).exists())

    def test_reactivacion(self):
        compromiso = self.crear_compromiso(activo=False)
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse("compromiso_cambiar_estado", args=[compromiso.pk])
        )

        compromiso.refresh_from_db()
        self.assertTrue(compromiso.activo)

    def test_baja_exige_post(self):
        compromiso = self.crear_compromiso()
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(
            reverse("compromiso_cambiar_estado", args=[compromiso.pk])
        )

        self.assertEqual(respuesta.status_code, 405)

