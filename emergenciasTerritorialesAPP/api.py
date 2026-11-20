from drf_spectacular.utils import OpenApiExample, extend_schema
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

from .ambito import filtrar_por_ambito, verificar_ambito
from .models import ContactoEmergencia, ZonaRiesgo
from .serializers import ContactoEmergenciaSerializer, ZonaRiesgoSerializer


# ============================================================
# API: EMERGENCIAS TERRITORIALES
# ============================================================
# Mismas reglas que la web: permisos del perfil, ámbito por delegación,
# validación con el formulario web y baja lógica. Los campos sensibles
# solo los recibe el Administrador (ver serializers.py).


def _guardar(request, serializer_class, instancia=None):
    """Crea (201) o modifica (200) verificando el ámbito de la delegación."""
    contexto = {"request": request}

    if instancia is None:
        serializer = serializer_class(data=request.data, context=contexto)
    else:
        serializer = serializer_class(
            instancia,
            data=request.data,
            partial=request.method == "PATCH",
            context=contexto,
        )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    delegacion = serializer.validated_data.get("delegacion")
    if delegacion is not None:
        verificar_ambito(request.user, delegacion.pk)

    serializer.save()
    codigo = status.HTTP_201_CREATED if instancia is None else status.HTTP_200_OK
    return Response(serializer.data, status=codigo)


# ============================================================
# MANTENEDOR 1: ZONAS DE RIESGO
# ============================================================

def _zona(request, pk):
    zona = obtener_o_404(ZonaRiesgo.objects.all(), pk, "Zona de riesgo no encontrada.")
    verificar_ambito(request.user, zona.delegacion_id)
    return zona


@extend_schema(
    methods=["GET"],
    tags=["Zonas de riesgo"],
    summary="Listar zonas de riesgo",
    description="Solo las de su delegación, salvo el Administrador.",
    parameters=[PARAM_ESTADO, PARAM_BUSQUEDA],
    responses={200: ZonaRiesgoSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Zonas de riesgo"],
    summary="Registrar zona de riesgo",
    request=ZonaRiesgoSerializer,
    responses={201: ZonaRiesgoSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403},
    examples=[
        OpenApiExample(
            "Nueva zona",
            value={
                "nombre": "Quebrada Peñuelas",
                "delegacion": 1,
                "nivel_peligro": "alto",
                "descripcion_riesgo": "Desborde en lluvias intensas.",
                "coordenadas_aprox": "-29.9440, -71.2680",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Respuesta para el perfil Usuario (sin coordenadas)",
            value={
                "id": 3,
                "nombre": "Quebrada Peñuelas",
                "delegacion": 1,
                "delegacion_nombre": "Delegación Centro",
                "nivel_peligro": "alto",
                "descripcion_riesgo": "Desborde en lluvias intensas.",
                "activo": True,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["GET", "POST"])
def zona_lista(request):
    exigir_permiso(request, ZonaRiesgo)

    if request.method == "POST":
        return _guardar(request, ZonaRiesgoSerializer)

    zonas = filtrar_por_ambito(
        request.user, ZonaRiesgo.objects.select_related("delegacion")
    )
    zonas = filtrar_por_estado(request, zonas)
    zonas = buscar(request, zonas, ["nombre", "descripcion_riesgo", "delegacion__nombre"])

    return Response(
        ZonaRiesgoSerializer(zonas, many=True, context={"request": request}).data
    )


@extend_schema(
    methods=["GET"],
    tags=["Zonas de riesgo"],
    summary="Consultar zona de riesgo",
    responses={200: ZonaRiesgoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Zonas de riesgo"],
    summary="Modificar zona de riesgo",
    request=ZonaRiesgoSerializer,
    responses={200: ZonaRiesgoSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Zonas de riesgo"],
    summary="Dar de baja zona de riesgo (baja lógica)",
    description=(
        "Queda con activo=false. Se rechaza (409) si tiene contactos "
        "asignados o reportes en curso."
    ),
    responses={200: ZonaRiesgoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def zona_detalle(request, pk):
    exigir_permiso(request, ZonaRiesgo)
    zona = _zona(request, pk)

    if request.method == "GET":
        return Response(ZonaRiesgoSerializer(zona, context={"request": request}).data)

    if request.method in ("PUT", "PATCH"):
        return _guardar(request, ZonaRiesgoSerializer, zona)

    if zona.activo:
        if not zona.puede_dar_de_baja():
            return conflicto(
                "No se puede dar de baja: la zona tiene contactos asignados "
                "o reportes en curso."
            )
        zona.activo = False
        zona.save(update_fields=["activo"])

    return Response(ZonaRiesgoSerializer(zona, context={"request": request}).data)


@extend_schema(
    tags=["Zonas de riesgo"],
    summary="Reactivar zona de riesgo",
    request=None,
    responses={200: ZonaRiesgoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def zona_reactivar(request, pk):
    exigir_permiso(request, ZonaRiesgo, "delete")
    zona = _zona(request, pk)

    if not zona.activo:
        if not zona.delegacion.activo:
            return conflicto("No se puede reactivar: la delegación está dada de baja.")

        if ZonaRiesgo.objects.filter(
            nombre__iexact=zona.nombre,
            delegacion_id=zona.delegacion_id,
            activo=True,
        ).exclude(pk=zona.pk).exists():
            return conflicto(
                "No se puede reactivar: ya existe otra zona activa con el "
                "mismo nombre en la delegación."
            )

        zona.activo = True
        zona.save(update_fields=["activo"])

    return Response(ZonaRiesgoSerializer(zona, context={"request": request}).data)


# ============================================================
# MANTENEDOR 2: CONTACTOS DE EMERGENCIA
# ============================================================

def _contacto(request, pk):
    contacto = obtener_o_404(
        ContactoEmergencia.objects.all(), pk, "Contacto de emergencia no encontrado."
    )
    verificar_ambito(request.user, contacto.delegacion_id)
    return contacto


@extend_schema(
    methods=["GET"],
    tags=["Contactos de emergencia"],
    summary="Listar contactos de emergencia",
    description=(
        "Solo los de su delegación, salvo el Administrador. Teléfono y "
        "correo solo se incluyen para el Administrador."
    ),
    parameters=[PARAM_ESTADO, PARAM_BUSQUEDA],
    responses={200: ContactoEmergenciaSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Contactos de emergencia"],
    summary="Registrar contacto de emergencia",
    request=ContactoEmergenciaSerializer,
    responses={201: ContactoEmergenciaSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403},
    examples=[
        OpenApiExample(
            "Nuevo contacto",
            value={
                "nombre": "Central de Bomberos",
                "cargo": "Unidad de Emergencia",
                "telefono": "132",
                "email": "central@bomberos.cl",
                "delegacion": 1,
                "zona_asignada": 3,
            },
            request_only=True,
        ),
        OpenApiExample(
            "Respuesta para el perfil Usuario (sin teléfono ni correo)",
            value={
                "id": 5,
                "nombre": "Central de Bomberos",
                "cargo": "Unidad de Emergencia",
                "delegacion": 1,
                "delegacion_nombre": "Delegación Centro",
                "zona_asignada": 3,
                "zona_nombre": "Quebrada Peñuelas",
                "activo": True,
            },
            response_only=True,
            status_codes=["200"],
        ),
    ],
)
@api_view(["GET", "POST"])
def contacto_lista(request):
    exigir_permiso(request, ContactoEmergencia)

    if request.method == "POST":
        return _guardar(request, ContactoEmergenciaSerializer)

    contactos = filtrar_por_ambito(
        request.user,
        ContactoEmergencia.objects.select_related("delegacion", "zona_asignada"),
    )
    contactos = filtrar_por_estado(request, contactos)
    contactos = buscar(request, contactos, ["nombre", "cargo", "delegacion__nombre"])

    return Response(
        ContactoEmergenciaSerializer(
            contactos, many=True, context={"request": request}
        ).data
    )


@extend_schema(
    methods=["GET"],
    tags=["Contactos de emergencia"],
    summary="Consultar contacto de emergencia",
    responses={200: ContactoEmergenciaSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Contactos de emergencia"],
    summary="Modificar contacto de emergencia",
    request=ContactoEmergenciaSerializer,
    responses={200: ContactoEmergenciaSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Contactos de emergencia"],
    summary="Dar de baja contacto de emergencia (baja lógica)",
    description="Queda con activo=false. Se rechaza (409) si tiene reportes derivados en curso.",
    responses={200: ContactoEmergenciaSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def contacto_detalle(request, pk):
    exigir_permiso(request, ContactoEmergencia)
    contacto = _contacto(request, pk)

    if request.method == "GET":
        return Response(
            ContactoEmergenciaSerializer(contacto, context={"request": request}).data
        )

    if request.method in ("PUT", "PATCH"):
        return _guardar(request, ContactoEmergenciaSerializer, contacto)

    if contacto.activo:
        if not contacto.puede_dar_de_baja():
            return conflicto(
                "No se puede dar de baja: el contacto tiene reportes "
                "derivados en curso."
            )
        contacto.activo = False
        contacto.save(update_fields=["activo"])

    return Response(
        ContactoEmergenciaSerializer(contacto, context={"request": request}).data
    )


@extend_schema(
    tags=["Contactos de emergencia"],
    summary="Reactivar contacto de emergencia",
    request=None,
    responses={200: ContactoEmergenciaSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def contacto_reactivar(request, pk):
    exigir_permiso(request, ContactoEmergencia, "delete")
    contacto = _contacto(request, pk)

    if not contacto.activo:
        if not contacto.delegacion.activo:
            return conflicto("No se puede reactivar: la delegación está dada de baja.")

        contacto.activo = True
        contacto.save(update_fields=["activo"])

    return Response(
        ContactoEmergenciaSerializer(contacto, context={"request": request}).data
    )
