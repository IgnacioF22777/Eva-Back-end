from datetime import date
from decimal import Decimal

from django.conf import settings


# ============================================================
# REGLAS DE LA MATRIZ SGR (EVALUACIÓN 3) - FUNCIONES PURAS
# ============================================================
# Responsable: Camilo Villalobos.
#
# Son funciones sin base de datos, para poder probarlas solas, igual
# que las de tubo_gestionAPP/validadores.py. Se dejan en esta app (y no
# en validadores.py) para no chocar con los cambios de José en ese
# archivo.
#
# Los porcentajes salen de la hoja RECLAMOS de la matriz Excel y del
# tope confirmado por el profesor. Se pueden ajustar en settings.py sin
# tocar el código.

BONO_FELICITACION = Decimal(str(getattr(settings, "SGR_BONO_FELICITACION", "0.10")))
DESCUENTO_RECLAMO = Decimal(str(getattr(settings, "SGR_DESCUENTO_RECLAMO", "0.20")))
TOPE_CUMPLIMIENTO = Decimal(str(getattr(settings, "SGR_TOPE_CUMPLIMIENTO", "1.20")))

# Semáforo (hoja SEMAFORO): naranjo desde el 60% del objetivo del día.
UMBRAL_NARANJO = Decimal("0.60")

VERDE = "VERDE"
NARANJO = "NARANJO"
ROJO = "ROJO"


# ------------------------------------------------------------
# FECHAS
# ------------------------------------------------------------

def se_traslapan(inicio_a, fin_a, inicio_b, fin_b):
    """
    Dos rangos de fechas se traslapan si uno empieza antes de que el otro
    termine y termina después de que el otro empieza. Los extremos
    cuentan: una ausencia que termina el 5 y otra que empieza el 5 se
    traslapan (CP-AUS-001).
    """
    return inicio_a <= fin_b and fin_a >= inicio_b


def interseccion(inicio_a, fin_a, inicio_b, fin_b):
    """Parte común de dos rangos, o None si no se tocan."""
    if not se_traslapan(inicio_a, fin_a, inicio_b, fin_b):
        return None

    return max(inicio_a, inicio_b), min(fin_a, fin_b)


def trimestre_de(fecha):
    """(año, número de trimestre 1-4) de una fecha."""
    return fecha.year, (fecha.month - 1) // 3 + 1


def trimestre_anterior(anio, trimestre):
    if trimestre == 1:
        return anio - 1, 4
    return anio, trimestre - 1


# ------------------------------------------------------------
# FELICITACIONES Y RECLAMOS
# ------------------------------------------------------------

def aplicar_ajustes(total_base, felicitaciones, reclamos,
                    bono=None, descuento=None, tope=None):
    """
    Cumplimiento final de un funcionario (CP-AJU-001 a 003):

        total base + bono × felicitaciones − descuento × reclamos

    y luego se limita: nunca menos de 0 ni más del tope (120%).
    Todos los valores son fracciones: 0.95 = 95%.
    """
    bono = BONO_FELICITACION if bono is None else Decimal(str(bono))
    descuento = DESCUENTO_RECLAMO if descuento is None else Decimal(str(descuento))
    tope = TOPE_CUMPLIMIENTO if tope is None else Decimal(str(tope))

    if felicitaciones < 0 or reclamos < 0:
        raise ValueError("Las cantidades no pueden ser negativas.")

    total = (
        Decimal(str(total_base))
        + bono * felicitaciones
        - descuento * reclamos
    )

    return min(max(total, Decimal("0")), tope)


def requiere_informe_rrhh(fechas_reclamos, hoy=None):
    """
    Hoja RECLAMOS: "los reclamos no pueden exceder más de 2 trimestres
    seguidos (informar a RRHH)". Se marca la alerta cuando el
    funcionario tiene reclamos en el trimestre actual Y en el anterior
    (CP-AJU-004).
    """
    hoy = hoy or date.today()
    actual = trimestre_de(hoy)
    anterior = trimestre_anterior(*actual)
    trimestres = {trimestre_de(fecha) for fecha in fechas_reclamos}

    return actual in trimestres and anterior in trimestres


# ------------------------------------------------------------
# SEMÁFORO POR FUNCIONARIO
# ------------------------------------------------------------

def objetivo_al_dia(dias_transcurridos, dias_totales):
    """
    Fracción de la meta que el funcionario debería llevar hoy. Los días
    totales ya vienen descontadas las ausencias.
    """
    if dias_totales <= 0:
        return Decimal("0")

    fraccion = Decimal(dias_transcurridos) / Decimal(dias_totales)
    return min(max(fraccion, Decimal("0")), Decimal("1"))


def color_semaforo(avance, objetivo, umbral=UMBRAL_NARANJO):
    """
    Fórmula de la hoja SEMAFORO (CP-SEM-001 a 003):
      avance >= objetivo              -> VERDE
      avance >= umbral × objetivo     -> NARANJO
      menos                           -> ROJO
    """
    avance = Decimal(str(avance))
    objetivo = Decimal(str(objetivo))

    if avance >= objetivo:
        return VERDE

    if avance >= objetivo * umbral:
        return NARANJO

    return ROJO
