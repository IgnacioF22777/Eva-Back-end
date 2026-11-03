import re
from importlib import metadata
from pathlib import Path

from django.conf import settings
from django.core.checks import Warning, register


# ============================================================
# COMPROBACIÓN: VERSIONES INSTALADAS VS requirements.txt
# ============================================================
# Producción (EC2) y los equipos de desarrollo deben usar exactamente las
# versiones de requirements.txt. Si alguien instala otra versión (por
# ejemplo, Django 6 en su PC mientras el servidor usa 4.2), Django lo
# avisa en `manage.py check`, `runserver`, `migrate` y en las pruebas.
#
# Solo emite advertencias: nunca impide que la aplicación funcione.

LINEA_FIJADA = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)\s*(?:;(.*))?$")


def version_instalada(nombre):
    for candidato in (nombre, nombre.replace("-", "_"), nombre.replace("_", "-")):
        try:
            return metadata.version(candidato)
        except metadata.PackageNotFoundError:
            continue

    return None


def aplica_en_este_equipo(marcador):
    if not marcador or not marcador.strip():
        return True

    try:
        from packaging.markers import Marker
    except ImportError:
        return True

    try:
        return Marker(marcador.strip()).evaluate()
    except Exception:
        return True


def leer_requisitos(ruta):
    requisitos = []

    for linea in ruta.read_text(encoding="utf-8").splitlines():
        coincidencia = LINEA_FIJADA.match(linea)

        if coincidencia:
            nombre, version, marcador = coincidencia.groups()

            if aplica_en_este_equipo(marcador):
                requisitos.append((nombre, version))

    return requisitos


@register()
def versiones_de_dependencias(app_configs=None, **kwargs):
    ruta = Path(settings.BASE_DIR) / "requirements.txt"

    if not ruta.exists():
        return []

    avisos = []

    for nombre, esperada in leer_requisitos(ruta):
        instalada = version_instalada(nombre)

        if instalada is None:
            avisos.append(Warning(
                f"{nombre} no está instalado (requirements.txt pide {esperada}).",
                hint="Ejecute: pip install -r requirements.txt",
                id="sgr.W001",
            ))
        elif instalada != esperada:
            avisos.append(Warning(
                f"{nombre} {instalada} está instalado, pero requirements.txt "
                f"(y el servidor de producción) usan {esperada}.",
                hint="Ejecute: pip install -r requirements.txt",
                id="sgr.W002",
            ))

    return avisos
