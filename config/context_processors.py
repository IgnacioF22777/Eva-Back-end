"""Versión de los archivos estáticos propios (evita CSS antiguo en caché).

Nginx entrega /static/ sin cabeceras de caché y el navegador decide cuánto
tiempo reutilizar el CSS. Si el HTML se actualiza pero el navegador sigue
con el custom.css anterior, la página se ve rota (por ejemplo, texto blanco
sobre fondo blanco en la portada). La plantilla agrega ?v=<versión> al
enlace: cuando el archivo cambia, cambia la URL y el navegador lo descarga
de nuevo.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings


@lru_cache(maxsize=1)
def _version():
    archivos = [
        Path(carpeta) / "css" / "custom.css" for carpeta in settings.STATICFILES_DIRS
    ]
    for archivo in archivos:
        if archivo.exists():
            return str(int(archivo.stat().st_mtime))
    return "1"


def version_estaticos(request):
    return {"version_estaticos": _version()}
