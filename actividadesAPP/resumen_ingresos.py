
"""
SGR - EVA 3
Resumen de ingresos de actividades.

Responsable: José Villalobos.

Calcula:
- Último ingreso del funcionario.
- Total de ingresos del período.
- Ingresos que generan puntaje.
- Ingresos sin puntaje.
- Promedio diario de ingresos.
- Días computables transcurridos.
- Cupos utilizados y disponibles del día.

No modifica información de la base de datos.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone

from sgr_maestrosAPP.feriados import feriados_entre
from tubo_gestionAPP.validadores import calcular_dias_computables

from .models import (
    RegistroActividad,
    ZONA_CHILE,
    rango_dia_chile,
)


DOS_DECIMALES = Decimal("0.01")


def calcular_promedio_diario(total_ingresos, dias_computables):
    """
    Calcula el promedio por día hábil transcurrido.

    Se incluyen los días sin registros.
    Si no existen días computables, retorna cero.
    """

    if total_ingresos < 0:
        raise ValueError(
            "El total de ingresos no puede ser negativo."
        )

    if dias_computables < 0:
        raise ValueError(
            "Los días computables no pueden ser negativos."
        )

    if dias_computables == 0:
        return Decimal("0.00")

    promedio = (
        Decimal(total_ingresos)
        / Decimal(dias_computables)
    )

    return promedio.quantize(
        DOS_DECIMALES,
        rounding=ROUND_HALF_UP,
    )


def obtener_resumen_ingresos(
    funcionario,
    periodo=None,
    fecha_referencia=None,
):
    """
    Obtiene el resumen de ingresos del funcionario.

    Si se entrega un período, utiliza sus fechas.
    Si no se entrega, utiliza la semana actual.

    El promedio considera los días hábiles
    transcurridos, excluyendo feriados.

    Los ingresos se contabilizan por fecha_ingreso
    en la zona horaria de Chile.

    Solo cuenta registros activos.
    Las actividades sin puntaje también cuentan
    como ingresos, pero se identifican por separado.
    """

    if fecha_referencia is None:
        fecha_referencia = timezone.localdate(
            timezone.now(),
            timezone=ZONA_CHILE,
        )

    # ==========================================
    # 1. FECHAS DEL RESUMEN
    # ==========================================

    if periodo is not None:
        fecha_inicio = periodo.fecha_inicio
        fecha_fin = periodo.fecha_fin

    else:
        fecha_inicio = (
            fecha_referencia
            - timedelta(
                days=fecha_referencia.weekday()
            )
        )

        fecha_fin = fecha_inicio + timedelta(days=6)

    if fecha_fin < fecha_inicio:
        raise ValueError(
            "La fecha final no puede ser anterior "
            "a la fecha inicial."
        )

    # No considerar días futuros para el promedio.
    fecha_corte = min(
        fecha_fin,
        fecha_referencia,
    )

    # ==========================================
    # 2. REGISTROS ACTIVOS
    # ==========================================

    registros = RegistroActividad.objects.filter(
        funcionario=funcionario,
        activo=True,
    )

    ultimo_ingreso = registros.order_by(
        "-fecha_ingreso",
        "-pk",
    ).first()

    # ==========================================
    # 3. REGISTROS DEL PERÍODO
    # ==========================================

    if fecha_corte >= fecha_inicio:

        inicio_datetime, _ = rango_dia_chile(
            fecha_inicio
        )

        _, fin_datetime = rango_dia_chile(
            fecha_corte
        )

        registros_periodo = registros.filter(
            fecha_ingreso__gte=inicio_datetime,
            fecha_ingreso__lt=fin_datetime,
        )

        feriados = feriados_entre(
            fecha_inicio,
            fecha_corte,
        )

        dias_computables = calcular_dias_computables(
            fecha_inicio,
            fecha_corte,
            feriados,
        )

    else:
        registros_periodo = registros.none()
        dias_computables = 0

    total_ingresos = registros_periodo.count()

    ingresos_con_puntaje = registros_periodo.filter(
        puntua=True,
    ).count()

    ingresos_sin_puntaje = (
        total_ingresos - ingresos_con_puntaje
    )

    ultimo_ingreso_periodo = registros_periodo.order_by(
        "-fecha_ingreso",
        "-pk",
    ).first()

    # ==========================================
    # 4. PROMEDIO DIARIO
    # ==========================================

    promedio_diario = calcular_promedio_diario(
        total_ingresos,
        dias_computables,
    )

    # ==========================================
    # 5. CUPOS DEL DÍA
    # ==========================================

    inicio_hoy, fin_hoy = rango_dia_chile(
        fecha_referencia
    )

    ingresos_hoy = registros.filter(
        fecha_ingreso__gte=inicio_hoy,
        fecha_ingreso__lt=fin_hoy,
    ).count()

    limite_diario = int(
        getattr(
            settings,
            "MAX_INGRESOS_DIARIOS",
            7,
        )
    )

    disponibles_hoy = max(
        0,
        limite_diario - ingresos_hoy,
    )

    # ==========================================
    # 6. RESULTADO
    # ==========================================

    return {
        "funcionario": funcionario,
        "periodo": periodo,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "fecha_corte": fecha_corte,

        "ultimo_ingreso": ultimo_ingreso,
        "ultimo_ingreso_periodo": ultimo_ingreso_periodo,

        "total_ingresos": total_ingresos,
        "ingresos_con_puntaje": ingresos_con_puntaje,
        "ingresos_sin_puntaje": ingresos_sin_puntaje,

        "dias_computables": dias_computables,
        "promedio_diario": promedio_diario,

        "ingresos_hoy": ingresos_hoy,
        "limite_diario": limite_diario,
        "disponibles_hoy": disponibles_hoy,
    }
