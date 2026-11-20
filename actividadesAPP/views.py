"""Pantallas propias de actividades diarias del SGR (EVA 3, R1–R5).

El funcionario se obtiene desde la sesión, nunca desde parámetros enviados
por el navegador. Cada usuario opera exclusivamente sus propios registros.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from config import exportar

from .forms import RegistroActividadForm
from .models import RegistroActividad, ZONA_CHILE, rango_dia_chile


def obtener_funcionario(usuario):
    """Recupera el perfil del usuario autenticado; sin perfil, acceso denegado."""
    try:
        return usuario.perfil
    except ObjectDoesNotExist as exc:
        raise PermissionDenied(
            "Tu usuario no tiene una ficha de funcionario. "
            "Solicita al administrador que complete tu perfil."
        ) from exc


def registros_propios(usuario):
    """Ámbito estricto: nunca exponer datos de otros funcionarios."""
    funcionario = obtener_funcionario(usuario)
    return RegistroActividad.objects.filter(funcionario=funcionario)


def agregar_error_guardado(formulario, error):
    """Muestra validaciones del servidor (incluido el 8.º ingreso) en el formulario."""
    formulario.add_error(None, " ".join(error.messages))


def filtrar_registros(request):
    """Filtro de situación del listado (también lo usa la exportación)."""
    registros = registros_propios(request.user).select_related("actividad", "verificado_por")

    situacion = request.GET.get("situacion", "activos")
    if situacion == "inactivos":
        registros = registros.filter(activo=False)
    elif situacion != "todos":
        situacion = "activos"
        registros = registros.filter(activo=True)

    return registros, situacion


@login_required
@permission_required("actividadesAPP.view_registroactividad", raise_exception=True)
def actividad_lista(request):
    """Mis actividades y cupos restantes del día chileno."""
    registros, situacion = filtrar_registros(request)

    hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
    inicio, fin = rango_dia_chile(hoy)
    usados_hoy = registros_propios(request.user).filter(
        activo=True,
        fecha_ingreso__gte=inicio,
        fecha_ingreso__lt=fin,
    ).count()
    maximo_diario = getattr(settings, "MAX_INGRESOS_DIARIOS", 7)

    return render(
        request,
        "actividades/actividad_lista.html",
        {
            "registros": registros,
            "situacion": situacion,
            "usados_hoy": usados_hoy,
            "maximo_diario": maximo_diario,
            "restantes_hoy": max(0, maximo_diario - usados_hoy),
        },
    )


@login_required
@permission_required("actividadesAPP.add_registroactividad", raise_exception=True)
def actividad_crear(request):
    """Registra una gestión; R1–R5 se recalculan en el modelo."""
    funcionario = obtener_funcionario(request.user)
    if request.method == "POST":
        formulario = RegistroActividadForm(request.POST, request.FILES, funcionario=funcionario)
        if formulario.is_valid():
            try:
                registro = formulario.save()
            except ValidationError as error:
                # El modelo vuelve a comprobar el cupo dentro de la transacción,
                # incluso si alguien envió dos formularios simultáneamente.
                agregar_error_guardado(formulario, error)
            else:
                if registro.puntua:
                    messages.success(request, "Actividad registrada y válida para puntaje.")
                else:
                    messages.warning(
                        request,
                        "Actividad guardada sin puntaje: "
                        f"{registro.motivo_sin_puntaje}.",
                    )
                return redirect("actividades:lista")
    else:
        formulario = RegistroActividadForm(funcionario=funcionario)

    return render(
        request,
        "actividades/actividad_form.html",
        {
            "form": formulario,
            "titulo": "Registrar actividad diaria",
            "es_edicion": False,
        },
    )


@login_required
@permission_required("actividadesAPP.change_registroactividad", raise_exception=True)
def actividad_editar(request, pk):
    """Modifica solo registros propios, activos y aún dentro del plazo R4."""
    registro = get_object_or_404(registros_propios(request.user), pk=pk, activo=True)
    funcionario = obtener_funcionario(request.user)

    if registro.esta_aprobado:
        messages.error(request, "Un registro aprobado no se puede modificar.")
        return redirect("actividades:lista")

    if request.method == "POST":
        formulario = RegistroActividadForm(
            request.POST,
            request.FILES,
            instance=registro,
            funcionario=funcionario,
        )
        if formulario.is_valid():
            try:
                actualizado = formulario.save()
            except ValidationError as error:
                agregar_error_guardado(formulario, error)
            else:
                if actualizado.puntua:
                    messages.success(request, "Actividad actualizada correctamente.")
                else:
                    messages.warning(
                        request,
                        "Actividad actualizada sin puntaje: "
                        f"{actualizado.motivo_sin_puntaje}.",
                    )
                return redirect("actividades:lista")
    else:
        formulario = RegistroActividadForm(
            instance=registro,
            funcionario=funcionario,
        )

    return render(
        request,
        "actividades/actividad_form.html",
        {
            "form": formulario,
            "titulo": "Editar actividad diaria",
            "es_edicion": True,
            "registro": registro,
        },
    )


@login_required
@permission_required("actividadesAPP.delete_registroactividad", raise_exception=True)
@require_POST
def actividad_cambiar_estado(request, pk):
    """Baja lógica o reactivación, sin eliminar historial ni evadir R3/R4."""
    registro = get_object_or_404(registros_propios(request.user), pk=pk)
    registro.activo = not registro.activo
    try:
        # Al reactivar, el modelo recalcula puntúa y revalida cupos.
        # Si la semana está cerrada, también bloquea el cambio.
        registro.save(update_fields=["activo"])
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if registro.activo:
            messages.success(request, "Actividad reactivada.")
        else:
            messages.success(request, "Actividad dada de baja sin borrar el historial.")
    return redirect("actividades:lista")


# ============================================================
# EXPORTACIÓN A EXCEL Y PDF
# ============================================================
# Igual que el listado, cada funcionario exporta solo sus propios registros.

ENCABEZADOS_ACTIVIDADES = [
    "Código", "Fecha", "Actividad", "Tipo", "Solicitante", "Vecino / Usuario",
    "Teléfono", "Puntaje", "Verificación / motivo", "Fecha de ingreso", "Estado",
]

ETIQUETAS_SITUACION = {
    "activos": "Activas",
    "inactivos": "Inactivas",
    "todos": "Todas",
}


def datos_actividades(request):
    registros, situacion = filtrar_registros(request)
    filas = [
        [
            registro.codigo or "",
            registro.fecha_actividad,
            registro.actividad.nombre,
            (
                "Preparatoria"
                if registro.actividad.tipo_gestion == "PREPARATORIA"
                else "Ejecución"
            ),
            registro.get_solicitante_tipo_display(),
            registro.nombre_usuario or "Sin nombre",
            registro.telefono_usuario or "Sin teléfono",
            "Válida" if registro.puntua else "Sin puntaje",
            f"{registro.get_estado_verificacion_display()}. {registro.motivo_sin_puntaje}".strip(" ."),
            registro.fecha_ingreso,
            exportar.activo_inactivo(registro.activo),
        ]
        for registro in registros
    ]
    return filas, f"situación: {ETIQUETAS_SITUACION[situacion]}"


@login_required
@permission_required("actividadesAPP.view_registroactividad", raise_exception=True)
def exportar_actividades_excel(request):
    filas, _ = datos_actividades(request)
    return exportar.exportar_excel(
        "Mis Actividades Diarias",
        ENCABEZADOS_ACTIVIDADES,
        filas,
        "mis_actividades",
        usuario=request.user,
    )


@login_required
@permission_required("actividadesAPP.view_registroactividad", raise_exception=True)
def exportar_actividades_pdf(request):
    filas, filtros = datos_actividades(request)
    return exportar.exportar_pdf(
        "Mis Actividades Diarias",
        ENCABEZADOS_ACTIVIDADES,
        filas,
        "mis_actividades",
        usuario=request.user,
        anchos=[1.1, 0.8, 1.8, 0.9, 1.1, 1.4, 0.9, 0.8, 1.8, 1.1, 0.7],
        horizontal=True,
        filtros=filtros,
    )
