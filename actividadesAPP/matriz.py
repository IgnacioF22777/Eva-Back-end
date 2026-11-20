
"""
Vista de la matriz de puntajes y resumen de ingresos.
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from sgr_maestrosAPP.models import Periodo

from .models import ZONA_CHILE
from .puntajes import obtener_mi_matriz
from .resumen_ingresos import obtener_resumen_ingresos
from .views import obtener_funcionario


@login_required
@permission_required(
    "actividadesAPP.view_registroactividad",
    raise_exception=True,
)
def matriz(request):
    """
    Muestra las metas, puntajes y resumen de ingresos
    del funcionario que inició sesión.
    """

    funcionario = obtener_funcionario(request.user)

    hoy = timezone.localdate(
        timezone.now(),
        timezone=ZONA_CHILE,
    )

    periodos = Periodo.objects.order_by(
        "-fecha_inicio",
        "-pk",
    )

    periodo_id = request.GET.get("periodo", "").strip()

    if periodo_id:
        if not periodo_id.isdecimal():
            raise Http404(
                "El período seleccionado no es válido."
            )

        periodo = get_object_or_404(
            Periodo,
            pk=int(periodo_id),
        )
    else:
        periodo = periodos.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
        ).first()

        if periodo is None:
            periodo = periodos.filter(
                fecha_inicio__lte=hoy,
            ).first()

    datos_matriz = None
    resumen = None

    if periodo is not None:
        # Pendiente de integrar las ausencias reales.
        dias_ausencia = 0

        datos_matriz = obtener_mi_matriz(
            funcionario=funcionario,
            periodo=periodo,
            dias_ausencia=dias_ausencia,
        )

        resumen = obtener_resumen_ingresos(
            funcionario=funcionario,
            periodo=periodo,
            fecha_referencia=hoy,
        )

    contexto = {
        "funcionario": funcionario,
        "cargo": funcionario.cargo,
        "periodos": periodos,
        "periodo": periodo,
        "matriz": datos_matriz,
        "resumen": resumen,
        "fecha_actual": hoy,
        "ausencias_integradas": False,
    }

    return render(
        request,
        "actividades/matriz.html",
        contexto,
    )
