from datetime import date
from django.test import SimpleTestCase
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import ProtectedError

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
