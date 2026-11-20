"""Configuración para ejecutar las pruebas automatizadas sin MariaDB.

Usa SQLite en memoria, de modo que cualquier integrante (o un tercero que
reproduzca la instalación) puede correr la batería completa sin crear una
base de datos ni un archivo .env:

    python manage.py test --settings=config.settings_pruebas

La batería oficial se repite sobre MariaDB en el servidor con la
configuración normal (``python manage.py test``).
"""

import os

# La clave solo se usa durante las pruebas; nunca en un servidor.
os.environ.setdefault(
    "SECRET_KEY",
    "clave-exclusiva-para-pruebas-automatizadas-no-usar-en-produccion",
)

from config.settings import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Hash rápido: las pruebas crean muchos usuarios y no necesitan PBKDF2.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
