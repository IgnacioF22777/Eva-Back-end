from django.core.cache import cache
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from delegacionesAPP.models import Delegacion, Servicio
from seguridadAPP.perfiles import perfil_de
from seguridadAPP.views import (
    MAX_INTENTOS_LOGIN,
    MINUTOS_BLOQUEO,
    clave_intentos,
)
from sgr_maestrosAPP.models import CatalogoActividad, Periodo
from sgr_maestrosAPP.models import Meta as MetaModelo
from tubo_gestionAPP.ambito import (
    compromisos_visibles,
    verificar_acceso_compromiso,
)
from tubo_gestionAPP.models import Compromiso

from .permisos import exigir_permiso, obtener_o_404
from .serializers import (
    CatalogoActividadSerializer,
    CompromisoSerializer,
    DelegacionSerializer,
    MetaSerializer,
    PeriodoSerializer,
    ServicioSerializer,
)


# ============================================================
# DOCUMENTACIÓN COMÚN (SWAGGER)
# ============================================================

PARAM_ESTADO = OpenApiParameter(
    name="estado",
    type=OpenApiTypes.STR,
    enum=["activos", "inactivos", "todos"],
    default="activos",
    description="Filtra por estado de baja lógica.",
)

PARAM_BUSQUEDA = OpenApiParameter(
    name="q",
    type=OpenApiTypes.STR,
    description="Texto a buscar (no distingue mayúsculas).",
)

RESPUESTA_400 = OpenApiResponse(
    description="Datos inválidos: el detalle indica el error por campo."
)
RESPUESTA_403 = OpenApiResponse(
    description="Su perfil no tiene permiso o el registro está fuera de su ámbito."
)
RESPUESTA_404 = OpenApiResponse(description="El registro no existe.")
RESPUESTA_409 = OpenApiResponse(
    description="La operación no se permite por una regla de negocio."
)


def conflicto(mensaje):
    """409: la solicitud es válida, pero una regla de negocio la impide."""
    return Response({"detail": mensaje}, status=status.HTTP_409_CONFLICT)


def filtrar_por_estado(request, queryset):
    estado = request.query_params.get("estado", "activos")

    if estado == "todos":
        return queryset
    if estado == "inactivos":
        return queryset.filter(activo=False)
    return queryset.filter(activo=True)


def buscar(request, queryset, campos):
    texto = (request.query_params.get("q") or "").strip()

    if not texto:
        return queryset

    condicion = Q()
    for campo in campos:
        condicion |= Q(**{f"{campo}__icontains": texto})

    return queryset.filter(condicion)


def actualizar(request, serializer_class, instancia):
    """PUT reemplaza todos los campos editables; PATCH solo los enviados."""
    serializer = serializer_class(
        instancia,
        data=request.data,
        partial=request.method == "PATCH",
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# AUTENTICACIÓN JWT
# ============================================================

class ObtenerTokenView(TokenObtainPairView):
    """
    Entrega el par de tokens JWT (access y refresh).

    Usa el mismo inicio de sesión que la web: RUT (con o sin puntos),
    correo o nombre de usuario, y comparte su bloqueo de 15 minutos tras
    5 intentos fallidos, para que la API no permita ataques de fuerza
    bruta que la web sí bloquea.
    """

    @extend_schema(
        tags=["Autenticación"],
        summary="Obtener token JWT",
        description=(
            "Ingrese su RUT (o correo) y su contraseña. Copie el token "
            "`access` y péguelo en **Authorize**. Tras 5 intentos "
            "fallidos el identificador queda bloqueado 15 minutos (429)."
        ),
        examples=[
            OpenApiExample(
                "Ingreso con RUT",
                value={"username": "12.345.678-5", "password": "su_clave"},
                request_only=True,
            ),
        ],
        responses={
            200: OpenApiResponse(description="Tokens access y refresh."),
            401: OpenApiResponse(description="Credenciales inválidas."),
            429: OpenApiResponse(description="Demasiados intentos fallidos."),
        },
    )
    def post(self, request, *args, **kwargs):
        datos = request.data if hasattr(request.data, "get") else {}
        clave = clave_intentos(str(datos.get("username") or ""))

        if cache.get(clave, 0) >= MAX_INTENTOS_LOGIN:
            return Response(
                {
                    "detail": (
                        "Demasiados intentos fallidos. Intente "
                        f"nuevamente en {MINUTOS_BLOQUEO} minutos."
                    )
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            respuesta = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            cache.set(clave, cache.get(clave, 0) + 1, MINUTOS_BLOQUEO * 60)
            raise

        cache.delete(clave)
        return respuesta


@extend_schema(
    tags=["Autenticación"],
    summary="Renovar token de acceso",
    description=(
        "Envíe el token `refresh` para obtener un nuevo `access` sin volver "
        "a ingresar la contraseña."
    ),
)
class RenovarTokenView(TokenRefreshView):
    pass


@extend_schema(
    tags=["Autenticación"],
    summary="Usuario autenticado",
    description="Datos y perfil del usuario dueño del token.",
    responses=inline_serializer(
        name="UsuarioActual",
        fields={
            "id": serializers.IntegerField(),
            "username": serializers.CharField(),
            "nombre": serializers.CharField(),
            "email": serializers.EmailField(),
            "rut": serializers.CharField(allow_null=True),
            "perfil": serializers.CharField(allow_null=True),
            "delegacion": serializers.CharField(allow_null=True),
            "cargo": serializers.CharField(allow_null=True),
        },
    ),
)
@api_view(["GET"])
def usuario_actual(request):
    usuario = request.user
    perfil = getattr(usuario, "perfil", None)

    return Response({
        "id": usuario.pk,
        "username": usuario.username,
        "nombre": usuario.get_full_name(),
        "email": usuario.email,
        "rut": perfil.rut_formateado if perfil else None,
        "perfil": perfil_de(usuario),
        "delegacion": (
            perfil.delegacion.nombre if perfil and perfil.delegacion else None
        ),
        "cargo": perfil.cargo.nombre if perfil and perfil.cargo else None,
    })


# ============================================================
# DELEGACIONES
# ============================================================

@extend_schema(
    methods=["GET"],
    tags=["Delegaciones"],
    summary="Listar delegaciones",
    parameters=[PARAM_ESTADO, PARAM_BUSQUEDA],
    responses={200: DelegacionSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Delegaciones"],
    summary="Registrar delegación",
    description=(
        "Crea una delegación. Si existe una delegación dada de baja con el "
        "mismo nombre, se reactiva con los nuevos datos (200) en lugar de "
        "duplicarla."
    ),
    request=DelegacionSerializer,
    responses={
        201: DelegacionSerializer,
        200: DelegacionSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
    },
    examples=[
        OpenApiExample(
            "Nueva delegación",
            value={
                "nombre": "Delegación Las Compañías",
                "direccion": "Av. Las Compañías 1234",
                "encargado": "María Pérez",
                "email": "companias@laserena.cl",
                "telefono": "51 2 000 000",
                "celular": "+56 9 1234 5678",
            },
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def delegacion_lista(request):
    exigir_permiso(request, Delegacion)

    if request.method == "GET":
        delegaciones = filtrar_por_estado(request, Delegacion.objects.all())
        delegaciones = buscar(
            request,
            delegaciones,
            ["nombre", "encargado", "email", "direccion"],
        )
        serializer = DelegacionSerializer(delegaciones, many=True)
        return Response(serializer.data)

    serializer = DelegacionSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Misma regla que la web: un nombre de una delegación inactiva la
    # reactiva en lugar de crear un duplicado.
    inactiva = Delegacion.objects.filter(
        nombre__iexact=serializer.validated_data["nombre"],
        activo=False,
    ).first()

    if inactiva:
        serializer.instance = inactiva
        serializer.save(activo=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    methods=["GET"],
    tags=["Delegaciones"],
    summary="Consultar delegación",
    responses={200: DelegacionSerializer, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Delegaciones"],
    summary="Modificar delegación",
    request=DelegacionSerializer,
    responses={200: DelegacionSerializer, 400: RESPUESTA_400, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Delegaciones"],
    summary="Dar de baja delegación (baja lógica)",
    description=(
        "No se elimina: queda con activo=false. Se rechaza (409) si tiene "
        "servicios o compromisos activos."
    ),
    responses={200: DelegacionSerializer, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def delegacion_detalle(request, pk):
    delegacion = obtener_o_404(
        Delegacion.objects.all(), pk, "Delegación no encontrada."
    )

    if request.method == "GET":
        exigir_permiso(request, Delegacion)
        return Response(DelegacionSerializer(delegacion).data)

    if request.method in ("PUT", "PATCH"):
        exigir_permiso(request, Delegacion)
        return actualizar(request, DelegacionSerializer, delegacion)

    exigir_permiso(request, Delegacion, "delete")

    if delegacion.activo:
        if not delegacion.puede_dar_de_baja():
            return conflicto(
                "No se puede dar de baja: la delegación tiene servicios o "
                "compromisos activos. Desactívelos primero."
            )

        delegacion.activo = False
        delegacion.save(update_fields=["activo"])

    return Response(DelegacionSerializer(delegacion).data)


@extend_schema(
    tags=["Delegaciones"],
    summary="Reactivar delegación",
    request=None,
    responses={200: DelegacionSerializer, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def delegacion_reactivar(request, pk):
    exigir_permiso(request, Delegacion, "delete")
    delegacion = obtener_o_404(
        Delegacion.objects.all(), pk, "Delegación no encontrada."
    )

    if not delegacion.activo:
        if Delegacion.objects.filter(
            nombre__iexact=delegacion.nombre,
            activo=True,
        ).exclude(pk=delegacion.pk).exists():
            return conflicto(
                "No se puede reactivar: ya existe otra delegación activa "
                "con el mismo nombre."
            )

        delegacion.activo = True
        delegacion.save(update_fields=["activo"])

    return Response(DelegacionSerializer(delegacion).data)


# ============================================================
# SERVICIOS
# ============================================================

@extend_schema(
    methods=["GET"],
    tags=["Servicios"],
    summary="Listar servicios",
    parameters=[
        PARAM_ESTADO,
        PARAM_BUSQUEDA,
        OpenApiParameter(
            name="delegacion",
            type=OpenApiTypes.INT,
            description="Id de la delegación para ver solo sus servicios.",
        ),
    ],
    responses={200: ServicioSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Servicios"],
    summary="Registrar servicio",
    description=(
        "Crea un servicio en una delegación activa. Si existe un servicio "
        "dado de baja con el mismo nombre en esa delegación, se reactiva "
        "(200)."
    ),
    request=ServicioSerializer,
    responses={
        201: ServicioSerializer,
        200: ServicioSerializer,
        400: RESPUESTA_400,
        403: RESPUESTA_403,
    },
    examples=[
        OpenApiExample(
            "Nuevo servicio",
            value={"delegacion": 1, "nombre": "Retiro de escombros"},
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def servicio_lista(request):
    exigir_permiso(request, Servicio)

    if request.method == "GET":
        servicios = Servicio.objects.select_related("delegacion")
        servicios = filtrar_por_estado(request, servicios)
        servicios = buscar(request, servicios, ["nombre", "delegacion__nombre"])

        delegacion_id = request.query_params.get("delegacion", "")
        if delegacion_id.isdigit():
            servicios = servicios.filter(delegacion_id=int(delegacion_id))

        return Response(ServicioSerializer(servicios, many=True).data)

    serializer = ServicioSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    inactivo = Servicio.objects.filter(
        delegacion=serializer.validated_data["delegacion"],
        nombre__iexact=serializer.validated_data["nombre"],
        activo=False,
    ).first()

    if inactivo:
        serializer.instance = inactivo
        serializer.save(activo=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    methods=["GET"],
    tags=["Servicios"],
    summary="Consultar servicio",
    responses={200: ServicioSerializer, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Servicios"],
    summary="Modificar servicio",
    request=ServicioSerializer,
    responses={200: ServicioSerializer, 400: RESPUESTA_400, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Servicios"],
    summary="Dar de baja servicio (baja lógica)",
    description="Se rechaza (409) si tiene compromisos activos asignados.",
    responses={200: ServicioSerializer, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def servicio_detalle(request, pk):
    servicio = obtener_o_404(
        Servicio.objects.select_related("delegacion"),
        pk,
        "Servicio no encontrado.",
    )
    exigir_permiso(request, Servicio)

    if request.method == "GET":
        return Response(ServicioSerializer(servicio).data)

    if request.method in ("PUT", "PATCH"):
        return actualizar(request, ServicioSerializer, servicio)

    if servicio.activo:
        if servicio.compromisos.filter(activo=True).exists():
            return conflicto(
                "No se puede dar de baja: el servicio tiene compromisos "
                "activos asignados. Reasígnelos o desactívelos primero."
            )

        servicio.activo = False
        servicio.save(update_fields=["activo"])

    return Response(ServicioSerializer(servicio).data)


@extend_schema(
    tags=["Servicios"],
    summary="Reactivar servicio",
    request=None,
    responses={200: ServicioSerializer, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def servicio_reactivar(request, pk):
    exigir_permiso(request, Servicio, "delete")
    servicio = obtener_o_404(
        Servicio.objects.select_related("delegacion"),
        pk,
        "Servicio no encontrado.",
    )

    if not servicio.activo:
        if not servicio.delegacion.activo:
            return conflicto(
                "No se puede reactivar el servicio porque su delegación "
                "está dada de baja."
            )

        servicio.activo = True
        servicio.save(update_fields=["activo"])

    return Response(ServicioSerializer(servicio).data)


# ============================================================
# COMPROMISOS (respetan el ámbito por delegación)
# ============================================================

def obtener_compromiso(request, pk):
    compromiso = obtener_o_404(
        Compromiso.objects.select_related("delegacion", "servicio"),
        pk,
        "Compromiso no encontrado.",
    )
    verificar_acceso_compromiso(request.user, compromiso)
    return compromiso


@extend_schema(
    methods=["GET"],
    tags=["Compromisos"],
    summary="Listar compromisos",
    description=(
        "Administrador: todos. Supervisor: los de su delegación y los sin "
        "asignar. Administrativo: solo los de su delegación."
    ),
    parameters=[
        PARAM_ESTADO,
        PARAM_BUSQUEDA,
        OpenApiParameter(
            name="semaforo",
            type=OpenApiTypes.STR,
            enum=["verde", "amarillo", "rojo"],
            description="Filtra por color del semáforo.",
        ),
    ],
    responses={200: CompromisoSerializer(many=True), 403: RESPUESTA_403},
)
@extend_schema(
    methods=["POST"],
    tags=["Compromisos"],
    summary="Registrar compromiso",
    description=(
        "Solo se indica la tarea. Comienza en 0% (rojo) y sin asignar: la "
        "asignación y el avance se hacen con las transacciones T1 y T2."
    ),
    request=CompromisoSerializer,
    responses={201: CompromisoSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403},
    examples=[
        OpenApiExample(
            "Nuevo compromiso",
            value={"tarea": "Reparar luminarias de la plaza"},
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def compromiso_lista(request):
    exigir_permiso(request, Compromiso)

    if request.method == "GET":
        compromisos = compromisos_visibles(
            request.user,
            Compromiso.objects.select_related("delegacion", "servicio"),
        )
        compromisos = filtrar_por_estado(request, compromisos)
        compromisos = buscar(
            request,
            compromisos,
            ["tarea", "delegacion__nombre"],
        )

        semaforo = request.query_params.get("semaforo", "")
        if semaforo in dict(Compromiso.ESTADOS):
            compromisos = compromisos.filter(estado=semaforo)

        return Response(CompromisoSerializer(compromisos, many=True).data)

    serializer = CompromisoSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Compromisos"],
    summary="Consultar compromiso",
    responses={200: CompromisoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Compromisos"],
    summary="Modificar la tarea del compromiso",
    request=CompromisoSerializer,
    responses={200: CompromisoSerializer, 400: RESPUESTA_400, 403: RESPUESTA_403},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Compromisos"],
    summary="Dar de baja compromiso (baja lógica)",
    responses={200: CompromisoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def compromiso_detalle(request, pk):
    exigir_permiso(request, Compromiso)
    compromiso = obtener_compromiso(request, pk)

    if request.method == "GET":
        return Response(CompromisoSerializer(compromiso).data)

    if request.method in ("PUT", "PATCH"):
        return actualizar(request, CompromisoSerializer, compromiso)

    if compromiso.activo:
        compromiso.activo = False
        compromiso.save(update_fields=["activo"])

    return Response(CompromisoSerializer(compromiso).data)


@extend_schema(
    tags=["Compromisos"],
    summary="Reactivar compromiso",
    request=None,
    responses={200: CompromisoSerializer, 403: RESPUESTA_403, 404: RESPUESTA_404},
)
@api_view(["POST"])
def compromiso_reactivar(request, pk):
    exigir_permiso(request, Compromiso, "delete")
    compromiso = obtener_compromiso(request, pk)

    if not compromiso.activo:
        compromiso.activo = True
        compromiso.save(update_fields=["activo"])

    return Response(CompromisoSerializer(compromiso).data)


# ============================================================
# CATÁLOGO DE ACTIVIDADES
# ============================================================
# Igual que en la web, dar de baja o reactivar una actividad usa el
# permiso de modificación (change), no el de eliminación.

@extend_schema(
    methods=["GET"],
    tags=["Catálogo de actividades"],
    summary="Listar actividades",
    parameters=[
        PARAM_ESTADO,
        PARAM_BUSQUEDA,
        OpenApiParameter(
            name="tipo",
            type=OpenApiTypes.STR,
            enum=["EJECUCION", "PREPARATORIA"],
            description="Filtra por tipo de gestión (R5).",
        ),
    ],
    responses={200: CatalogoActividadSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    tags=["Catálogo de actividades"],
    summary="Registrar actividad",
    description=(
        "El código debe ser único. Sin tipo de gestión, la actividad queda "
        "como EJECUCION (suma puntaje)."
    ),
    request=CatalogoActividadSerializer,
    responses={201: CatalogoActividadSerializer, 400: RESPUESTA_400},
    examples=[
        OpenApiExample(
            "Actividad preparatoria",
            value={
                "codigo": "COORD-TALLER",
                "nombre": "Coordinación de taller",
                "descripcion": "Correos e invitaciones para un taller.",
                "area": "Organizaciones comunitarias",
                "tipo_gestion": "PREPARATORIA",
            },
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def catalogo_lista(request):
    exigir_permiso(request, CatalogoActividad)

    if request.method == "GET":
        actividades = filtrar_por_estado(request, CatalogoActividad.objects.all())
        actividades = buscar(
            request,
            actividades,
            ["codigo", "nombre", "area", "descripcion"],
        )

        tipo = request.query_params.get("tipo", "")
        if tipo in dict(CatalogoActividad.TIPO_GESTION_OPCIONES):
            actividades = actividades.filter(tipo_gestion=tipo)

        return Response(CatalogoActividadSerializer(actividades, many=True).data)

    serializer = CatalogoActividadSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Catálogo de actividades"],
    summary="Consultar actividad",
    responses={200: CatalogoActividadSerializer, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Catálogo de actividades"],
    summary="Modificar actividad",
    request=CatalogoActividadSerializer,
    responses={200: CatalogoActividadSerializer, 400: RESPUESTA_400},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Catálogo de actividades"],
    summary="Dar de baja actividad (baja lógica)",
    description="Se rechaza (409) si la actividad tiene metas activas.",
    responses={200: CatalogoActividadSerializer, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def catalogo_detalle(request, pk):
    actividad = obtener_o_404(
        CatalogoActividad.objects.all(), pk, "Actividad no encontrada."
    )

    if request.method == "GET":
        exigir_permiso(request, CatalogoActividad)
        return Response(CatalogoActividadSerializer(actividad).data)

    exigir_permiso(request, CatalogoActividad, "change")

    if request.method in ("PUT", "PATCH"):
        return actualizar(request, CatalogoActividadSerializer, actividad)

    if actividad.activo:
        if actividad.metas.filter(activo=True).exists():
            return conflicto(
                "No se puede dar de baja: la actividad tiene metas activas. "
                "Dé de baja o reasigne esas metas primero."
            )

        actividad.activo = False
        actividad.save(update_fields=["activo"])

    return Response(CatalogoActividadSerializer(actividad).data)


@extend_schema(
    tags=["Catálogo de actividades"],
    summary="Reactivar actividad",
    request=None,
    responses={200: CatalogoActividadSerializer, 404: RESPUESTA_404},
)
@api_view(["POST"])
def catalogo_reactivar(request, pk):
    exigir_permiso(request, CatalogoActividad, "change")
    actividad = obtener_o_404(
        CatalogoActividad.objects.all(), pk, "Actividad no encontrada."
    )

    if not actividad.activo:
        actividad.activo = True
        actividad.save(update_fields=["activo"])

    return Response(CatalogoActividadSerializer(actividad).data)


# ============================================================
# PERÍODOS DE MEDICIÓN
# ============================================================

@extend_schema(
    methods=["GET"],
    tags=["Períodos"],
    summary="Listar períodos",
    parameters=[
        PARAM_BUSQUEDA,
        OpenApiParameter(
            name="estado",
            type=OpenApiTypes.STR,
            enum=["abiertos", "cerrados", "todos"],
            default="todos",
            description="Filtra por períodos abiertos o cerrados.",
        ),
    ],
    responses={200: PeriodoSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    tags=["Períodos"],
    summary="Registrar período",
    request=PeriodoSerializer,
    responses={201: PeriodoSerializer, 400: RESPUESTA_400},
    examples=[
        OpenApiExample(
            "Tercer trimestre 2026",
            value={
                "codigo": "2026-T3",
                "nombre": "Tercer trimestre 2026",
                "fecha_inicio": "2026-07-01",
                "fecha_fin": "2026-09-30",
                "cerrado": False,
            },
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def periodo_lista(request):
    exigir_permiso(request, Periodo)

    if request.method == "GET":
        periodos = buscar(request, Periodo.objects.all(), ["codigo", "nombre"])

        estado = request.query_params.get("estado", "todos")
        if estado == "abiertos":
            periodos = periodos.filter(cerrado=False)
        elif estado == "cerrados":
            periodos = periodos.filter(cerrado=True)

        return Response(PeriodoSerializer(periodos, many=True).data)

    serializer = PeriodoSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Períodos"],
    summary="Consultar período",
    responses={200: PeriodoSerializer, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Períodos"],
    summary="Modificar o cerrar período",
    description=(
        "Para cerrarlo envíe cerrado=true: se acepta solo si las metas "
        "activas de cada cargo suman 100%. Un período cerrado no se "
        "modifica (409)."
    ),
    request=PeriodoSerializer,
    responses={200: PeriodoSerializer, 400: RESPUESTA_400, 409: RESPUESTA_409},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Períodos"],
    summary="Eliminar período",
    description=(
        "Se elimina definitivamente solo si no tiene detalles ni metas; "
        "si los tiene se rechaza (409) y corresponde cerrarlo."
    ),
    responses={204: None, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def periodo_detalle(request, pk):
    periodo = obtener_o_404(Periodo.objects.all(), pk, "Período no encontrado.")
    exigir_permiso(request, Periodo)

    if request.method == "GET":
        return Response(PeriodoSerializer(periodo).data)

    if request.method in ("PUT", "PATCH"):
        if periodo.cerrado:
            return conflicto("Este período está cerrado y no puede modificarse.")

        return actualizar(request, PeriodoSerializer, periodo)

    if periodo.detalles.exists() or periodo.metas.exists():
        return conflicto(
            f"El período '{periodo.codigo}' tiene detalles o metas "
            "asociados y no puede eliminarse. Ciérrelo para conservar su "
            "historial."
        )

    periodo.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================
# METAS
# ============================================================

@extend_schema(
    methods=["GET"],
    tags=["Metas"],
    summary="Listar metas",
    parameters=[
        PARAM_ESTADO,
        PARAM_BUSQUEDA,
        OpenApiParameter(
            name="periodo",
            type=OpenApiTypes.INT,
            description="Id del período.",
        ),
        OpenApiParameter(
            name="cargo",
            type=OpenApiTypes.STR,
            description="Id del cargo, o 'sin' para las metas generales.",
        ),
    ],
    responses={200: MetaSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    tags=["Metas"],
    summary="Registrar meta",
    description=(
        "El período debe estar abierto y la actividad activa. Las metas "
        "activas de un mismo período y cargo no pueden superar el 100%."
    ),
    request=MetaSerializer,
    responses={201: MetaSerializer, 400: RESPUESTA_400},
    examples=[
        OpenApiExample(
            "Meta de un cargo",
            value={
                "codigo": "GSOC-VISITAS",
                "nombre": "Visitas a terreno",
                "descripcion": "Visitas del Gestor Social en el trimestre.",
                "periodo": 1,
                "actividad": 1,
                "cargo": 1,
                "valor_objetivo": "12.00",
                "ponderacion": "20.00",
            },
            request_only=True,
        ),
    ],
)
@api_view(["GET", "POST"])
def meta_lista(request):
    exigir_permiso(request, MetaModelo)

    if request.method == "GET":
        metas = MetaModelo.objects.select_related("periodo", "actividad", "cargo")
        metas = filtrar_por_estado(request, metas)
        metas = buscar(
            request,
            metas,
            ["codigo", "nombre", "periodo__codigo", "actividad__nombre",
             "cargo__nombre"],
        )

        periodo_id = request.query_params.get("periodo", "")
        if periodo_id.isdigit():
            metas = metas.filter(periodo_id=int(periodo_id))

        cargo_id = request.query_params.get("cargo", "")
        if cargo_id == "sin":
            metas = metas.filter(cargo__isnull=True)
        elif cargo_id.isdigit():
            metas = metas.filter(cargo_id=int(cargo_id))

        return Response(MetaSerializer(metas, many=True).data)

    serializer = MetaSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Metas"],
    summary="Consultar meta",
    responses={200: MetaSerializer, 404: RESPUESTA_404},
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Metas"],
    summary="Modificar meta",
    request=MetaSerializer,
    responses={200: MetaSerializer, 400: RESPUESTA_400, 409: RESPUESTA_409},
)
@extend_schema(
    methods=["DELETE"],
    tags=["Metas"],
    summary="Dar de baja meta (baja lógica)",
    description="No se modifican metas de períodos cerrados (409).",
    responses={200: MetaSerializer, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["GET", "PUT", "PATCH", "DELETE"])
def meta_detalle(request, pk):
    meta = obtener_o_404(
        MetaModelo.objects.select_related("periodo", "actividad", "cargo"),
        pk,
        "Meta no encontrada.",
    )

    if request.method == "GET":
        exigir_permiso(request, MetaModelo)
        return Response(MetaSerializer(meta).data)

    # Igual que en la web, la baja de una meta usa el permiso "change".
    exigir_permiso(request, MetaModelo, "change")

    if meta.periodo.cerrado:
        return conflicto("No se pueden modificar metas de períodos cerrados.")

    if request.method in ("PUT", "PATCH"):
        return actualizar(request, MetaSerializer, meta)

    if meta.activo:
        meta.activo = False
        meta.save(update_fields=["activo"])

    return Response(MetaSerializer(meta).data)


@extend_schema(
    tags=["Metas"],
    summary="Reactivar meta",
    description=(
        "Se rechaza (409) si el período está cerrado, si la actividad está "
        "inactiva o si la ponderación superaría el 100% del cargo."
    ),
    request=None,
    responses={200: MetaSerializer, 404: RESPUESTA_404, 409: RESPUESTA_409},
)
@api_view(["POST"])
def meta_reactivar(request, pk):
    exigir_permiso(request, MetaModelo, "change")
    meta = obtener_o_404(
        MetaModelo.objects.select_related("periodo", "actividad", "cargo"),
        pk,
        "Meta no encontrada.",
    )

    if meta.activo:
        return Response(MetaSerializer(meta).data)

    if meta.periodo.cerrado:
        return conflicto("No se pueden modificar metas de períodos cerrados.")

    if not meta.actividad.activo:
        return conflicto(
            "No se puede reactivar una meta asociada a una actividad inactiva."
        )

    disponible = meta.ponderacion_disponible()

    if meta.ponderacion > disponible:
        ambito = (
            f"el cargo '{meta.cargo.nombre}' en el período"
            if meta.cargo_id else "el período"
        )
        return conflicto(
            f"No se puede reactivar la meta: {ambito} superaría el 100% de "
            f"ponderación (disponible: {disponible}%)."
        )

    meta.activo = True
    meta.save(update_fields=["activo"])

    return Response(MetaSerializer(meta).data)
