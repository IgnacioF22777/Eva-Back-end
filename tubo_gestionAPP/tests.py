from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.models import PerfilUsuario, normalizar_rut
from seguridadAPP.perfiles import (
    ADMINISTRADOR,
    ADMINISTRATIVO,
    SUPERVISOR,
)
from seguridadAPP.roles import sincronizar_roles

from .models import Compromiso, AsignacionCompromiso, RegistroAvance

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

    def test_servicio_debe_pertenecer_a_la_delegacion(self):
        servicio_rural = Servicio.objects.create(
            delegacion=self.rural,
            nombre="Aseo rural",
        )
        compromiso = Compromiso(
            tarea="Compromiso inconsistente",
            cumplimiento=0,
            delegacion=self.centro,
            servicio=servicio_rural,
        )

        with self.assertRaises(ValidationError):
            compromiso.full_clean()

    def test_asignacion_protege_delegacion_servicio_y_usuario(self):
        servicio = Servicio.objects.create(
            delegacion=self.centro,
            nombre="Aseo",
        )
        compromiso = self.crear_compromiso()
        AsignacionCompromiso.objects.create(
            compromiso=compromiso,
            delegacion=self.centro,
            servicio=servicio,
            usuario_asignador=self.supervisor,
        )

        with self.assertRaises(ProtectedError):
            self.centro.delete()

        with self.assertRaises(ProtectedError):
            servicio.delete()

        with self.assertRaises(ProtectedError):
            self.supervisor.delete()

    def test_asignacion_no_acepta_servicio_de_otra_delegacion(self):
        servicio_rural = Servicio.objects.create(
            delegacion=self.rural,
            nombre="Aseo rural",
        )
        asignacion = AsignacionCompromiso(
            compromiso=self.crear_compromiso(),
            delegacion=self.centro,
            servicio=servicio_rural,
            usuario_asignador=self.supervisor,
        )

        with self.assertRaises(ValidationError):
            asignacion.full_clean()

    def test_registro_avance_exige_evidencia(self):
        registro = RegistroAvance(
            compromiso=self.crear_compromiso(),
            usuario_registro=self.administrativo,
            porcentaje_avance=10,
            evidencia="   ",
        )

        with self.assertRaises(ValidationError):
            registro.full_clean()

    def test_registro_avance_valida_porcentaje(self):
        for valor in (101, -1):
            registro = RegistroAvance(
                compromiso=self.crear_compromiso(),
                usuario_registro=self.administrativo,
                porcentaje_avance=valor,
                evidencia="Acta de reunión",
            )

            with self.assertRaises(ValidationError, msg=str(valor)):
                registro.full_clean()

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
    def test_crear_compromiso_inicia_sin_asignacion_y_en_rojo(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_crear"),
            {
                "tarea": "Mejorar iluminación del sector",
                # Estos campos ya no son editables: deben ignorarse.
                "cumplimiento": 92,
                "delegacion": self.centro.pk,
            },
        )

        self.assertRedirects(respuesta, reverse("compromiso_lista"))

        compromiso = Compromiso.objects.get(
            tarea="Mejorar iluminación del sector"
        )
        self.assertEqual(compromiso.cumplimiento, 0)
        self.assertEqual(compromiso.estado, "rojo")
        self.assertIsNone(compromiso.delegacion)
        self.assertIsNone(compromiso.servicio)
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

    def test_formulario_solo_permite_editar_la_tarea(self):
        from .forms import CompromisoForm

        self.assertEqual(list(CompromisoForm().fields), ["tarea"])

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
    def test_editar_no_permite_cambiar_el_cumplimiento(self):
        compromiso = self.crear_compromiso(cumplimiento=95)
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            reverse("compromiso_editar", args=[compromiso.pk]),
            {
                "tarea": "Tarea corregida",
                "cumplimiento": 40,
                "delegacion": self.centro.pk,
            },
        )

        self.assertRedirects(respuesta, reverse("compromiso_lista"))

        compromiso.refresh_from_db()
        self.assertEqual(compromiso.tarea, "Tarea corregida")
        self.assertEqual(compromiso.cumplimiento, 95)
        self.assertEqual(compromiso.estado, "verde")
        self.assertEqual(compromiso.delegacion, self.centro)

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


class PruebasFase4Transacciones(TestCase):
    """
    Fase 4: dos transacciones atómicas.

    T1 -> el Supervisor asigna el compromiso (transaction.atomic +
          select_for_update sobre Compromiso).
    T2 -> el Administrativo registra el avance (transaction.atomic +
          select_for_update sobre Compromiso).
    """

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.admin = crear_usuario(
            "13.333.333-3", "admin.f4@laserena.cl", ADMINISTRADOR
        )
        cls.supervisor = crear_usuario(
            "14.444.444-4", "supervisor.f4@laserena.cl", SUPERVISOR
        )
        cls.administrativo = crear_usuario(
            "15.555.555-5", "administrativo.f4@laserena.cl", ADMINISTRATIVO
        )

        cls.centro = Delegacion.objects.create(
            nombre="Delegación Centro F4",
            direccion="Av. Principal 500",
            encargado="Ana Rojas",
            email="centro.f4@laserena.cl",
            telefono="51 2 100 000",
            celular="+56 9 1000 0000",
        )
        cls.rural = Delegacion.objects.create(
            nombre="Delegación Rural F4",
            direccion="Camino Rural km 9",
            encargado="Pedro Soto",
            email="rural.f4@laserena.cl",
            telefono="51 2 100 001",
            celular="",
        )

        cls.servicio = Servicio.objects.create(
            delegacion=cls.centro,
            nombre="Aseo y ornato",
        )
        cls.servicio_rural = Servicio.objects.create(
            delegacion=cls.rural,
            nombre="Riego rural",
        )
        cls.servicio_inactivo = Servicio.objects.create(
            delegacion=cls.centro,
            nombre="Servicio dado de baja",
            activo=False,
        )

    def setUp(self):
        self.compromiso = Compromiso.objects.create(
            tarea="Mejorar luminarias del sector",
            cumplimiento=0,
        )

    # --- AYUDAS ---
    def asignar_directo(self):
        """Asignación válida creada por ORM, para probar T2 aislada."""
        asignacion = AsignacionCompromiso.objects.create(
            compromiso=self.compromiso,
            delegacion=self.centro,
            servicio=self.servicio,
            usuario_asignador=self.supervisor,
        )
        self.compromiso.delegacion = self.centro
        self.compromiso.servicio = self.servicio
        self.compromiso.save()

        return asignacion

    def url(self, nombre, compromiso=None):
        return reverse(
            nombre, args=[(compromiso or self.compromiso).pk]
        )

    # --- T1: ASIGNACIÓN ---
    def test_supervisor_asigna_compromiso(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url("compromiso_asignar"),
            {
                "delegacion": self.centro.pk,
                "servicio": self.servicio.pk,
                "observacion": "Coordinar con la unidad de aseo.",
            },
        )

        self.assertRedirects(
            respuesta, self.url("compromiso_historial")
        )

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.delegacion, self.centro)
        self.assertEqual(self.compromiso.servicio, self.servicio)

        asignacion = AsignacionCompromiso.objects.get(
            compromiso=self.compromiso
        )
        self.assertTrue(asignacion.activo)
        self.assertEqual(asignacion.usuario_asignador, self.supervisor)
        self.assertEqual(self.compromiso.asignaciones.count(), 1)

    def test_reasignar_desactiva_la_anterior_sin_borrarla(self):
        self.client.force_login(self.supervisor)

        self.client.post(
            self.url("compromiso_asignar"),
            {
                "delegacion": self.centro.pk,
                "servicio": self.servicio.pk,
            },
        )

        respuesta = self.client.post(
            self.url("compromiso_asignar"),
            {
                "delegacion": self.rural.pk,
                "servicio": self.servicio_rural.pk,
            },
        )

        self.assertRedirects(
            respuesta, self.url("compromiso_historial")
        )

        asignaciones = AsignacionCompromiso.objects.filter(
            compromiso=self.compromiso
        )
        self.assertEqual(asignaciones.count(), 2)
        self.assertEqual(asignaciones.filter(activo=True).count(), 1)

        vigente = asignaciones.get(activo=True)
        self.assertEqual(vigente.delegacion, self.rural)

        anterior = asignaciones.get(activo=False)
        self.assertEqual(anterior.delegacion, self.centro)
        self.assertEqual(anterior.servicio, self.servicio)

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.servicio, self.servicio_rural)

    def test_asignacion_rechaza_servicio_de_otra_delegacion(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url("compromiso_asignar"),
            {
                "delegacion": self.centro.pk,
                "servicio": self.servicio_rural.pk,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            AsignacionCompromiso.objects.count(), 0
        )

        self.compromiso.refresh_from_db()
        self.assertIsNone(self.compromiso.delegacion)
        self.assertIsNone(self.compromiso.servicio)

    def test_asignacion_rechaza_servicio_inactivo(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url("compromiso_asignar"),
            {
                "delegacion": self.centro.pk,
                "servicio": self.servicio_inactivo.pk,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(AsignacionCompromiso.objects.count(), 0)

    def test_asignacion_rechaza_compromiso_inactivo(self):
        self.compromiso.activo = False
        self.compromiso.save(update_fields=["activo"])
        self.client.force_login(self.supervisor)

        respuesta = self.client.post(
            self.url("compromiso_asignar"),
            {
                "delegacion": self.centro.pk,
                "servicio": self.servicio.pk,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dado de baja")
        self.assertEqual(AsignacionCompromiso.objects.count(), 0)

    def test_asignacion_es_atomica(self):
        self.client.force_login(self.supervisor)

        with patch(
            "tubo_gestionAPP.views.AsignacionCompromiso.save",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.url("compromiso_asignar"),
                    {
                        "delegacion": self.centro.pk,
                        "servicio": self.servicio.pk,
                    },
                )

        self.assertEqual(AsignacionCompromiso.objects.count(), 0)

        self.compromiso.refresh_from_db()
        self.assertIsNone(self.compromiso.delegacion)
        self.assertIsNone(self.compromiso.servicio)

    def test_administrativo_no_puede_asignar(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(self.url("compromiso_asignar"))

        self.assertEqual(respuesta.status_code, 403)

    def test_asignacion_requiere_sesion(self):
        respuesta = self.client.get(self.url("compromiso_asignar"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])

    # --- T2: AVANCE ---
    def test_administrativo_registra_avance(self):
        self.asignar_directo()
        self.client.force_login(self.administrativo)

        respuesta = self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 95,
                "evidencia": "Acta de recepción de luminarias",
                "observacion": "Se instalaron 40 luminarias.",
            },
        )

        self.assertRedirects(
            respuesta, self.url("compromiso_historial")
        )

        registro = RegistroAvance.objects.get(compromiso=self.compromiso)
        self.assertEqual(registro.porcentaje_avance, 95)
        self.assertEqual(registro.usuario_registro, self.administrativo)

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 95)
        self.assertEqual(self.compromiso.estado, "verde")

    def test_avance_actualiza_el_semaforo_amarillo(self):
        self.asignar_directo()
        self.client.force_login(self.administrativo)

        self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 70,
                "evidencia": "Informe de avance parcial",
            },
        )

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 70)
        self.assertEqual(self.compromiso.estado, "amarillo")

    def test_avance_no_puede_retroceder(self):
        self.asignar_directo()
        self.compromiso.cumplimiento = 80
        self.compromiso.save()
        self.client.force_login(self.administrativo)

        respuesta = self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 50,
                "evidencia": "Intento de retroceso",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede ser menor")
        self.assertEqual(RegistroAvance.objects.count(), 0)

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 80)

    def test_avance_exige_asignacion_vigente(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 40,
                "evidencia": "Acta sin asignación",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "asignación vigente")
        self.assertEqual(RegistroAvance.objects.count(), 0)

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 0)

    def test_avance_exige_evidencia(self):
        self.asignar_directo()
        self.client.force_login(self.administrativo)

        respuesta = self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 30,
                "evidencia": "   ",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_avance_rechaza_porcentaje_fuera_de_rango(self):
        self.asignar_directo()
        self.client.force_login(self.administrativo)

        for valor in (101, -1):
            respuesta = self.client.post(
                self.url("compromiso_avance"),
                {
                    "porcentaje_avance": valor,
                    "evidencia": "Valor inválido",
                },
            )
            self.assertEqual(respuesta.status_code, 200, valor)

        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_avance_rechaza_compromiso_inactivo(self):
        self.asignar_directo()
        self.compromiso.activo = False
        self.compromiso.save(update_fields=["activo"])
        self.client.force_login(self.administrativo)

        respuesta = self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 50,
                "evidencia": "Acta de compromiso inactivo",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dado de baja")
        self.assertEqual(RegistroAvance.objects.count(), 0)

    def test_avance_ignora_campos_ajenos(self):
        self.asignar_directo()
        otro = Compromiso.objects.create(
            tarea="Otro compromiso", cumplimiento=0
        )
        self.client.force_login(self.administrativo)

        self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 60,
                "evidencia": "Acta válida",
                "compromiso": otro.pk,
                "usuario_registro": self.supervisor.pk,
            },
        )

        registro = RegistroAvance.objects.get()
        self.assertEqual(registro.compromiso, self.compromiso)
        self.assertEqual(registro.usuario_registro, self.administrativo)

        otro.refresh_from_db()
        self.assertEqual(otro.cumplimiento, 0)

    def test_avance_es_atomico(self):
        self.asignar_directo()
        self.client.force_login(self.administrativo)

        with patch(
            "tubo_gestionAPP.views.Compromiso.save",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.url("compromiso_avance"),
                    {
                        "porcentaje_avance": 65,
                        "evidencia": "Acta que no debe persistir",
                    },
                )

        self.assertEqual(RegistroAvance.objects.count(), 0)

        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.cumplimiento, 0)
        self.assertEqual(self.compromiso.estado, "rojo")

    def test_supervisor_no_puede_registrar_avance(self):
        self.asignar_directo()
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(self.url("compromiso_avance"))

        self.assertEqual(respuesta.status_code, 403)

    def test_avance_requiere_sesion(self):
        respuesta = self.client.get(self.url("compromiso_avance"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])

    # --- HISTORIAL ---
    def test_historial_muestra_asignaciones_y_avances(self):
        self.asignar_directo()
        self.client.force_login(self.administrativo)

        self.client.post(
            self.url("compromiso_avance"),
            {
                "porcentaje_avance": 95,
                "evidencia": "Acta 12/2026",
                "observacion": "Trabajo terminado",
            },
        )

        respuesta = self.client.get(self.url("compromiso_historial"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Aseo y ornato")
        self.assertContains(respuesta, "Acta 12/2026")
        self.assertContains(respuesta, "Vigente")
        self.assertContains(respuesta, "95%")

    def test_historial_visible_para_supervisor(self):
        self.asignar_directo()
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(self.url("compromiso_historial"))

        self.assertEqual(respuesta.status_code, 200)

    def test_historial_requiere_sesion(self):
        respuesta = self.client.get(self.url("compromiso_historial"))

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("seguridad:login"), respuesta["Location"])

    # --- PROHIBIDO BORRAR ---
    def test_baja_logica_no_elimina_historial(self):
        self.asignar_directo()
        RegistroAvance.objects.create(
            compromiso=self.compromiso,
            usuario_registro=self.administrativo,
            porcentaje_avance=40,
            evidencia="Acta previa",
        )
        self.client.force_login(self.supervisor)

        self.client.post(
            reverse(
                "compromiso_cambiar_estado", args=[self.compromiso.pk]
            )
        )

        self.compromiso.refresh_from_db()
        self.assertFalse(self.compromiso.activo)
        self.assertEqual(self.compromiso.asignaciones.count(), 1)
        self.assertEqual(self.compromiso.avances.count(), 1)

    def test_tablero_muestra_acciones_segun_perfil(self):
        self.asignar_directo()

        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("compromiso_lista"))
        self.assertContains(respuesta, self.url("compromiso_asignar"))
        self.assertNotContains(respuesta, self.url("compromiso_avance"))

        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("compromiso_lista"))
        self.assertContains(respuesta, self.url("compromiso_avance"))
        self.assertNotContains(respuesta, self.url("compromiso_asignar"))


