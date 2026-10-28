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
| Supervisor | 20 | Operación, catálogos y lectura de usuarios |
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
   la reactivación está disponible para el Administrador.
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

- **71 pruebas automatizadas** en verde, incluidas las del flujo completo.
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

## 5. Servicios expuestos

| Servicio | Estado inicial | Medida |
|---|---|---|
| SSH (22) | Acceso con llave | Rotada y revocada la anterior |
| HTTP (80) | Nginx + Gunicorn | Se mantiene; HTTPS pendiente (sin dominio) |
| MariaDB (3306) | `0.0.0.0` (todas las interfaces) | Restringido a `127.0.0.1` |
| phpMyAdmin | Público en `/phpmyadmin` | Restringido a acceso local (túnel SSH) |

## 6. Verificación

```bash
# La llave antigua debe ser rechazada
ssh -i aws_key.pem ec2-user@44.217.180.71      # Permission denied (publickey)

# La llave nueva debe funcionar
ssh -i sgr-nueva-key.pem ec2-user@44.217.180.71

# MariaDB no debe escuchar en interfaces públicas
ss -tln | grep 3306                             # 127.0.0.1:3306

# El repositorio no debe rastrear llaves
git ls-files | grep -E '\.(pem|key)$'           # sin resultados
```
