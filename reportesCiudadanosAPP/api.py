from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apiAPP.permisos import exigir_permiso, obtener_o_404
from apiAPP.views import (
    PARAM_BUSQUEDA,
    PARAM_ESTADO,
    RESPUESTA_400,
    RESPUESTA_403,
    RESPUESTA_404,
    RESPUESTA_409,
    buscar,
    conflicto,
    filtrar_por_estado,
)
from emergenciasTerritorialesAPP.ambito import filtrar_por_ambito, verificar_ambito

from .models import DerivacionReporte, ReporteCiudadano
from .serializers import (
    DerivacionCrearSerializer,
    DerivacionModificarSerializer,
    DerivacionSerializer,
    ReporteCiudadanoSerializer,
)
from .transaccion import (
    ReglaNegocioError,
    anular_derivacion,
    derivar_reporte,
    modificar_derivacion,
    resolver_reporte,
)


# ============================================================
# API: REPORTES CIUDADANOS Y TRANSACCIÓN DE DERIVACIÓN
# ============================================================
# La transacción usa las mismas funciones que la web
# (reportesCiudadanosAPP/transaccion.py). Respuestas:
#   400 datos inválidos · 403 sin permiso o fuera de ámbito
#   404 no existe       · 409 una regla del negocio lo impide


def _reporte(request, pk):
    reporte = obtener_o_404(
        ReporteCiudadano.objects.select_related("delegacion", "zona", "contacto"),
        pk,
        "Reporte ciudadano no encontrado.",
    )
    verificar_ambito(request.user, reporte.delegacion_id)
    return reporte


def _datos_reporte(request, reporte):
    return ReporteCiudadanoSerializer(reporte, context={"request": request}).data


def _datos_derivacion(request, derivacion):
    return DerivacionSerializer(derivacion, context={"request": request}).data


# ============================================================
# REPORTES CIUDADANOS
# ============================================================

PARAM_SITUACION = OpenApiParameter(
    name="situacion",
    type=OpenApiTypes.STR,
    enum=["pendiente", "derivado", "resuelto"],
    description="Filtra por la situación del reporte.",
)


@extend_schema(
    methods=["GET"],
    tags=["Reportes ciudadanos"],
    summary="Listar reportes ciudadanos",
    description=(
        "Solo los de su delegación, salvo el Administrador. Los datos del "
        "vecino solo se incluyen para el Administrador."
    ),
    parameters=[PARAM_ESTADO, PARAM_BUSQUEDA, PARAM_SITUACION],
    responses={200: ReporteCiudadanoSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Reportes ciudadanos"],
    summary="Registrar reporte ciudadano",
    description="El reporte queda pendiente hasta que se derive.",
    request=ReporteCiudadanoSerializer,
    responses={201: ReporteCiudadanoSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403},
    examples=[
        OpenApiExample(
            "Nuevo reporte",
            value={
                "delegacion": 1,
                "tipo": "alumbrado",
                "prioridad": "alta",
                "descripcion": "Tres luminarias apagadas frente a la plaza.",
                "ubicacion": "Av. Francisco de Aguirre 300",
                "nombre_vecino": "Juan Soto",
                "telefono_vecino": "+56 9 8765 4321",
                "email_vecino": "juan.soto@correo.cl",
            },
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def reporte_lista(request):
    exigir_permiso(request, ReporteCiudadano)

    if request.method == "POST":
        serializer = ReporteCiudadanoSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        verificar_ambito(request.user, serializer.validated_data["delegacion"].pk)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    reportes = filtrar_por_ambito(
        request.user,
        ReporteCiudadano.objects.select_related("delegacion", "zona", "contacto"),
    )
    reportes = filtrar_por_estado(request, reportes)
    reportes = buscar(request, reportes, ["descripcion", "ubicacion", "delegacion__nombre"])

    situacion = request.query_params.get("situacion")
    if situacion in dict(ReporteCiudadano.ESTADO):
        reportes = reportes.filter(estado=situacion)

    return Response(
        ReporteCiudadanoSerializer(reportes, many=True, context={"request": request}).data
    )


@extend_schema(
    methods=["GET"],
    tags=["Reportes ciudadanos"],
    summary="Consultar reporte ciudadano",
    responses={200: ReporteCiudadanoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Reportes ciudadanos"],
    summary="Modificar datos del reporte",
    description=(
        "Modifica los datos informados por el vecino. El estado, la zona y "
        "el contacto solo cambian por la transacción de derivación. Un "
        "reporte resuelto no se modifica (409)."
    ),
    request=ReporteCiudadanoSerializer,
    responses={
        200: ReporteCiudadanoSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
)
@extend_schema(
    methods=["DELETE"],
    tags=["Reportes ciudadanos"],
    summary="Dar de baja reporte (baja lógica)",
    description="Queda con activo=false. Un reporte derivado en curso no se da de baja (409).",
    responses={200: ReporteCiudadanoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def reporte_detalle(request, pk):
    exigir_permiso(request, ReporteCiudadano)
    reporte = _reporte(request, pk)

    if request.method == "GET":
        return Response(_datos_reporte(request, reporte))

    if request.method in ("PUT", "PATCH"):
        if reporte.esta_resuelto:
            return conflicto("El reporte ya está resuelto: no se puede modificar.")

        serializer = ReporteCiudadanoSerializer(
            reporte,
            data=request.data,
            partial=request.method == "PATCH",
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        delegacion = serializer.validated_data.get("delegacion")
        if delegacion is not None:
            verificar_ambito(request.user, delegacion.pk)
            if delegacion.pk != reporte.delegacion_id and reporte.estado != "pendiente":
                return conflicto(
                    "Un reporte ya derivado no puede cambiar de delegación."
                )

        serializer.save()
        return Response(serializer.data)

    if reporte.activo:
        if reporte.estado == "derivado":
            return conflicto(
                "No se puede dar de baja un reporte derivado en curso. Anule "
                "la derivación o resuelva el reporte primero."
            )
        reporte.activo = False
        reporte.save(update_fields=["activo"])

    return Response(_datos_reporte(request, reporte))


@extend_schema(
    tags=["Reportes ciudadanos"],
    summary="Reactivar reporte",
    request=None,
    responses={200: ReporteCiudadanoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def reporte_reactivar(request, pk):
    exigir_permiso(request, ReporteCiudadano, "delete")
    reporte = _reporte(request, pk)

    if not reporte.activo:
        if not reporte.delegacion.activo:
            return conflicto("No se puede reactivar: la delegación está dada de baja.")
        reporte.activo = True
        reporte.save(update_fields=["activo"])

    return Response(_datos_reporte(request, reporte))


@extend_schema(
    tags=["Derivaciones (transacción)"],
    summary="Resolver reporte",
    description="Cierra un reporte derivado y registra la fecha de resolución.",
    request=None,
    responses={200: ReporteCiudadanoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def reporte_resolver(request, pk):
    exigir_permiso(request, DerivacionReporte, "change")
    reporte = _reporte(request, pk)

    try:
        reporte = resolver_reporte(request.user, reporte.pk)
    except ReglaNegocioError as error:
        return conflicto(str(error))

    return Response(_datos_reporte(request, reporte))


# ============================================================
# TRANSACCIÓN: DERIVACIONES
# ============================================================

PARAM_REPORTE = OpenApiParameter(
    name="reporte",
    type=OpenApiTypes.INT,
    description="Id del reporte: muestra solo su historial.",
)

PARAM_VIGENTES = OpenApiParameter(
    name="vigentes",
    type=OpenApiTypes.BOOL,
    description="true: solo las derivaciones vigentes.",
)


@extend_schema(
    methods=["GET"],
    tags=["Derivaciones (transacción)"],
    summary="Consultar historial de derivaciones",
    parameters=[PARAM_REPORTE, PARAM_VIGENTES],
    responses={200: DerivacionSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Derivaciones (transacción)"],
    summary="Derivar reporte (registrar)",
    description=(
        "Transacción atómica: bloquea el reporte, valida que la zona y el "
        "contacto estén activos y sean de la delegación del reporte, deja "
        "la derivación anterior como historial y marca el reporte como "
        "derivado. Si una regla lo impide responde 409 y no guarda nada."
    ),
    request=DerivacionCrearSerializer,
    responses={
        201: DerivacionSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        409: RESPUESTA_409,
    },
    examples=[
        OpenApiExample(
            "Derivar a zona y contacto",
            value={
                "reporte": 7,
                "zona": 3,
                "contacto": 5,
                "observacion": "Revisar luminarias antes del fin de semana.",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Regla de negocio (409)",
            value={"detail": "La zona de riesgo no pertenece a la delegación del reporte."},
            response_only=True,
            status_codes=["409"],
        ),
    ],
)
@api_view(["GET", "POST"])
def derivacion_lista(request):
    exigir_permiso(request, DerivacionReporte)

    if request.method == "POST":
        entrada = DerivacionCrearSerializer(data=request.data)
        if not entrada.is_valid():
            return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

        datos = entrada.validated_data
        verificar_ambito(request.user, datos["reporte"].delegacion_id)

        try:
            derivacion = derivar_reporte(
                request.user,
                datos["reporte"].pk,
                datos["zona"].pk,
                datos["contacto"].pk,
                datos.get("observacion", ""),
            )
        except ReglaNegocioError as error:
            return conflicto(str(error))

        return Response(
            _datos_derivacion(request, derivacion), status=status.HTTP_201_CREATED
        )

    derivaciones = filtrar_por_ambito(
        request.user,
        DerivacionReporte.objects.select_related(
            "reporte", "zona", "contacto", "usuario"
        ),
        campo="reporte__delegacion_id",
    )

    reporte_id = request.query_params.get("reporte")
    if reporte_id:
        if not str(reporte_id).isdigit():
            return Response(
                {"reporte": ["Debe ser un número entero."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        derivaciones = derivaciones.filter(reporte_id=int(reporte_id))

    if request.query_params.get("vigentes") == "true":
        derivaciones = derivaciones.filter(activo=True)

    return Response(
        DerivacionSerializer(derivaciones, many=True, context={"request": request}).data
    )


@extend_schema(
    methods=["GET"],
    tags=["Derivaciones (transacción)"],
    summary="Consultar derivación",
    responses={200: DerivacionSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Derivaciones (transacción)"],
    summary="Modificar derivación vigente",
    description=(
        "Corrige zona, contacto u observación de la derivación vigente. "
        "Una derivación histórica o de un reporte resuelto no se modifica (409)."
    ),
    request=DerivacionModificarSerializer,
    responses={
        200: DerivacionSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
        404: RESPUESTA_404,
        409: RESPUESTA_409,
    },
)
@extend_schema(
    methods=["DELETE"],
    tags=["Derivaciones (transacción)"],
    summary="Anular derivación vigente (baja lógica)",
    description=(
        "La derivación queda en el historial como anulada y el reporte "
        "vuelve a quedar pendiente, sin zona ni contacto."
    ),
    responses={200: DerivacionSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def derivacion_detalle(request, pk):
    exigir_permiso(request, DerivacionReporte)
    derivacion = obtener_o_404(
        DerivacionReporte.objects.select_related("reporte", "zona", "contacto", "usuario"),
        pk,
        "Derivación no encontrada.",
    )
    verificar_ambito(request.user, derivacion.reporte.delegacion_id)

    if request.method == "GET":
        return Response(_datos_derivacion(request, derivacion))

    try:
        if request.method in ("PUT", "PATCH"):
            entrada = DerivacionModificarSerializer(
                data=request.data, partial=request.method == "PATCH"
            )
            if not entrada.is_valid():
                return Response(entrada.errors, status=status.HTTP_400_BAD_REQUEST)

            datos = entrada.validated_data
            derivacion = modificar_derivacion(
                request.user,
                derivacion.pk,
                zona_id=datos["zona"].pk if "zona" in datos else None,
                contacto_id=datos["contacto"].pk if "contacto" in datos else None,
                observacion=datos.get("observacion"),
            )
        else:
            derivacion = anular_derivacion(request.user, derivacion.pk)
    except ReglaNegocioError as error:
        return conflicto(str(error))

    derivacion.refresh_from_db()
    return Response(_datos_derivacion(request, derivacion))
