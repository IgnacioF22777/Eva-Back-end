# Política de Seguridad — SGR Municipalidad de La Serena

Este documento registra el incidente de seguridad detectado durante la auditoría
del proyecto y las medidas aplicadas. Se mantiene versionado para dejar
trazabilidad técnica sin reescribir el historial de Git.

## 1. Incidente: exposición de llave privada SSH

| Campo | Detalle |
|---|---|
| Severidad | Crítica |
| Detectado | Auditoría de seguridad previa a la Evaluación Sumativa 3 |
| Componente | `aws_key.pem` (llave privada del usuario `ec2-user`) |
| Origen | Commit `b44a94d` ("Add migrations for new apps") |
| Remoción del árbol | Commit `9d693fa` ("chore: remove exposed ssh key from git") |
| Estado | **Remediado** |

### Causa raíz

El archivo `.pem` se agregó al repositorio por error y el `.gitignore` no
excluía llaves ni certificados. Eliminar el archivo en un commit posterior
**no elimina el contenido del historial**: cualquier persona con acceso al
repositorio puede recuperarlo con `git show b44a94d:aws_key.pem`.

### Contención aplicada

1. **Rotación de credenciales**: se generó un nuevo par de llaves
   (`sgr-produccion-2026`) y se autorizó su llave pública en la instancia EC2.
2. **Revocación de la llave antigua**: se eliminó la clave comprometida de
   `~/.ssh/authorized_keys`. Verificado: la llave antigua ya **no** autentica
   y `authorized_keys` contiene una sola entrada.
3. **Prevención**: se agregó `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.ppk`,
   `*.sql` y `*.dump` al `.gitignore`.
4. **Resguardo local**: las llaves privadas se movieron fuera del directorio
   del proyecto (`%USERPROFILE%\.ssh`) con permisos restringidos al usuario.

### Riesgo residual

La llave antigua sigue siendo recuperable desde el historial de Git. Se acepta
este riesgo porque la credencial fue **revocada en el servidor** y ya no otorga
acceso. Se prioriza conservar el historial de desarrollo requerido por la
asignatura.

> Si el repositorio se hiciera público a terceros o la instancia se reutilizara,
> se recomienda purgar el historial con `git filter-repo` y notificar a los
> colaboradores que deben reclonar.

## 2. Endurecimiento de configuración

- `DEBUG` se controla por variable de entorno y por defecto es `False`.
- Los secretos (`SECRET_KEY`, credenciales de base de datos y correo) viven en
  `.env`, excluido del control de versiones y con permisos `600`.
- `ALLOWED_HOSTS` restringido a la IP de la instancia y a `localhost`.

## 3. Control de acceso por perfiles (Fase 1)

El sistema migró de seis roles históricos a **tres perfiles obligatorios**,
implementados como grupos de Django con permisos explícitos.

| Perfil | Permisos | Alcance |
|---|---|---|
| Administrador | 56 | Acceso total: usuarios, roles, catálogos y operación |
| Supervisor | 26 | Operación, catálogos y lectura de usuarios |
| Administrativo | 8 | Consulta de operación y registro de compromisos |

### Reglas aplicadas

1. **Nadie ve el panel de otro perfil.** Cada panel vive en su propia ruta y
   está protegido por `@perfil_requerido`. Un perfil distinto recibe `403`, no
   una redirección silenciosa.
2. **Sin perfil no hay acceso.** Un usuario autenticado sin ninguno de los tres
   perfiles recibe `403` al entrar a `/seguridad/panel/`.
3. **Toda la aplicación exige sesión.** Las vistas de Delegaciones, Tubo de
   Gestión y Maestros dejaron de ser públicas.
4. **El menú se construye por permisos**, no por `is_staff`, de modo que un
   perfil no ve enlaces a secciones que no puede abrir.
5. **Baja lógica, no borrado.** Los usuarios se desactivan (`is_active=False`);
   la reactivación está disponible para el Administrador. Los roles tampoco se
   eliminan: se conservan para mantener el historial de acceso.
6. **Los permisos usan el *app label* real** (`sgr_maestrosAPP`), distinto del
   *namespace* de URLs (`sgr_maestros`). Confundirlos produce `403` silenciosos.

### Verificación ejecutada en producción

`58` pruebas automatizadas y una prueba de extremo a extremo con las tres
cuentas, en la base real:

```
Administrador    -> panel/administrador 200 | supervisor 403 | administrativo 403
Supervisor       -> panel/supervisor    200 | administrador 403 | administrativo 403
Administrativo   -> panel/administrativo 200 | administrador 403 | supervisor 403
Sin perfil       -> panel 403
Anónimo          -> panel, usuarios y maestros 302 (redirige al login)
```

## 4. Recuperación de contraseña (Fase 2)

Se implementó con el **flujo nativo de Django** (`PasswordResetView` y sus tres
vistas asociadas), sin lógica de tokens propia.

### Funcionamiento

1. El usuario abre **"¿Olvidó su contraseña?"** desde el inicio de sesión.
2. Escribe su **correo institucional**. Django busca la cuenta por correo, no
   por RUT.
3. Si la cuenta existe y está activa, recibe un enlace con un **token firmado**.
4. Abre el enlace, define la nueva contraseña y confirma con el botón
   **"Validar y cambiar contraseña"**.

### Propiedades de seguridad

| Propiedad | Implementación |
|---|---|
| Vigencia del enlace | 1 hora (`PASSWORD_RESET_TIMEOUT=3600`) |
| Reutilización | Imposible: el token se invalida al usarse |
| Cambio de contraseña | Invalida cualquier enlace pendiente |
| Enumeración de cuentas | El sistema responde igual exista o no el correo |
| Usuarios inactivos | No reciben enlace |
| Abuso del formulario | 5 solicitudes por IP cada 15 minutos |
| Identificación de IP | `X-Real-IP` de Nginx, no falsificable por el cliente |

### Configuración

Las credenciales viven solo en `.env` (permisos `600`, excluido de Git):

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<cuenta institucional de envio>
EMAIL_HOST_PASSWORD=<contrasena de aplicacion>
DEFAULT_FROM_EMAIL="SGR La Serena <cuenta institucional>"
EMAIL_TIMEOUT=10
```

`EMAIL_TIMEOUT` evita que un servidor de correo que no responde bloquee a los
workers de Gunicorn.

### Verificación ejecutada en producción

- **71 pruebas automatizadas** en verde durante la Fase 2, incluidas las del
  flujo completo. La suite se amplió a **136** en la Fase 3.
- Prueba real de extremo a extremo: se solicitó el enlace, **el correo llegó**
  con las versiones de texto y HTML, se abrió el enlace, la contraseña débil
  fue rechazada, la nueva fue aceptada, la contraseña antigua dejó de servir y
  la nueva permitió iniciar sesión.

### Limitaciones conocidas

1. El remitente es una **cuenta Gmail**, no el dominio `@laserena.cl`. Algunos
   filtros pueden enviar el mensaje a la carpeta de spam.
2. Límite de Gmail: alrededor de **500 destinatarios por día**.
3. La recuperación exige que el usuario tenga un **correo cargado** en su
   perfil. Si no lo tiene, debe solicitarla el Administrador.

> Para producción institucional se recomienda reemplazar Gmail por el **relay
> SMTP de la Municipalidad**, de modo que los correos salgan del dominio
> oficial con su configuración SPF/DKIM. El cambio es solo de variables de
> entorno.
>
> La contraseña de aplicación usada durante la evaluación debe **revocarse** al
> finalizar.

## 5. Mantenedores y baja lógica (Fase 3)

### Django Admin fuera de servicio

La pauta prohíbe usar Django Admin como mecanismo de administración. Por eso
`config/urls.py` **no incluye** `admin.site.urls`:

- `/admin/`, `/admin/login/` y `/admin/auth/user/` responden `404`, incluso para
  el Administrador.
- `django.contrib.admin` sigue en `INSTALLED_APPS` porque el modelo de usuarios
  y grupos lo utiliza internamente, pero su panel no está publicado.
- Toda operación se realiza desde interfaces propias con Django Templates.

### Baja lógica generalizada

| Entidad | Campo | Efecto |
|---|---|---|
| Delegación | `activo` | Se conserva; bloquea servicios y compromisos asociados |
| Servicio | `activo` | Se conserva; se reactiva sin duplicar |
| Compromiso | `activo` | Se conserva; el semáforo sigue calculándose |
| Detalle de período | `activo` | Se conserva; bloqueado si el período está cerrado |
| Usuario | `is_active` | Baja lógica con reactivación |
| Rol | — | Nunca se elimina; se ajustan usuarios y permisos |

Las acciones de baja y reactivación son **solo POST**, están protegidas con
`@require_POST` y exigen el permiso `delete_*` del modelo correspondiente.

### Reglas de integridad

1. **`Servicio.delegacion` y `Compromiso.delegacion` usan `PROTECT`**: no se
   puede eliminar una delegación con registros asociados.
2. **Unicidad de servicios** por delegación mediante `UniqueConstraint`, además
   de la validación de formulario.
3. **Validación de duplicados** en delegaciones y detalles de período. Si el
   registro equivalente está inactivo, se reactiva en lugar de crear otro.
4. **Bloqueo de baja** de una delegación con servicios o compromisos activos.
5. **Semáforo derivado en el servidor**: `Compromiso.estado` es
   `editable=False` y se recalcula en `save()` desde `cumplimiento`. El cliente
   no puede enviar un estado arbitrario.
6. **Períodos cerrados**: sus detalles no se crean, editan ni dan de baja.

### Permisos actualizados

El perfil **Supervisor** recibió los permisos CRUD de Delegaciones y Servicios
(además de Compromisos), alcanzando **26 permisos**. El perfil
**Administrativo** mantiene **8**: consulta de la operación y registro de
compromisos, sin edición ni baja.

### Verificación ejecutada

- **136 pruebas automatizadas en verde** con Django 4.2, en un clon aislado del
  repositorio y con SQLite en memoria (sin tocar la base real).
- `makemigrations --check` sin cambios pendientes antes y después del despliegue.
- Migraciones aplicadas en producción con **respaldo previo** de la base
  (`evaluacion_db_fase3_20261028_173908.sql.gz`, 22 tablas).
- Smoke test de rutas y permisos con los tres perfiles en producción, ejecutado
  **dentro de una transacción revertida**: no quedaron usuarios ni sesiones de
  prueba.
- Verificación de datos reales: 13 delegaciones, 48 servicios y 9 compromisos
  conservados; `/admin/` responde `404`.

## 6. Servicios expuestos

| Servicio | Estado inicial | Medida |
|---|---|---|
| SSH (22) | Acceso con llave | Rotada y revocada la anterior |
| HTTP (80) | Nginx + Gunicorn | Se mantiene; HTTPS pendiente (sin dominio) |
| MariaDB (3306) | `0.0.0.0` (todas las interfaces) | Restringido a `127.0.0.1` |
| phpMyAdmin | Público en `/phpmyadmin` | Restringido a acceso local (túnel SSH) |

## 7. Verificación

```bash
# La llave antigua debe ser rechazada
ssh -i aws_key.pem ec2-user@44.217.180.71      # Permission denied (publickey)

# La llave nueva debe funcionar
ssh -i sgr-nueva-key.pem ec2-user@44.217.180.71

# MariaDB no debe escuchar en interfaces públicas
ss -tln | grep 3306                             # 127.0.0.1:3306

# El repositorio no debe rastrear llaves
git ls-files | grep -E '\.(pem|key)$'           # sin resultados

# Django Admin no debe estar expuesto
curl -o /dev/null -s -w "%{http_code}\n" http://44.217.180.71/admin/   # 404

# La suite completa debe pasar
cd ~/Eva-Back-end && ./venv/bin/python manage.py test
```
