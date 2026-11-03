from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from delegacionesAPP.models import Servicio

from .ambito import (
    SIN_DELEGACION,
    compromisos_visibles,
    delegacion_id_de,
    es_global,
    verificar_acceso_compromiso,
    verificar_delegacion_destino,
)
from .forms import (
    AsignacionCompromisoForm,
    CompromisoForm,
    RegistroAvanceForm,
)
from .models import AdjuntoAvance, AsignacionCompromiso, Compromiso


def resumen_semaforo(compromisos):
    """Cantidad de compromisos activos por color, sin consultas por fila."""
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0}

    for fila in compromisos.filter(activo=True).values(
        "estado"
    ).annotate(total=Count("pk")):
        if fila["estado"] in resumen:
            resumen[fila["estado"]] = fila["total"]

    return resumen


def obtener_compromiso(usuario, pk, queryset=None):
    """Busca el compromiso y verifica que esté dentro del ámbito."""
    if queryset is None:
        queryset = Compromiso.objects.select_related("delegacion", "servicio")

    compromiso = get_object_or_404(queryset, pk=pk)
    verificar_acceso_compromiso(usuario, compromiso)

    return compromiso


def eliminar_archivos(storage, nombres):
    """Borra del disco los archivos de una transacción que se revirtió."""
    for nombre in nombres:
        try:
            storage.delete(nombre)
        except OSError:
            pass


# ============================================================
# MANTENEDOR: COMPROMISOS DEL TUBO DE GESTIÓN
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.view_compromiso", raise_exception=True)
def compromiso_lista(request):
    busqueda = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    situacion = request.GET.get("situacion", "activos")

    # Ámbito territorial: cada perfil solo ve los compromisos de su
    # delegación (el Administrador ve todos).
    visibles = compromisos_visibles(request.user, Compromiso.objects.all())

    compromisos = visibles.select_related("delegacion", "servicio")

    if busqueda:
        compromisos = compromisos.filter(
            Q(tarea__icontains=busqueda)
            | Q(delegacion__nombre__icontains=busqueda)
        )

    if estado in ("verde", "amarillo", "rojo"):
        compromisos = compromisos.filter(estado=estado)

    if situacion == "activos":
        compromisos = compromisos.filter(activo=True)
    elif situacion == "inactivos":
        compromisos = compromisos.filter(activo=False)

    return render(
        request,
        "tubo_gestion/tablero_metas.html",
        {
            "compromisos": compromisos,
            "busqueda": busqueda,
            "estado": estado,
            "situacion": situacion,
            "resumen": resumen_semaforo(visibles),
            "total_activos": visibles.filter(activo=True).count(),
            "total_inactivos": visibles.filter(activo=False).count(),
            "sin_delegacion": (
                not es_global(request.user)
                and delegacion_id_de(request.user) is None
            ),
            "aviso_sin_delegacion": SIN_DELEGACION,
        },
    )


@login_required
@permission_required("tubo_gestionAPP.add_compromiso", raise_exception=True)
def compromiso_crear(request):
    if request.method == "POST":
        form = CompromisoForm(request.POST)

        if form.is_valid():
            compromiso = form.save()

            messages.success(
                request,
                "Compromiso registrado correctamente. "
                f"Estado calculado: {compromiso.get_estado_display()}.",
            )
            return redirect("compromiso_lista")
    else:
        form = CompromisoForm()

    return render(
        request,
        "tubo_gestion/compromiso_form.html",
        {
            "form": form,
            "titulo": "Registrar compromiso",
            "es_edicion": False,
        },
    )


@login_required
@permission_required("tubo_gestionAPP.change_compromiso", raise_exception=True)
def compromiso_editar(request, pk):
    compromiso = obtener_compromiso(request.user, pk)

    if request.method == "POST":
        form = CompromisoForm(request.POST, instance=compromiso)

        if form.is_valid():
            compromiso = form.save()

            messages.success(
                request,
                "Compromiso actualizado correctamente. "
                f"Estado calculado: {compromiso.get_estado_display()}.",
            )
            return redirect("compromiso_lista")
    else:
        form = CompromisoForm(instance=compromiso)

    return render(
        request,
        "tubo_gestion/compromiso_form.html",
        {
            "form": form,
            "compromiso": compromiso,
            "titulo": f"Editar compromiso: {compromiso.tarea}",
            "es_edicion": True,
        },
    )


@login_required
@permission_required("tubo_gestionAPP.delete_compromiso", raise_exception=True)
@require_POST
def compromiso_cambiar_estado(request, pk):
    compromiso = obtener_compromiso(request.user, pk, Compromiso.objects.all())

    compromiso.activo = not compromiso.activo
    compromiso.save(update_fields=["activo"])

    if compromiso.activo:
        messages.success(
            request,
            "Compromiso reactivado correctamente.",
        )
    else:
        messages.success(
            request,
            "Compromiso dado de baja. Puede reactivarlo cuando sea "
            "necesario.",
        )

    return redirect("compromiso_lista")


# ============================================================
# FASE 4 - TRANSACCIÓN 1: ASIGNACIÓN DEL COMPROMISO (SUPERVISOR)
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.change_compromiso", raise_exception=True)
def compromiso_asignar(request, pk):
    """
    Asigna un compromiso a una delegación y a un servicio de esa
    delegación.

    Toda la operación ocurre dentro de una única transacción:

      1. se bloquea la fila del compromiso con SELECT ... FOR UPDATE,
      2. se desactiva la asignación vigente (no se elimina: queda como
         historial),
      3. se crea la nueva asignación,
      4. se actualizan delegación y servicio del compromiso.

    Si cualquier paso falla, la transacción se revierte completa y el
    compromiso queda exactamente como estaba.
    """
    compromiso = obtener_compromiso(request.user, pk)

    if request.method == "POST":
        form = AsignacionCompromisoForm(request.POST, usuario=request.user)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # Bloqueo pesimista: dos supervisores asignando el
                    # mismo compromiso a la vez se serializan aquí.
                    compromiso = Compromiso.objects.select_for_update().get(
                        pk=pk
                    )

                    # Con la fila bloqueada se repite el control de
                    # ámbito: otro usuario pudo reasignarlo entre la carga
                    # de la página y este POST.
                    verificar_acceso_compromiso(request.user, compromiso)
                    verificar_delegacion_destino(
                        request.user, form.cleaned_data["delegacion"].pk
                    )

                    if not compromiso.activo:
                        raise ValidationError(
                            "No se puede asignar un compromiso dado de "
                            "baja. Reactívelo primero."
                        )

                    # Revalidación contra la base, ya con la fila
                    # bloqueada: el servicio pudo darse de baja entre la
                    # carga del formulario y este POST.
                    servicio = Servicio.objects.select_related(
                        "delegacion"
                    ).filter(pk=form.cleaned_data["servicio"].pk).first()

                    if servicio is None:
                        raise ValidationError(
                            "El servicio seleccionado ya no existe."
                        )

                    if not servicio.activo or not servicio.delegacion.activo:
                        raise ValidationError(
                            "El servicio seleccionado está dado de baja."
                        )

                    if (
                        servicio.delegacion_id
                        != form.cleaned_data["delegacion"].pk
                    ):
                        raise ValidationError(
                            "El servicio seleccionado no pertenece a la "
                            "delegación."
                        )

                    # La asignación anterior se conserva como historial.
                    AsignacionCompromiso.objects.filter(
                        compromiso=compromiso,
                        activo=True,
                    ).update(activo=False)

                    asignacion = form.save(commit=False)
                    asignacion.compromiso = compromiso
                    asignacion.usuario_asignador = request.user
                    asignacion.save()

                    compromiso.delegacion = asignacion.delegacion
                    compromiso.servicio = asignacion.servicio
                    compromiso.save(
                        update_fields=["delegacion", "servicio", "estado"]
                    )

            except ValidationError as error:
                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            else:
                messages.success(
                    request,
                    "Compromiso asignado a "
                    f"{asignacion.delegacion.nombre} / "
                    f"{asignacion.servicio.nombre}.",
                )
                return redirect("compromiso_historial", pk=compromiso.pk)
    else:
        form = AsignacionCompromisoForm(usuario=request.user)

    return render(
        request,
        "tubo_gestion/compromiso_asignar.html",
        {
            "form": form,
            "compromiso": compromiso,
            "asignacion_actual": compromiso.asignaciones.filter(
                activo=True
            ).select_related("delegacion", "servicio").first(),
        },
    )


# ============================================================
# FASE 4 - TRANSACCIÓN 2: REGISTRO DE AVANCE (ADMINISTRATIVO)
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.add_registroavance", raise_exception=True)
def compromiso_avance(request, pk):
    """
    Registra un avance sobre un compromiso asignado.

    Toda la operación ocurre dentro de una única transacción:

      1. se bloquea la fila del compromiso con SELECT ... FOR UPDATE,
      2. se valida que esté activo y con asignación vigente,
      3. se guarda el registro de avance con su evidencia y sus archivos,
      4. se actualiza el cumplimiento y el semáforo del compromiso.

    El registro histórico nunca se modifica ni se elimina: cada avance
    es una fila nueva. Si la transacción se revierte, también se borran
    del disco los archivos que alcanzaron a guardarse.
    """
    compromiso = obtener_compromiso(request.user, pk)

    if request.method == "POST":
        form = RegistroAvanceForm(request.POST, request.FILES)

        if form.is_valid():
            storage = AdjuntoAvance._meta.get_field("archivo").storage
            guardados = []

            try:
                with transaction.atomic():
                    compromiso = Compromiso.objects.select_for_update().get(
                        pk=pk
                    )

                    # Con la fila bloqueada se repite el control de
                    # ámbito: el compromiso pudo reasignarse a otra
                    # delegación entre la carga de la página y este POST.
                    verificar_acceso_compromiso(request.user, compromiso)

                    if not compromiso.activo:
                        raise ValidationError(
                            "No se puede registrar avance en un compromiso "
                            "dado de baja."
                        )

                    if not compromiso.asignaciones.filter(
                        activo=True
                    ).exists():
                        raise ValidationError(
                            "El compromiso no tiene una asignación vigente. "
                            "Solicite al Supervisor que lo asigne antes de "
                            "registrar avances."
                        )

                    nuevo_porcentaje = form.cleaned_data["porcentaje_avance"]

                    # Con la fila bloqueada, la comparación es confiable:
                    # ningún otro usuario puede haber subido el
                    # cumplimiento entre la validación y el guardado.
                    if nuevo_porcentaje < compromiso.cumplimiento:
                        raise ValidationError(
                            "El avance no puede ser menor al cumplimiento "
                            f"actual ({compromiso.cumplimiento}%). Si hubo "
                            "un error, registre la corrección con una "
                            "observación que la explique."
                        )

                    registro = form.save(commit=False)
                    registro.compromiso = compromiso
                    registro.usuario_registro = request.user
                    registro.save()

                    for archivo in form.cleaned_data["adjuntos"]:
                        adjunto = AdjuntoAvance(
                            registro=registro,
                            nombre_original=archivo.name,
                            tamano=archivo.size,
                            tipo_contenido=(
                                getattr(archivo, "content_type", "") or ""
                            )[:100],
                        )
                        adjunto.archivo.save(archivo.name, archivo, save=False)
                        guardados.append(adjunto.archivo.name)
                        adjunto.save()

                    compromiso.cumplimiento = registro.porcentaje_avance
                    compromiso.save(
                        update_fields=["cumplimiento", "estado"]
                    )

            except ValidationError as error:
                eliminar_archivos(storage, guardados)

                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            except BaseException:
                eliminar_archivos(storage, guardados)
                raise
            else:
                messages.success(
                    request,
                    "Avance registrado: "
                    f"{compromiso.cumplimiento}% "
                    f"({compromiso.get_estado_display()}).",
                )
                return redirect("compromiso_historial", pk=compromiso.pk)
    else:
        form = RegistroAvanceForm(
            initial={"porcentaje_avance": compromiso.cumplimiento}
        )

    return render(
        request,
        "tubo_gestion/compromiso_avance.html",
        {
            "form": form,
            "compromiso": compromiso,
            "asignacion_actual": compromiso.asignaciones.filter(
                activo=True
            ).select_related("delegacion", "servicio").first(),
        },
    )


# ============================================================
# FASE 4 - HISTORIAL DEL COMPROMISO (SOLO LECTURA)
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.view_compromiso", raise_exception=True)
def compromiso_historial(request, pk):
    """
    Muestra la trazabilidad completa del compromiso: asignaciones y
    avances, del más reciente al más antiguo. No permite modificar ni
    eliminar nada.
    """
    compromiso = obtener_compromiso(request.user, pk)

    asignaciones = compromiso.asignaciones.select_related(
        "delegacion", "servicio", "usuario_asignador"
    )

    avances = compromiso.avances.select_related(
        "usuario_registro"
    ).prefetch_related("adjuntos")

    return render(
        request,
        "tubo_gestion/compromiso_historial.html",
        {
            "compromiso": compromiso,
            "asignaciones": asignaciones,
            "avances": avances,
            "asignacion_actual": asignaciones.filter(activo=True).first(),
        },
    )


@login_required
@permission_required("tubo_gestionAPP.view_registroavance", raise_exception=True)
def adjunto_descargar(request, pk):
    """
    Entrega un archivo adjunto solo a quien puede ver el compromiso.

    Se fuerza la descarga (Content-Disposition: attachment) con el nombre
    original, para que el navegador nunca interprete el archivo como una
    página del sitio.
    """
    adjunto = get_object_or_404(
        AdjuntoAvance.objects.select_related("registro__compromiso"),
        pk=pk,
    )
    verificar_acceso_compromiso(request.user, adjunto.registro.compromiso)

    try:
        archivo = adjunto.archivo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("El archivo ya no se encuentra en el servidor.")

    return FileResponse(
        archivo,
        as_attachment=True,
        filename=adjunto.nombre_original,
    )


# Alias histórico: los paneles y el menú usan "tablero_metas".
tablero_metas = compromiso_lista


# ============================================================
# PORTADA DEL MÓDULO
# ============================================================

@login_required
@permission_required("tubo_gestionAPP.view_compromiso", raise_exception=True)
def inicio(request):
    resumen = resumen_semaforo(
        compromisos_visibles(request.user, Compromiso.objects.all())
    )

    return render(
        request,
        "tubo_gestion/inicio.html",
        {
            "resumen": resumen,
            "total": sum(resumen.values()),
        },
    )
