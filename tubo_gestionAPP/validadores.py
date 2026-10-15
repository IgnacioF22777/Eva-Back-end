from datetime import date, timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import ProtectedError

# ==========================================
# 1. AUTENTICACIÓN Y ROLES (Camilo)
# ==========================================
def validar_credenciales(usuario_registrado: bool, clave_correcta: bool, esta_activo: bool) -> bool:
    """Valida inicio de sesión y estado de cuenta (CP-LOG-001 a CP-LOG-003)."""
    if not usuario_registrado or not clave_correcta:
        raise ValidationError("Credenciales inválidas.")
    if not esta_activo:
        raise ValidationError("Cuenta inactiva o deshabilitada.")
    return True

def validar_rut_chileno(rut: str) -> bool:
    """Valida formato y algoritmo Módulo 11 del RUT (CP-USR-001 y CP-USR-002)."""
    rut_limpio = rut.replace(".", "").replace("-", "").strip().upper()
    if len(rut_limpio) < 2:
        raise ValidationError("El RUT ingresado no es válido.")
    
    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]
    
    if not cuerpo.isdigit():
        raise ValidationError("El RUT ingresado no es válido.")
        
    suma = 0
    multiplicador = 2
    for c in reversed(cuerpo):
        suma += int(c) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1
        
    resto = suma % 11
    dv_esperado = 11 - resto
    
    if dv_esperado == 11:
        dv_calculado = "0"
    elif dv_esperado == 10:
        dv_calculado = "K"
    else:
        dv_calculado = str(dv_esperado)
        
    if dv != dv_calculado:
        raise ValidationError("El RUT ingresado no es válido o su dígito verificador es incorrecto.")
    return True

def verificar_ambito_delegacion(id_delegacion_usuario: int, id_delegacion_destino: int) -> bool:
    """Valida coherencia territorial RBAC (CP-ROL-001 y CP-ROL-002)."""
    if id_delegacion_usuario != id_delegacion_destino:
        raise PermissionDenied("Ámbito de delegación no autorizado.")
    return True

# ==========================================
# 2. METAS Y PERÍODOS (José)
# ==========================================
def validar_suma_ponderaciones(ponderaciones: list) -> bool:
    """Valida que la suma de metas alcance exactamente el 100% (CP-MET-001 y CP-MET-002)."""
    total = sum(ponderaciones)
    if round(total, 2) != 100.0:
        raise ValidationError("La suma de ponderaciones debe ser exactamente 100%.")
    return True

def validar_rango_fechas(fecha_inicio: date, fecha_termino: date) -> bool:
    """Valida cronología del período (CP-PER-001 y CP-PER-002)."""
    if fecha_termino < fecha_inicio:
        raise ValidationError("La fecha de término no puede ser anterior a la fecha de inicio.")
    return True

def calcular_dias_computables(fecha_inicio: date, fecha_termino: date, feriados: list = None) -> int:
    """Calcula días laborales descontando feriados (CP-PER-003)."""
    if feriados is None:
        feriados = []
    
    total_dias = 0
    delta = (fecha_termino - fecha_inicio).days + 1
    
    for i in range(delta):
        dia_actual = fecha_inicio + timedelta(days=i)
        if dia_actual.weekday() < 5 and dia_actual not in feriados:
            total_dias += 1
            
    return total_dias

def validar_codigo_unico_catalogo(codigo: str, codigos_existentes: list) -> bool:
    """Valida que no existan duplicados en catálogo (CP-CAT-001 y CP-CAT-002)."""
    if codigo in codigos_existentes:
        raise ValidationError("Ya existe un elemento registrado con este código.")
    return True

# ==========================================
# 3. CARGOS Y BAJA LÓGICA (Orlando)
# ==========================================
def verificar_eliminacion_cargo(usuarios_asociados: int, metas_asociadas: int) -> bool:
    """Bloquea eliminación física si existen dependencias (CP-CAR-001)."""
    if usuarios_asociados > 0 or metas_asociadas > 0:
        raise ProtectedError("No es posible eliminar el cargo porque cuenta con registros asociados.", None)
    return True

def desactivar_cargo(estado_actual: bool) -> bool:
    """Aplica baja lógica cambiando el estado a inactivo (CP-CAR-002)."""
    return False
