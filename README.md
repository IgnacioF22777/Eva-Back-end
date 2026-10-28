# Evaluación Sumativa #3: Aplicación Web con CRUD

Proyecto desarrollado para la asignatura **Programación Back End (TI3041)** de la
carrera de Ingeniería en Informática / Analista Programador.

## Descripción del Proyecto

El **SGR (Sistema de Gestión de Resultados)** es una plataforma web modular para
la Municipalidad de La Serena. Permite administrar delegaciones territoriales,
sus servicios, los compromisos del Tubo de Gestión y las tablas maestras de
actividades, períodos y metas.

La aplicación se opera **íntegramente con Django Templates**. Django Admin no
está expuesto: la ruta `/admin/` responde `404` para cualquier usuario, incluido
el Administrador. Toda la funcionalidad evaluada (crear, buscar, listar,
modificar y dar de baja) se realiza desde interfaces propias.

## Funcionalidades

### Autenticación y perfiles

- **Inicio de sesión con RUT o correo** (`/seguridad/login/`), con bloqueo de
  15 minutos tras 5 intentos fallidos.
- **Recuperación de contraseña** con el flujo nativo de Django y envío de correo
  (texto y HTML).
- **Tres perfiles obligatorios**: Administrador, Supervisor y Administrativo.
- **Paneles exclusivos por perfil**: cada usuario solo puede abrir su propio
  panel; cualquier intento de abrir el panel de otro perfil responde `403`.
- **Menú construido por permisos**: un perfil no ve enlaces a secciones que no
  puede utilizar.

### Mantenedores

Todos incluyen **crear, buscar, listar, modificar, dar de baja y reactivar**.
Ningún registro se elimina definitivamente: la baja es lógica y reversible.

| Módulo | Ruta | Detalle |
|---|---|---|
| Delegaciones | `/delegaciones/` | Búsqueda por nombre, encargado, correo o dirección; filtro por estado |
| Servicios | `/delegaciones/<id>/` | CRUD anidado en la ficha de la delegación, con búsqueda |
| Compromisos | `/gestion/compromisos/` | Búsqueda por tarea o delegación; filtro por semáforo y estado |
| Catálogo de Actividades | `/maestros/catalogo/` | Búsqueda por código, nombre, área o descripción |
| Metas | `/maestros/metas/` | Búsqueda por código, nombre, período o actividad |
| Detalles de período | `/maestros/detalle-periodos/` | Baja lógica; bloqueado en períodos cerrados |
| Usuarios | `/seguridad/usuarios/` | Baja lógica y reactivación |
| Roles | `/seguridad/roles/` | Los roles se conservan; no se borran |

### Reglas de negocio

- **Semáforo automático de compromisos**: el estado se calcula desde el
  cumplimiento y no puede editarse a mano.
  - **Verde**: 90 % o más.
  - **Amarillo**: 60 % a 89 %.
  - **Rojo**: menos de 60 %.
- **Bloqueo de baja de delegaciones**: una delegación con servicios o
  compromisos activos no puede darse de baja hasta reasignarlos o desactivarlos.
- **Validación de duplicados**: no se crean delegaciones ni servicios activos
  con el mismo nombre. Si existe un registro inactivo equivalente, se reactiva
  en lugar de duplicarlo.
- **Integridad referencial**: los servicios y compromisos usan `PROTECT`; no se
  puede borrar una delegación con registros asociados.
- **Períodos cerrados**: sus detalles no se pueden crear, editar ni dar de baja.

## Stack Tecnológico

- **Lenguaje:** Python 3.9+
- **Framework:** Django 4.2
- **Servidor Web:** Nginx + Gunicorn
- **Base de Datos:** MySQL / MariaDB
- **Infraestructura:** AWS EC2 (Amazon Linux 2023)
- **Control de Versiones:** Git + GitHub

## Instalación y Despliegue Local

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/IgnacioF22777/Eva-Back-end.git
   ```
2. Crear y activar el entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Crear el archivo `.env`:
   ```
   SECRET_KEY=tu_clave_secreta
   DB_NAME=evaluacion_db
   DB_USER=usuario
   DB_PASSWORD=clave
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DEBUG=False
   ```
5. Aplicar migraciones y cargar datos:
   ```bash
   python manage.py migrate
   python manage.py import_data
   ```
6. Crear los roles y permisos base:
   ```bash
   python manage.py crear_roles
   ```
7. Ejecutar el servidor de desarrollo:
   ```bash
   python manage.py runserver
   ```

## Pruebas Automatizadas

```bash
python manage.py test
```

La suite cubre autenticación, recuperación de contraseña, permisos por perfil,
CRUD de los mantenedores, búsqueda, duplicados, baja lógica, reactivación,
semáforo y cierre de `/admin/`.

- **136 pruebas en verde** en el servidor con Django 4.2.
- Verificación de extremo a extremo con los tres perfiles en producción,
  ejecutada dentro de una transacción revertida para no dejar datos de prueba.

## Seguridad

- `DEBUG` se controla por variable de entorno y por defecto es `False`.
- Credenciales y secretos viven en `.env`, excluido de Git y con permisos `600`.
- Contraseñas protegidas con los hashers de Django y validadores de robustez.
- Control de acceso en el servidor con `@login_required` y
  `@permission_required`; un permiso faltante responde `403`.
- Todos los formularios POST usan `{% csrf_token %}`.
- Los detalles del incidente de la llave SSH y las medidas aplicadas están en
  [`SECURITY.md`](SECURITY.md).

## Despliegue en AWS

- Instancia EC2 con Amazon Linux 2023.
- Gunicorn como servidor de aplicación sobre socket Unix.
- Nginx como proxy inverso, con `X-Real-IP` para el control de solicitudes.
- MariaDB escuchando solo en `127.0.0.1`.
- Despliegue validado con respaldo previo de la base, migraciones, recolección
  de estáticos y reinicio de Gunicorn.

## Autoría por Módulo

| Módulo / Transacción | Responsable |
|---|---|
| Delegaciones y Servicios | Integrante 1 |
| Compromisos del Tubo de Gestión | Integrante 1 |
| Catálogo de Actividades | Integrante 2 |
| Metas y Detalles de período | Integrante 2 |

> Completar los nombres de los integrantes en la portada del informe. La
> distribución anterior respeta el mínimo de **dos mantenedores por integrante**
> exigido por la pauta.

## Evidencia de IA

El proyecto fue desarrollado con apoyo de herramientas de IA (OpenCode) para
revisión de seguridad, diseño de la baja lógica, construcción de los
mantenedores, redacción de pruebas automatizadas y resolución de errores de
despliegue en AWS. Las decisiones técnicas fueron revisadas y validadas contra
la pauta y el entorno real; la IA se documenta como evidencia de apoyo y no
reemplaza los mecanismos nativos de Django.

---

*Primavera 2026*
