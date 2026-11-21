from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from seguridadAPP.perfiles import ADMINISTRADOR, SUPERVISOR, perfil_de
from tubo_gestionAPP.ambito import SIN_DELEGACION, delegacion_id_de, es_global

from .forms import CartaForm
from .models import DIAS_ALERTA, CartaOficinaPartes


POR_PAGINA = 25


def cartas_visibles(usuario):
    """Cada funcionario ve las cartas de su delegación; el Administrador, todas."""
    cartas = CartaOficinaPartes.objects.select_related("delegacion", "registrada_por")
    if es_global(usuario):
        return cartas
    propia = delegacion_id_de(usuario)
    return cartas.filter(delegacion_id=propia) if propia else cartas.none()


def obtener_carta(usuario, pk):
    carta = get_object_or_404(CartaOficinaPartes, pk=pk)
    if not es_global(usuario) and carta.delegacion_id != delegacion_id_de(usuario):
        raise PermissionDenied(
            "La carta pertenece a otra delegación: su perfil solo puede "
            "operar las cartas de su delegación."
        )
    return carta


def puede_modificar(usuario, carta, perfil=None):
    """
    Pauta Eva 3: todos los funcionarios de la delegación consultan el tubo
    de cartas, pero cada funcionario solo modifica las cartas que él
    registró y mientras sigan «En proceso» (no aprobadas ni cerradas). El
    delegado (Supervisor) y el Administrador hacen el seguimiento de todas
    las cartas de su ámbito.
    """
    perfil = perfil or perfil_de(usuario)
    if perfil in (ADMINISTRADOR, SUPERVISOR):
        return True
    return carta.registrada_por_id == usuario.pk and carta.estado == CartaOficinaPartes.EN_PROCESO


NO_MODIFICABLE = (
    "Solo puede modificar las cartas que usted registró y mientras sigan "
    "«En proceso». El seguimiento posterior lo hace el delegado."
)


# ============================================================
# TUBO DE CARTAS DE OFICINA DE PARTES
# ============================================================

@login_required
@permission_required("oficinaPartesAPP.view_cartaoficinapartes", raise_exception=True)
def carta_lista(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    destinatario = request.GET.get("destinatario", "")
    solo_atrasadas = request.GET.get("atrasadas") == "1"
    vigencia = request.GET.get("vigencia", "activos")

    visibles = cartas_visibles(request.user)
    cartas = visibles

    if busqueda:
        cartas = cartas.filter(
            Q(remitente__icontains=busqueda)
            | Q(tema__icontains=busqueda)
            | Q(numero_ingreso__icontains=busqueda)
            | Q(encargado_seguimiento__icontains=busqueda)
        )

    if estado in dict(CartaOficinaPartes.ESTADOS):
        cartas = cartas.filter(estado=estado)
    else:
        estado = ""

    if destinatario in dict(CartaOficinaPartes.DESTINATARIOS):
        cartas = cartas.filter(destinatario=destinatario)
    else:
        destinatario = ""

    limite = date.today() - timedelta(days=DIAS_ALERTA)
    if solo_atrasadas:
        cartas = cartas.filter(estado=CartaOficinaPartes.EN_PROCESO, fecha_recepcion__lt=limite)

    if vigencia == "activos":
        cartas = cartas.filter(activo=True)
    elif vigencia == "inactivos":
        cartas = cartas.filter(activo=False)
    else:
        vigencia = "todos"

    # Resumen como el encabezado de la hoja TUBO CARTAS: cantidad por estado.
    vigentes = visibles.filter(activo=True)
    por_estado = dict(vigentes.values_list("estado").annotate(total=Count("pk")))
    resumen = [
        {"clave": clave, "nombre": nombre, "total": por_estado.get(clave, 0)}
        for clave, nombre in CartaOficinaPartes.ESTADOS
    ]

    pagina = Paginator(cartas, POR_PAGINA).get_page(request.GET.get("pagina"))
    perfil = perfil_de(request.user)
    for carta in pagina:
        carta.editable = puede_modificar(request.user, carta, perfil)
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(
        request,
        "oficina_partes/carta_lista.html",
        {
            "pagina": pagina,
            "busqueda": busqueda,
            "estado": estado,
            "destinatario": destinatario,
            "solo_atrasadas": solo_atrasadas,
            "vigencia": vigencia,
            "parametros": parametros.urlencode(),
            "estados": CartaOficinaPartes.ESTADOS,
            "destinatarios": CartaOficinaPartes.DESTINATARIOS,
            "resumen": resumen,
            "total_vigentes": vigentes.count(),
            "total_atrasadas": vigentes.filter(
                estado=CartaOficinaPartes.EN_PROCESO, fecha_recepcion__lt=limite
            ).count(),
            "dias_alerta": DIAS_ALERTA,
            "sin_delegacion": not es_global(request.user) and delegacion_id_de(request.user) is None,
            "aviso_sin_delegacion": SIN_DELEGACION,
        },
    )


@login_required
@permission_required("oficinaPartesAPP.add_cartaoficinapartes", raise_exception=True)
def carta_crear(request):
    if not es_global(request.user) and delegacion_id_de(request.user) is None:
        raise PermissionDenied(SIN_DELEGACION)

    if request.method == "POST":
        form = CartaForm(request.POST, usuario=request.user)
        if form.is_valid():
            carta = form.save(commit=False)
            carta.registrada_por = request.user
            carta.save()
            messages.success(request, "Carta registrada en el tubo correctamente.")
            return redirect("oficina_partes:carta_lista")
    else:
        form = CartaForm(usuario=request.user)

    return render(
        request,
        "oficina_partes/carta_form.html",
        {"form": form, "titulo": "Registrar carta de Oficina de Partes"},
    )


@login_required
@permission_required("oficinaPartesAPP.change_cartaoficinapartes", raise_exception=True)
def carta_editar(request, pk):
    carta = obtener_carta(request.user, pk)
    if not puede_modificar(request.user, carta):
        raise PermissionDenied(NO_MODIFICABLE)

    if request.method == "POST":
        form = CartaForm(request.POST, instance=carta, usuario=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Carta actualizada correctamente.")
            return redirect("oficina_partes:carta_lista")
    else:
        form = CartaForm(instance=carta, usuario=request.user)

    return render(
        request,
        "oficina_partes/carta_form.html",
        {"form": form, "titulo": f"Seguimiento de la carta: {carta}", "carta": carta},
    )


@login_required
@permission_required("oficinaPartesAPP.delete_cartaoficinapartes", raise_exception=True)
@require_POST
def carta_cambiar_estado(request, pk):
    carta = obtener_carta(request.user, pk)

    # Baja lógica: una carta ingresada por error se anula y puede reactivarse.
    carta.activo = not carta.activo
    carta.save(update_fields=["activo"])

    messages.success(
        request,
        "Carta reactivada." if carta.activo else "Carta anulada. Puede reactivarla cuando sea necesario.",
    )
    return redirect("oficina_partes:carta_lista")
