from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from django.utils import timezone

from actividadesAPP.models import ZONA_CHILE, RegistroActividad, rango_dia_chile
from actividadesAPP.seguimiento import (
    delegacion_elegida,
    entero_o_none,
    fecha_o_none,
    funcionarios_del_ambito,
    registros_de_delegacion,
)
from delegacionesAPP.models import Delegacion
from tubo_gestionAPP.ambito import es_global

from .indicadores import INDICADORES, NOMBRES, Umbrales, detectar


DIAS_POR_DEFECTO = 28
DIAS_MAXIMOS = 92


def rango_pedido(request, hoy):
    """Rango de fechas de ingreso: últimas 4 semanas por defecto, máximo un trimestre."""
    desde = fecha_o_none(request.GET.get("desde"))
    hasta = fecha_o_none(request.GET.get("hasta"))
    avisos = []

    hasta = min(hasta or hoy, hoy)
    desde = desde or hasta - timedelta(days=DIAS_POR_DEFECTO - 1)
    if desde > hasta:
        desde, hasta = hasta, desde
        avisos.append("La fecha «desde» era posterior a «hasta»: se invirtieron.")
    if (hasta - desde).days + 1 > DIAS_MAXIMOS:
        desde = hasta - timedelta(days=DIAS_MAXIMOS - 1)
        avisos.append(f"El rango máximo es de {DIAS_MAXIMOS} días: se acortó desde el {desde:%d-%m-%Y}.")
    return desde, hasta, avisos


# ============================================================
# ALERTAS DE REGISTROS SOSPECHOSOS (R6)
# ============================================================

@login_required
@permission_required("actividadesAPP.verificar_registroactividad", raise_exception=True)
def alerta_lista(request):
    hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
    desde, hasta, avisos = rango_pedido(request, hoy)
    for aviso in avisos:
        messages.info(request, aviso)

    delegacion = delegacion_elegida(request)
    funcionario = entero_o_none(request.GET.get("funcionario"))
    indicador = request.GET.get("indicador", "")
    if indicador not in NOMBRES:
        indicador = ""

    inicio, _ = rango_dia_chile(desde)
    _, fin = rango_dia_chile(hasta)
    registros = (
        registros_de_delegacion(request.user)
        .filter(activo=True, fecha_ingreso__gte=inicio, fecha_ingreso__lt=fin)
        .exclude(estado_verificacion=RegistroActividad.RECHAZADA)
    )
    if delegacion is not None:
        registros = registros.filter(funcionario__delegacion=delegacion)
    if funcionario:
        registros = registros.filter(funcionario_id=funcionario)

    umbrales = Umbrales.desde_settings()
    alertas = detectar(registros, umbrales, [indicador] if indicador else None)

    conteo = {clave: 0 for clave in NOMBRES}
    for alerta in alertas:
        conteo[alerta.indicador] += 1

    return render(request, "alertas/alerta_lista.html", {
        "alertas": alertas,
        "resumen": [
            {"clave": clave, "nombre": nombre, "total": conteo[clave]}
            for clave, nombre in INDICADORES
        ],
        "funcionarios_con_alertas": len({a.funcionario.pk for a in alertas}),
        "registros_involucrados": len({r.pk for a in alertas for r in a.registros}),
        "umbrales": umbrales,
        "indicadores": INDICADORES,
        "filtros": {"desde": desde, "hasta": hasta, "funcionario": funcionario, "indicador": indicador},
        "funcionarios": funcionarios_del_ambito(request.user, delegacion),
        "delegaciones": Delegacion.objects.filter(activo=True) if es_global(request.user) else None,
        "delegacion": delegacion,
    })
