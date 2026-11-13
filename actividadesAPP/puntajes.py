
"""
SGR - EVA 3
Cálculo de puntajes individuales (R7).

Responsable: José Villalobos.

Utiliza los registros de actividades y las metas
por cargo ya existentes en el proyecto.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count

from sgr_maestrosAPP.models import Meta
from sgr_maestrosAPP.feriados import feriados_entre
from tubo_gestionAPP.validadores import calcular_dias_computables

from .models import RegistroActividad


# ============================================================
# CONSTANTES
# ============================================================

TOPE_CUMPLIMIENTO = Decimal("120.00")
CIEN = Decimal("100")
DOS_DECIMALES = Decimal("0.01")


def redondear(valor):
    """Redondea un resultado a dos decimales."""
    return Decimal(str(valor)).quantize(
        DOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# R7 - META AJUSTADA POR AUSENCIAS
# ============================================================

def calcular_meta_ajustada(
    objetivo,
    dias_periodo,
    dias_ausencia=0,
):
    """
    Calcula la meta considerando los días de ausencia.

    Fórmula:
    objetivo * (días período - ausencias) / días período

    El parámetro dias_ausencia permitirá integrar
    posteriormente el módulo de Camilo.
    """

    objetivo = Decimal(str(objetivo))
    dias_periodo = int(dias_periodo)
    dias_ausencia = int(dias_ausencia)

    if objetivo < 0:
        raise ValueError(
            "El objetivo no puede ser negativo."
        )

    if dias_periodo < 0:
        raise ValueError(
            "Los días del período no pueden ser negativos."
        )

    if dias_ausencia < 0 or dias_ausencia > dias_periodo:
        raise ValueError(
            "Los días de ausencia deben estar dentro del período."
        )

    if dias_periodo == 0:
        return Decimal("0")

    return (
        objetivo
        * Decimal(dias_periodo - dias_ausencia)
        / Decimal(dias_periodo)
    )


# ============================================================
# R7 - CUMPLIMIENTO CON TOPE DE 120%
# ============================================================

def calcular_cumplimiento_item(
    avance,
    meta_ajustada,
):
    """
    Devuelve el porcentaje de cumplimiento de un ítem.

    Nunca supera el 120%.
    """

    avance = Decimal(str(avance))
    meta_ajustada = Decimal(str(meta_ajustada))

    if avance < 0:
        raise ValueError(
            "El avance no puede ser negativo."
        )

    if meta_ajustada <= 0:
        return Decimal("0.00")

    porcentaje = (
        avance / meta_ajustada
    ) * CIEN

    return redondear(
        min(porcentaje, TOPE_CUMPLIMIENTO)
    )


# ============================================================
# R7 - PUNTAJE PONDERADO
# ============================================================

def calcular_puntaje_ponderado(
    cumplimiento,
    ponderacion,
):
    """
    Ejemplo:
    Cumplimiento: 80%
    Ponderación: 25%
    Resultado: 20 puntos.
    """

    cumplimiento = Decimal(str(cumplimiento))
    ponderacion = Decimal(str(ponderacion))

    if cumplimiento < 0 or ponderacion < 0:
        raise ValueError(
            "El cumplimiento y la ponderación "
            "no pueden ser negativos."
        )

    cumplimiento = min(
        cumplimiento,
        TOPE_CUMPLIMIENTO,
    )

    return redondear(
        cumplimiento * ponderacion / CIEN
    )


# ============================================================
# DÍAS COMPUTABLES DEL PERÍODO
# ============================================================

def obtener_dias_periodo(periodo):
    """
    Calcula los días hábiles del período.

    Reutiliza el cálculo de feriados del proyecto.
    """

    feriados = feriados_entre(
        periodo.fecha_inicio,
        periodo.fecha_fin,
    )

    return calcular_dias_computables(
        periodo.fecha_inicio,
        periodo.fecha_fin,
        feriados,
    )


# ============================================================
# CONSULTA DE ACTIVIDADES VÁLIDAS
# ============================================================

def contar_actividades_por_catalogo(
    funcionario,
    periodo,
):
    """
    Agrupa las actividades válidas del funcionario.

    Solo considera:
    - Registros activos.
    - Registros que puntúan.
    - Actividades realizadas dentro del período.
    """

    registros = RegistroActividad.objects.filter(
        funcionario=funcionario,
        activo=True,
        puntua=True,
        fecha_actividad__gte=periodo.fecha_inicio,
        fecha_actividad__lte=periodo.fecha_fin,
    )

    conteos = registros.values(
        "actividad_id"
    ).annotate(
        total=Count("id")
    )

    return {
        fila["actividad_id"]: fila["total"]
        for fila in conteos
    }


# ============================================================
# R7 - MI MATRIZ
# ============================================================

def obtener_mi_matriz(
    funcionario,
    periodo,
    dias_ausencia=0,
):
    """
    Calcula la matriz individual de un funcionario.

    Las metas corresponden al cargo del funcionario.

    Retorna:
    - Metas del cargo.
    - Avance por actividad.
    - Meta ajustada.
    - Cumplimiento con tope 120%.
    - Puntaje ponderado.
    - Total individual.
    """

    dias_periodo = obtener_dias_periodo(periodo)

    # Se validan también aquí las ausencias aunque
    # el funcionario todavía no tenga metas.
    calcular_meta_ajustada(
        0,
        dias_periodo,
        dias_ausencia,
    )

    resultado = {
        "funcionario": funcionario,
        "periodo": periodo,
        "cargo": funcionario.cargo,
        "dias_periodo": dias_periodo,
        "dias_ausencia": dias_ausencia,
        "items": [],
        "puntaje_total": Decimal("0.00"),
        "ponderacion_total": Decimal("0.00"),
    }

    if funcionario.cargo_id is None:
        return resultado

    metas = Meta.objects.filter(
        periodo=periodo,
        cargo_id=funcionario.cargo_id,
        activo=True,
    ).select_related(
        "actividad",
        "cargo",
    ).order_by(
        "codigo",
    )

    conteos = contar_actividades_por_catalogo(
        funcionario,
        periodo,
    )

    puntaje_total = Decimal("0")
    ponderacion_total = Decimal("0")

    for meta in metas:

        avance = conteos.get(
            meta.actividad_id,
            0,
        )

        objetivo_ajustado = calcular_meta_ajustada(
            meta.valor_objetivo,
            dias_periodo,
            dias_ausencia,
        )

        cumplimiento = calcular_cumplimiento_item(
            avance,
            objetivo_ajustado,
        )

        puntaje = calcular_puntaje_ponderado(
            cumplimiento,
            meta.ponderacion,
        )

        resultado["items"].append({
            "meta": meta,
            "actividad": meta.actividad,
            "objetivo_original": meta.valor_objetivo,
            "objetivo_ajustado": redondear(
                objetivo_ajustado
            ),
            "avance": avance,
            "cumplimiento": cumplimiento,
            "ponderacion": meta.ponderacion,
            "puntaje": puntaje,
        })

        puntaje_total += puntaje
        ponderacion_total += meta.ponderacion

    resultado["puntaje_total"] = redondear(
        puntaje_total
    )

    resultado["ponderacion_total"] = redondear(
        ponderacion_total
    )

    return resultado
