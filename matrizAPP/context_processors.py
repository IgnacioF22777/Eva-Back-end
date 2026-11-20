from django.utils.functional import SimpleLazyObject


def configuracion_matriz(request):
    """
    `config_matriz` en las plantillas, para mostrar los porcentajes
    vigentes (felicitación y reclamo) sin escribirlos a mano. Es perezoso:
    solo consulta la base si la plantilla lo usa.
    """
    from .models import ConfiguracionMatriz

    return {"config_matriz": SimpleLazyObject(ConfiguracionMatriz.obtener)}
