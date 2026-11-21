from django.core.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apiAPP.permisos import exigir_permiso, obtener_o_404
from apiAPP.views import (
    RESPUESTA_400,
    RESPUESTA_403,
    RESPUESTA_404,
    RESPUESTA_409,
    conflicto,
)

from .ambito import compromisos_visibles, verificar_acceso_compromiso
from .models import AsignacionCompromiso, Compromiso
from .serializers_asignaciones import (
    AsignacionAnularSerializer,
    AsignacionCorregirSerializer,
    AsignacionCrearSerializer,
    AsignacionSerializer,
)
from .transacciones import anular_asignacion, asignar_compromiso, corregir_asignacion


# ============================================================
# API: TRANSACCIÓN 1 (T1) - ASIGNACIÓN DEL COMPROMISO
# ============================================================
#   GET    /api/asignaciones/        historial (filtro ?compromiso=<id>)
#   POST   /api/asignaciones/        asignar o reasignar
#   GET    /api/asignaciones/<id>/   consultar
#   PUT    /api/asignaciones/<id>/   corregir la observación
#   DELETE /api/asignaciones/<id>/   anular (baja lógica, con motivo)
#
# Mismos permisos que la web: consultar exige ver asignaciones; asignar,
# corregir y anular exigen modificar compromisos (perfil Supervisor o
# Administrador). Usa las funciones de transacciones.py.

TAG = "Asignaciones (transacción T1)"


def _mensaje(error):
    return " ".join(error.messages)


def _datos(request, asignacion):
    asignacion = AsignacionCompromiso.objects.select_related(
        "compromiso", "delegacion", "servicio", "usuario_asignador", "anulado_por"
    ).get(pk=asignacion.pk)
    return AsignacionSerializer(asignacion, context={"request": request}).data


def _exigir_permiso_escritura(request):
    """Igual que la vista web de T1: modificar compromisos."""
    exigir_permiso(request, Compromiso, "change")


PARAM_COMPROMISO = OpenApiParameter(
    name="compromiso",
    type=OpenApiTypes.INT,
    description="Id del compromiso: muestra solo su historial de asignaciones.",
)

PARAM_VIGENTES = OpenApiParameter(
    name="vigentes",
    type=OpenApiTypes.BOOL,
    description="true: solo la asignación vigente de cada compromiso.",
)


@extend_schema(
    methods=["GET"],
    tags=[TAG],
    summary="Consultar historial de asignaciones",
    description="Solo los compromisos de su ámbito (delegación).",
    parameters=[PARAM_COMPROMISO, PARAM_VIGENTES],
    responses={200: AsignacionSerializer(many=True), 400: RESPUESTA_400, 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=[TAG],
    summary="Asignar compromiso (T1)",
    description=(
        "Transacción atómica: bloquea el compromiso, verifica el ámbito, "
        "revalida que el servicio esté activo y pertenezca a la "
        "delegación, deja la asignación anterior como historial y "
        "actualiza la delegación y el servicio del compromiso."
    ),
    request=AsignacionCrearSerializer,
    responses={
        201: AsignacionSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
    examples=[
        OpenApiExample(
            "Asignar a Delegación Centro / Trámites",
            value={
                "compromiso": 1,
                "delegacion": 1,
                "servicio": 2,
                "observacion": "Coordinar con la unidad de informática.",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Servicio de otra delegación (409)",
            value={"detail": "El servicio seleccionado no pertenece a la delegación."},
            response_only=True,
            status_codes=["409"],
        ),
    ],
)
@api_view(["GET", "POST"])
def asignacion_lista(request):
    if request.method == "GET":
        exigir_permiso(request, AsignacionCompromiso, "view")

        asignaciones = AsignacionCompromiso.objects.filter(
            compromiso__in=compromisos_visibles(request.user, Compromiso.objects.all())
        ).select_related(
            "compromiso", "delegacion", "servicio", "usuario_asignador", "anulado_por"
        )

        compromiso_id = request.query_params.get("compromiso")
        if compromiso_id:
            if not str(compromiso_id).isdigit():
                return Response(
                    {"compromiso": ["Debe ser un número entero."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            asignaciones = asignaciones.filter(compromiso_id=int(compromiso_id))

        if request.query_params.get("vigentes") == "true":
            asignaciones = asignaciones.filter(activo=True)

        return Response(
            AsignacionSerializer(asignaciones, many=True, context={"request": request}).data
        )

    _exigir_permiso_escritura(request)

    entrada = AsignacionCrearSerializer(data=request.data)
    if not entrada.is_valid():
        return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

    datos = entrada.validated_data
    compromiso = obtener_o_404(
        Compromiso.objects.all(), datos["compromiso"], "Compromiso no encontrado."
    )
    verificar_acceso_compromiso(request.user, compromiso)

    try:
        asignacion, _ = asignar_compromiso(
            request.user,
            compromiso.pk,
            datos["delegacion"],
            datos["servicio"],
            datos.get("observacion", ""),
        )
    except ValidationError as error:
        return conflicto(_mensaje(error))

    return Response(_datos(request, asignacion), status=status.HTTP_201_CREATED)


@extend_schema(
    methods=["GET"],
    tags=[TAG],
    summary="Consultar asignación",
    responses={200: AsignacionSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=[TAG],
    summary="Corregir la observación de la asignación vigente",
    description=(
        "La delegación y el servicio no se corrigen: para cambiarlos se "
        "registra una nueva asignación (POST), así el historial muestra la "
        "reasignación."
    ),
    request=AsignacionCorregirSerializer,
    responses={
        200: AsignacionSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
)
@extend_schema(
    methods=["DELETE"],
    tags=[TAG],
    summary="Anular la asignación vigente (baja lógica)",
    description=(
        "La asignación queda en el historial como anulada, con el motivo, y "
        "el compromiso vuelve a la asignación anterior (o queda sin "
        "asignar). Se rechaza (409) si ya tiene avances registrados. El "
        "motivo se envía en el cuerpo JSON o en ?motivo=."
    ),
    request=AsignacionAnularSerializer,
    parameters=[
        OpenApiParameter(
            name="motivo",
            type=OpenApiTypes.STR,
            description="Motivo de la anulación (alternativa al cuerpo JSON).",
        )
    ],
    responses={
        200: AsignacionSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def asignacion_detalle(request, pk):
    if request.method == "GET":
        exigir_permiso(request, AsignacionCompromiso, "view")
    else:
        _exigir_permiso_escritura(request)

    asignacion = obtener_o_404(
        AsignacionCompromiso.objects.select_related("compromiso"),
        pk,
        "Asignación no encontrada.",
    )
    verificar_acceso_compromiso(request.user, asignacion.compromiso)

    if request.method == "GET":
        return Response(_datos(request, asignacion))

    try:
        if request.method in ("PUT", "PATCH"):
            entrada = AsignacionCorregirSerializer(data=request.data)
            if not entrada.is_valid():
                return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

            asignacion, _ = corregir_asignacion(
                request.user, asignacion.pk, entrada.validated_data["observacion"]
            )
        else:
            datos = {
                "motivo": request.data.get("motivo") or request.query_params.get("motivo")
            }
            entrada = AsignacionAnularSerializer(data=datos)
            if not entrada.is_valid():
                return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

            asignacion, _ = anular_asignacion(
                request.user, asignacion.pk, entrada.validated_data["motivo"]
            )
    except ValidationError as error:
        return conflicto(_mensaje(error))

    return Response(_datos(request, asignacion))
