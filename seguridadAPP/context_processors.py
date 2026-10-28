from .perfiles import DESCRIPCIONES, ETIQUETAS, perfil_de


def perfil_actual(request):
    """
    Expone el perfil del usuario en todas las plantillas para que el
    menú y los paneles se construyan según el perfil y no según
    is_staff.
    """
    usuario = getattr(request, "user", None)

    if usuario is None or not usuario.is_authenticated:
        return {
            "perfil_actual": None,
            "perfil_etiqueta": "",
            "perfil_descripcion": "",
        }

    if not hasattr(usuario, "_perfil_sgr"):
        usuario._perfil_sgr = perfil_de(usuario)

    perfil = usuario._perfil_sgr

    return {
        "perfil_actual": perfil,
        "perfil_etiqueta": ETIQUETAS.get(perfil, ""),
        "perfil_descripcion": DESCRIPCIONES.get(perfil, ""),
    }
