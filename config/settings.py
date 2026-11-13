from datetime import timedelta
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Creamos una ruta para nuestros html
TEMPLATES_DIR = os.path.join(BASE_DIR,'templates')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
# Se controla por variable de entorno y por defecto queda desactivado.
DEBUG = os.getenv("DEBUG", "False").strip().lower() in ("1", "true", "yes", "on")

# Dominios o IP desde los que se atiende el sitio, separados por coma. Si la
# variable no existe se usan la IP elástica actual y el equipo local, así
# que un servidor ya desplegado sigue funcionando sin cambios.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "44.217.180.71,localhost,127.0.0.1").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'delegacionesAPP',
    'tubo_gestionAPP',
    'emergenciasTerritorialesAPP',
    'reportesCiudadanosAPP',
    'sgr_maestrosAPP',
    'seguridadAPP',
    'organizacionesAPP',
    'oficinaPartesAPP',
    'atencionSocialAPP',  # EVA 3: tipos de atención social (RC-05).
    'actividadesAPP',  # EVA 3: registro diario de actividades (R1-R4).

    # API RESTful (Programación Back End): Django REST Framework,
    # autenticación JWT y documentación OpenAPI (Swagger / ReDoc).
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'apiAPP',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [TEMPLATES_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'seguridadAPP.context_processors.perfil_actual',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
        'OPTIONS': {
            'init_command': "SET time_zone='+00:00'",
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Autenticación: login con RUT o correo electrónico
# https://docs.djangoproject.com/en/4.2/topics/auth/customizing/

AUTHENTICATION_BACKENDS = [
    'seguridadAPP.backends.RutOCorreoBackend',
]

LOGIN_URL = 'seguridad:login'
LOGIN_REDIRECT_URL = 'seguridad:panel'
LOGOUT_REDIRECT_URL = 'seguridad:login'

# Sesiones protegidas: la cookie no es accesible desde JavaScript y
# expira tras 8 horas (o al cerrar el navegador si no se marca "recordar").
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Caché compartida en la base de datos.
# Guarda los contadores de intentos fallidos de inicio de sesión y de
# solicitudes de recuperación de contraseña. Con la caché en memoria
# (LocMemCache) cada worker de Gunicorn llevaba su propio contador, por lo
# que el bloqueo tras 5 intentos podía tardar hasta 15. En la base de
# datos todos los workers comparten el mismo contador.
# La tabla se crea con la migración seguridadAPP.0004 (createcachetable).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "sgr_cache",
    }
}


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'es-cl'

TIME_ZONE = 'America/Santiago'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]


# Archivos adjuntos (evidencias de los avances)
# Se guardan en MEDIA_ROOT, que NO se publica en Nginx ni tiene MEDIA_URL
# en las rutas: cada descarga pasa por una vista que exige sesión, permiso
# y pertenecer a la delegación del compromiso.

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

ADJUNTOS_MAX_ARCHIVOS = int(os.getenv("ADJUNTOS_MAX_ARCHIVOS", "5"))
ADJUNTOS_MAX_MB_POR_ARCHIVO = int(os.getenv("ADJUNTOS_MAX_MB_POR_ARCHIVO", "10"))
ADJUNTOS_MAX_MB_TOTAL = int(os.getenv("ADJUNTOS_MAX_MB_TOTAL", "25"))

# Los archivos quedan legibles solo por el usuario del servicio.
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# Email
# https://docs.djangoproject.com/en/4.2/topics/email/
# Django 4.2 usa EMAIL_BACKEND (no existe la opción "MAILERS").
# En producción se configura SMTP mediante variables de entorno.

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in (
    "1", "true", "yes", "on",
)

# No bloquear al worker de Gunicorn si el servidor de correo no responde.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "SGR La Serena <no-reply@laserena.cl>",
)

# Vigencia del enlace de recuperación de contraseña (1 hora).
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))


# EVA 3: límite diario de registros por funcionario (R3).
MAX_INGRESOS_DIARIOS = 7

# ============================================================
# API RESTFUL (apiAPP)
# ============================================================
# https://www.django-rest-framework.org/api-guide/settings/
#
# - Autenticación: token JWT (Authorization: Bearer <token>). También se
#   acepta la sesión web, para que un usuario que ya ingresó al SGR pueda
#   abrir la API en el navegador (DRF exige CSRF en ese caso).
# - Por defecto toda ruta exige usuario autenticado. Además, cada vista
#   comprueba los permisos del perfil (Administrador, Supervisor,
#   Administrativo) con los mismos permisos de Django que usa la web.

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

# https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html
SIMPLE_JWT = {
    # El token de acceso dura poco; el de refresco, lo mismo que la sesión web.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=8),
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Una cuenta desactivada deja de poder usar sus tokens.
    "CHECK_USER_IS_ACTIVE": True,
    # Al cambiar la contraseña, los tokens emitidos antes dejan de servir.
    "CHECK_REVOKE_TOKEN": True,
}

# https://drf-spectacular.readthedocs.io/en/latest/settings.html
SPECTACULAR_SETTINGS = {
    "TITLE": "API SGR - Municipalidad de La Serena",
    "DESCRIPTION": (
        "API RESTful del Sistema de Gestión de Resultados (SGR).\n\n"
        "Para usarla: obtenga un token en POST /api/token/ con su RUT o "
        "correo y su contraseña, presione **Authorize** y pegue el token "
        "de acceso (access). Cada perfil solo puede usar las operaciones "
        "que sus permisos le autorizan, igual que en la aplicación web.\n\n"
        "Las eliminaciones son **bajas lógicas**: el registro se conserva "
        "con activo=false y puede reactivarse."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Orden de las secciones en Swagger y ReDoc.
    "TAGS": [
        {"name": "Autenticación", "description": "Tokens JWT y usuario actual."},
        {"name": "Delegaciones", "description": "Delegaciones territoriales."},
        {"name": "Servicios", "description": "Servicios de cada delegación."},
        {"name": "Compromisos", "description": "Tubo de Gestión con semáforo."},
        {"name": "Catálogo de actividades", "description": "Actividades de Ejecución o Preparatoria (R5)."},
        {"name": "Períodos", "description": "Períodos de medición."},
        {"name": "Metas", "description": "Metas por período y cargo."},
    ],
}
