from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .ambito import registros_visibles, verificar_puede_registrar, verificar_puede_ver
from .forms import AjusteDesempenoForm, AusenciaForm
from .models import AjusteDesempeno, Ausencia


def filtrar(queryset, request, tipos):
    """Búsqueda por funcionario, filtro por tipo y por estado (común a los dos listados)."""
    busqueda = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "")
    estado = request.GET.get("estado", "vigentes")

    if busqueda:
        queryset = queryset.filter(
            Q(funcionario__first_name__icontains=busqueda)
            | Q(funcionario__last_name__icontains=busqueda)
            | Q(funcionario__perfil__rut__icontains=busqueda)
        )

    if tipo in dict(tipos):
        queryset = queryset.filter(tipo=tipo)
    else:
        tipo = ""

    if estado == "vigentes":
        queryset = queryset.filter(activo=True)
    elif estado == "anulados":
        queryset = queryset.filter(activo=False)
    else:
        estado = "todos"

    return queryset, {"busqueda": busqueda, "tipo": tipo, "estado": estado, "tipos": tipos}


def guardar_formulario(request, form):
    """Guarda con el usuario que registra; los errores del modelo vuelven al formulario."""
    registro = form.save(commit=False)

    # Defensa en profundidad: el formulario ya limita la lista de
    # funcionarios, pero se vuelve a comprobar en el servidor (403).
    verificar_puede_registrar(request.user, registro.funcionario)

    if registro.pk is None:
        registro.registrado_por = request.user

    try:
        registro.full_clean()
    except ValidationError as error:
        for campo, mensajes in error.message_dict.items():
            form.add_error(campo if campo in form.fields else None, mensajes)
        return None

    registro.save()
    return registro


# ============================================================
# AUSENCIAS (R9)
# ============================================================

@login_required
@permission_required("matrizAPP.view_ausencia", raise_exception=True)
def ausencia_lista(request):
    ausencias = registros_visibles(
        request.user,
        Ausencia.objects.select_related("funcionario", "delegacion", "registrado_por"),
    )
    ausencias, filtros = filtrar(ausencias, request, Ausencia.TIPOS)

    return render(request, "matriz/ausencia_lista.html", {"ausencias": ausencias, **filtros})


@login_required
@permission_required("matrizAPP.add_ausencia", raise_exception=True)
def ausencia_crear(request):
    form = AusenciaForm(request.POST or None, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        ausencia = guardar_formulario(request, form)
        if ausencia:
            messages.success(
                request,
                f"Ausencia registrada: {ausencia.dias} día(s) hábil(es) que se "
                "descuentan de la meta del funcionario.",
            )
            return redirect("matriz:ausencia_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": "Registrar ausencia",
        "ayuda": (
            "Los días hábiles se calculan solos (sin fines de semana ni "
            "feriados) y se descuentan de la meta del funcionario."
        ),
        "volver": "matriz:ausencia_lista",
    })


@login_required
@permission_required("matrizAPP.change_ausencia", raise_exception=True)
def ausencia_editar(request, pk):
    ausencia = get_object_or_404(Ausencia.objects.select_related("funcionario"), pk=pk)
    verificar_puede_registrar(request.user, ausencia.funcionario)

    form = AusenciaForm(request.POST or None, instance=ausencia, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        if guardar_formulario(request, form):
            messages.success(request, "Ausencia actualizada correctamente.")
            return redirect("matriz:ausencia_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": f"Editar ausencia de {ausencia.funcionario.get_full_name()}",
        "volver": "matriz:ausencia_lista",
    })


@login_required
@permission_required("matrizAPP.change_ausencia", raise_exception=True)
@require_POST
def ausencia_cambiar_estado(request, pk):
    ausencia = get_object_or_404(Ausencia.objects.select_related("funcionario"), pk=pk)
    verificar_puede_registrar(request.user, ausencia.funcionario)

    ausencia.activo = not ausencia.activo

    if ausencia.activo:
        # Al reactivar, no puede cruzarse con otra ausencia vigente.
        try:
            ausencia.full_clean()
        except ValidationError as error:
            messages.error(request, "No se puede reactivar: " + " ".join(error.messages))
            return redirect("matriz:ausencia_lista")

    ausencia.save(update_fields=["activo"])
    messages.success(
        request,
        "Ausencia reactivada." if ausencia.activo
        else "Ausencia anulada: ya no descuenta días de la meta.",
    )
    return redirect("matriz:ausencia_lista")


# ============================================================
# FELICITACIONES Y RECLAMOS (R8)
# ============================================================

@login_required
@permission_required("matrizAPP.view_ajustedesempeno", raise_exception=True)
def ajuste_lista(request):
    ajustes = registros_visibles(
        request.user,
        AjusteDesempeno.objects.select_related("funcionario", "delegacion", "registrado_por"),
    )
    ajustes, filtros = filtrar(ajustes, request, AjusteDesempeno.TIPOS)

    return render(request, "matriz/ajuste_lista.html", {"ajustes": ajustes, **filtros})


@login_required
@permission_required("matrizAPP.add_ajustedesempeno", raise_exception=True)
def ajuste_crear(request):
    form = AjusteDesempenoForm(request.POST or None, request.FILES or None, usuario=request.user)

    if request.method == "POST" and form.is_valid():
        ajuste = guardar_formulario(request, form)
        if ajuste:
            messages.success(request, f"{ajuste.get_tipo_display()} registrada correctamente.")
            return redirect("matriz:ajuste_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": "Registrar felicitación o reclamo",
        "ayuda": (
            "Solo valen si llegaron por escrito al delegado o a la "
            "delegación (correo, WhatsApp al delegado, libro de "
            "observaciones o carta). El respaldo es obligatorio. Cada "
            "felicitación suma 10% y cada reclamo resta 20%; el total "
            "nunca supera 120%."
        ),
        "volver": "matriz:ajuste_lista",
        "con_archivos": True,
    })


@login_required
@permission_required("matrizAPP.change_ajustedesempeno", raise_exception=True)
def ajuste_editar(request, pk):
    ajuste = get_object_or_404(AjusteDesempeno.objects.select_related("funcionario"), pk=pk)
    verificar_puede_registrar(request.user, ajuste.funcionario)

    form = AjusteDesempenoForm(
        request.POST or None, request.FILES or None, instance=ajuste, usuario=request.user,
    )

    if request.method == "POST" and form.is_valid():
        if guardar_formulario(request, form):
            messages.success(request, "Registro actualizado correctamente.")
            return redirect("matriz:ajuste_lista")

    return render(request, "matriz/formulario.html", {
        "form": form,
        "titulo": f"Editar {ajuste.get_tipo_display().split(' (')[0].lower()}",
        "volver": "matriz:ajuste_lista",
        "con_archivos": True,
    })


@login_required
@permission_required("matrizAPP.change_ajustedesempeno", raise_exception=True)
@require_POST
def ajuste_cambiar_estado(request, pk):
    ajuste = get_object_or_404(AjusteDesempeno.objects.select_related("funcionario"), pk=pk)
    verificar_puede_registrar(request.user, ajuste.funcionario)

    ajuste.activo = not ajuste.activo
    ajuste.save(update_fields=["activo"])
    messages.success(
        request,
        "Registro reactivado." if ajuste.activo
        else "Registro anulado: ya no afecta el cumplimiento.",
    )
    return redirect("matriz:ajuste_lista")


@login_required
@permission_required("matrizAPP.view_ajustedesempeno", raise_exception=True)
def ajuste_respaldo(request, pk):
    """
    Descarga protegida del respaldo, igual que los adjuntos de avances:
    exige sesión, permiso y que el registro esté en el ámbito del usuario.
    Se fuerza la descarga para que el navegador no lo abra como página.
    """
    ajuste = get_object_or_404(AjusteDesempeno, pk=pk)
    verificar_puede_ver(request.user, ajuste)

    try:
        archivo = ajuste.respaldo.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("El archivo ya no se encuentra en el servidor.")

    return FileResponse(archivo, as_attachment=True, filename=ajuste.nombre_original)
