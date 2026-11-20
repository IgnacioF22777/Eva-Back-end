from django.utils import timezone

from sgr_maestrosAPP.feriados import feriados_entre
from tubo_gestionAPP.validadores import calcular_dias_computables

from .models import AjusteDesempeno, Ausencia
from .reglas import aplicar_ajustes, interseccion, requiere_informe_rrhh


# ============================================================
# SERVICIOS DE LA MATRIZ PARA OTROS MÓDULOS
# ============================================================
# Funciones que usan José (puntaje), Ignacio (equipo) y el semáforo.
# Reciben fechas en vez de un Periodo para no depender de cómo se
# modele el período en cada pantalla:
#   dias_ausencia(funcionario, periodo.fecha_inicio, periodo.fecha_fin)


def dias_ausencia(funcionario, desde, hasta):
    """
    Días hábiles que el funcionario estuvo ausente entre `desde` y
    `hasta` (ambos incluidos). Cada ausencia se recorta al rango: una
    licencia del 28-sep al 3-oct cuenta solo hasta el 30-sep si el
    período termina ese día (CP-AUS-005).
    """
    total = 0
    ausencias = Ausencia.objects.filter(
        funcionario=funcionario,
        activo=True,
        fecha_inicio__lte=hasta,
        fecha_fin__gte=desde,
    )

    for ausencia in ausencias:
        tramo = interseccion(ausencia.fecha_inicio, ausencia.fecha_fin, desde, hasta)
        if tramo:
            inicio, fin = tramo
            total += calcular_dias_computables(inicio, fin, feriados_entre(inicio, fin))

    return total


def contar_ajustes(funcionario, desde, hasta):
    """(felicitaciones, reclamos) vigentes del funcionario en el rango."""
    ajustes = AjusteDesempeno.objects.filter(
        funcionario=funcionario, activo=True, fecha__range=(desde, hasta),
    )
    felicitaciones = ajustes.filter(tipo=AjusteDesempeno.FELICITACION).count()
    reclamos = ajustes.filter(tipo=AjusteDesempeno.RECLAMO).count()
    return felicitaciones, reclamos


def cumplimiento_final(funcionario, total_base, desde, hasta):
    """
    Total base (lo calcula José con los ítems y el tope de 120% por
    ítem) más felicitaciones y menos reclamos, con el tope de 120%.
    """
    felicitaciones, reclamos = contar_ajustes(funcionario, desde, hasta)
    return aplicar_ajustes(total_base, felicitaciones, reclamos)


def alerta_rrhh(funcionario, hoy=None):
    """True si tiene reclamos en el trimestre actual y en el anterior."""
    fechas = AjusteDesempeno.objects.filter(
        funcionario=funcionario, activo=True, tipo=AjusteDesempeno.RECLAMO,
    ).values_list("fecha", flat=True)

    return requiere_informe_rrhh(fechas, hoy or timezone.localdate())
