from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from actividadesAPP.models import ZONA_CHILE
from delegacionesAPP.models import Delegacion
from seguridadAPP.models import PerfilUsuario
from seguridadAPP.perfiles import ADMINISTRADOR, SUPERVISOR, perfil_requerido
from sgr_maestrosAPP.models import Periodo
from tubo_gestionAPP.ambito import SIN_DELEGACION, delegacion_id_de, es_global

from .calculo import calcular_resumen_equipo


def elegir_periodo(valor, hoy):
    """El período pedido; si no se pide, el vigente o el último que ya empezó."""
    periodos = Periodo.objects.order_by("-fecha_inicio", "-pk")

    valor = (valor or "").strip()
    if valor:
        if not valor.isdecimal():
            raise Http404("El período seleccionado no es válido.")
        return periodos, get_object_or_404(Periodo, pk=int(valor))

    periodo = periodos.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy).first()
    if periodo is None:
        periodo = periodos.filter(fecha_inicio__lte=hoy).first()
    return periodos, periodo


def elegir_delegacion(usuario, valor):
    """
    Ámbito: el Administrador elige cualquier delegación; el Supervisor
    (delegado) ve solo la suya y no puede cambiarla desde la URL.
    """
    if not es_global(usuario):
        propia = delegacion_id_de(usuario)
        if propia is None:
            raise PermissionDenied(SIN_DELEGACION)
        return get_object_or_404(Delegacion, pk=propia)

    valor = (valor or "").strip()
    if valor:
        if not valor.isdecimal():
            raise Http404("La delegación seleccionada no es válida.")
        return get_object_or_404(Delegacion, pk=int(valor))

    con_equipo = Delegacion.objects.filter(
        activo=True, funcionarios__usuario__is_active=True,
    ).distinct()
    return con_equipo.first() or Delegacion.objects.filter(activo=True).first()


# ============================================================
# PANTALLA DE PUNTAJE DEL EQUIPO (R10)
# ============================================================

@perfil_requerido(ADMINISTRADOR, SUPERVISOR)
def puntaje_equipo(request):
    hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)

    periodos, periodo = elegir_periodo(request.GET.get("periodo"), hoy)
    delegacion = elegir_delegacion(request.user, request.GET.get("delegacion"))

    resumen = None
    if periodo is not None and delegacion is not None:
        funcionarios = (
            PerfilUsuario.objects
            .filter(delegacion=delegacion, usuario__is_active=True)
            .select_related("usuario", "cargo", "delegacion")
        )
        resumen = calcular_resumen_equipo(funcionarios, periodo, hoy)

    return render(
        request,
        "puntaje_equipo/equipo.html",
        {
            "periodos": periodos,
            "periodo": periodo,
            "delegacion": delegacion,
            "delegaciones": Delegacion.objects.filter(activo=True) if es_global(request.user) else None,
            "resumen": resumen,
            "fecha_actual": hoy,
            "ausencias_integradas": False,
        },
    )
