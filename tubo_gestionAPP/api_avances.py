from django.core.exceptions import ValidationError
from django.http import QueryDict
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
from .forms import RegistroAvanceForm
from .models import Compromiso, RegistroAvance
from .serializers_avances import (
    AvanceAnularSerializer,
    AvanceCorregirSerializer,
    AvanceCrearSerializer,
    RegistroAvanceSerializer,
)
from .transacciones import anular_avance, corregir_avance, registrar_avance


# ============================================================
# API: TRANSACCIÓN 2 (T2) - REGISTRO DE AVANCE DEL COMPROMISO
# ============================================================
#   GET    /api/avances/           historial (filtro ?compromiso=<id>)
#   POST   /api/avances/           registrar avance (JSON o multipart)
#   GET    /api/avances/<id>/      consultar
#   PUT    /api/avances/<id>/      corregir evidencia u observación
#   DELETE /api/avances/<id>/      anular (baja lógica, con motivo)
#
# Usa las mismas funciones que la web (transacciones.py). Respuestas:
#   400 datos inválidos · 403 sin permiso o fuera de ámbito
#   404 no existe       · 409 una regla del negocio lo impide

TAG = "Avances (transacción T2)"


def _mensaje(error):
    return " ".join(error.messages)


def _datos(request, avance):
    avance = RegistroAvance.objects.select_related(
        "compromiso", "usuario_registro", "anulado_por"
    ).prefetch_related("adjuntos").get(pk=avance.pk)
    return RegistroAvanceSerializer(avance, context={"request": request}).data


def _avances_visibles(usuario):
    return RegistroAvance.objects.filter(
        compromiso__in=compromisos_visibles(usuario, Compromiso.objects.all())
    ).select_related(
        "compromiso", "usuario_registro", "anulado_por"
    ).prefetch_related("adjuntos")


PARAM_COMPROMISO = OpenApiParameter(
    name="compromiso",
    type=OpenApiTypes.INT,
    description="Id del compromiso: muestra solo su historial de avances.",
)

PARAM_VIGENTES = OpenApiParameter(
    name="vigentes",
    type=OpenApiTypes.BOOL,
    description="true: excluye los avances anulados.",
)


@extend_schema(
    methods=["GET"],
    tags=[TAG],
    summary="Consultar historial de avances",
    description="Solo los compromisos de su ámbito (delegación).",
    parameters=[PARAM_COMPROMISO, PARAM_VIGENTES],
    responses={200: RegistroAvanceSerializer(many=True), 400: RESPUESTA_400, 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=[TAG],
    summary="Registrar avance (T2)",
    description=(
        "Transacción atómica: bloquea el compromiso, verifica el ámbito, "
        "exige asignación vigente y que el avance no retroceda, guarda la "
        "evidencia y los archivos, y actualiza el cumplimiento y el "
        "semáforo. Para adjuntar archivos use multipart/form-data con el "
        "campo `adjuntos` repetido."
    ),
    request={
        "application/json": AvanceCrearSerializer,
        "multipart/form-data": AvanceCrearSerializer,
    },
    responses={
        201: RegistroAvanceSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
    examples=[
        OpenApiExample(
            "Registrar 95 %",
            value={
                "compromiso": 1,
                "porcentaje_avance": 95,
                "evidencia": "Acta de recepción N.° 45 del 18-11-2026",
                "observacion": "Plataforma publicada en producción.",
            },
            request_only=True,
        ),
        OpenApiExample(
            "El avance retrocede (409)",
            value={
                "detail": "El avance no puede ser menor al cumplimiento actual (60%). ..."
            },
            response_only=True,
            status_codes=["409"],
        ),
    ],
)
@api_view(["GET", "POST"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def avance_lista(request):
    exigir_permiso(request, RegistroAvance)

    if request.method == "GET":
        avances = _avances_visibles(request.user)

        compromiso_id = request.query_params.get("compromiso")
        if compromiso_id:
            if not str(compromiso_id).isdigit():
                return Response(
                    {"compromiso": ["Debe ser un número entero."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            avances = avances.filter(compromiso_id=int(compromiso_id))

        if request.query_params.get("vigentes") == "true":
            avances = avances.filter(anulado=False)

        return Response(
            RegistroAvanceSerializer(avances, many=True, context={"request": request}).data
        )

    entrada = AvanceCrearSerializer(data=request.data)
    if not entrada.is_valid():
        return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

    # Mismas reglas de la web para porcentaje, evidencia y archivos.
    datos = request.data
    if not isinstance(datos, QueryDict):
        datos = {clave: valor for clave, valor in datos.items() if clave != "adjuntos"}

    formulario = RegistroAvanceForm(datos, request.FILES)
    if not formulario.is_valid():
        return Response(
            {campo: list(m) for campo, m in formulario.errors.items()},
            status=status.HTTP_400_BAD_REQUEST,
        )

    compromiso = obtener_o_404(
        Compromiso.objects.all(),
        entrada.validated_data["compromiso"],
        "Compromiso no encontrado.",
    )
    verificar_acceso_compromiso(request.user, compromiso)

    try:
        registro, _ = registrar_avance(
            request.user,
            compromiso.pk,
            formulario.cleaned_data["porcentaje_avance"],
            formulario.cleaned_data["evidencia"],
            formulario.cleaned_data.get("observacion", ""),
            formulario.cleaned_data["adjuntos"],
        )
    except ValidationError as error:
        return conflicto(_mensaje(error))

    return Response(_datos(request, registro), status=status.HTTP_201_CREATED)


@extend_schema(
    methods=["GET"],
    tags=[TAG],
    summary="Consultar avance",
    responses={200: RegistroAvanceSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=[TAG],
    summary="Corregir evidencia u observación del último avance",
    description=(
        "Solo el último avance vigente del compromiso. El porcentaje no se "
        "corrige: para cambiarlo, anule el avance (DELETE) y registre uno "
        "nuevo, así el historial muestra la corrección."
    ),
    request=AvanceCorregirSerializer,
    responses={
        200: RegistroAvanceSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
)
@extend_schema(
    methods=["DELETE"],
    tags=[TAG],
    summary="Anular el último avance (baja lógica)",
    description=(
        "El avance queda en el historial como anulado, con el motivo, y el "
        "cumplimiento del compromiso vuelve al avance vigente anterior (o "
        "0 %). El motivo se envía en el cuerpo JSON o en ?motivo=."
    ),
    request=AvanceAnularSerializer,
    parameters=[
        OpenApiParameter(
            name="motivo",
            type=OpenApiTypes.STR,
            description="Motivo de la anulación (alternativa al cuerpo JSON).",
        )
    ],
    responses={
        200: RegistroAvanceSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def avance_detalle(request, pk):
    exigir_permiso(request, RegistroAvance)
    avance = obtener_o_404(
        RegistroAvance.objects.select_related("compromiso"),
        pk,
        "Registro de avance no encontrado.",
    )
    verificar_acceso_compromiso(request.user, avance.compromiso)

    if request.method == "GET":
        return Response(_datos(request, avance))

    try:
        if request.method in ("PUT", "PATCH"):
            entrada = AvanceCorregirSerializer(
                data=request.data, partial=request.method == "PATCH"
            )
            if not entrada.is_valid():
                return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

            avance, _ = corregir_avance(
                request.user,
                avance.pk,
                evidencia=entrada.validated_data.get("evidencia"),
                observacion=entrada.validated_data.get("observacion"),
            )
        else:
            datos = {"motivo": request.data.get("motivo") or request.query_params.get("motivo")}
            entrada = AvanceAnularSerializer(data=datos)
            if not entrada.is_valid():
                return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

            avance, _ = anular_avance(
                request.user, avance.pk, entrada.validated_data["motivo"]
            )
    except ValidationError as error:
        return conflicto(_mensaje(error))

    return Response(_datos(request, avance))
