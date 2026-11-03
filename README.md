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

Los mantenedores de **Delegaciones, Servicios, Compromisos, Catálogo, Metas,
Detalles de período y Usuarios** incluyen crear, buscar, listar, modificar, dar
de baja y reactivar. Ningún registro se elimina definitivamente: la baja es
lógica y reversible.

> **Sobre el requisito "Eliminar" de la pauta:** se implementa como **baja
> lógica**. El registro desaparece del listado de activos, se conserva en la base
> de datos con `activo=False` y puede reactivarse. Esto evita perder trazabilidad
> y respeta la integridad referencial (`PROTECT`) del sistema.

| Módulo | Ruta | Detalle |
|---|---|---|
| Delegaciones | `/delegaciones/` | Búsqueda por nombre, encargado, correo o dirección; filtro por estado |
| Servicios | `/delegaciones/<id>/` | CRUD anidado en la ficha de la delegación, con búsqueda |
| Compromisos | `/gestion/compromisos/` | Búsqueda por tarea o delegación; filtro por semáforo y estado |
| Catálogo de Actividades | `/maestros/catalogo/` | Búsqueda por código, nombre, área o descripción |
| Metas | `/maestros/metas/` | Búsqueda por código, nombre, período o actividad |
| Detalles de período | `/maestros/detalle-periodos/` | Baja lógica; bloqueado en períodos cerrados |
| Períodos de medición | `/maestros/periodos/` | Alta y edición; el cierre del período bloquea sus detalles |
| Usuarios | `/seguridad/usuarios/` | Baja lógica y reactivación |
| Roles | `/seguridad/roles/` | Los roles se conservan; no se borran |

### Fase 4: asignación y avance de compromisos

El flujo de ejecución de un compromiso se divide en dos transacciones atómicas
independientes, para que ninguna quede a medias:

| Transacción | Quién la ejecuta | Ruta | Qué hace |
|---|---|---|---|
| **T1: asignación** | Supervisor | `/gestion/compromisos/<id>/asignar/` | Asigna el compromiso a una delegación y a un servicio de esa delegación |
| **T2: avance** | Administrativo | `/gestion/compromisos/<id>/avance/` | Registra el porcentaje, la evidencia y la observación del avance |

- **Historial**: `/gestion/compromisos/<id>/historial/` muestra todas las
  asignaciones y todos los avances, en solo lectura.
- **Bloqueo pesimista**: ambas transacciones bloquean la fila del compromiso con
  `SELECT ... FOR UPDATE` (`select_for_update()`), de modo que dos usuarios no
  pueden asignar o avanzar el mismo compromiso al mismo tiempo.
- **Reasignación sin pérdida de historial**: al reasignar, la asignación anterior
  se marca como histórica (`activo=False`) y se conserva; nunca se elimina.
- **Un solo camino para el porcentaje**: `CompromisoForm` ya no expone
  `cumplimiento` ni `delegacion`. El porcentaje solo cambia por T2 y la
  delegación/servicio solo por T1.
- **Avance no retrocede**: un nuevo avance no puede ser menor al cumplimiento
  vigente del compromiso.
- **Evidencia obligatoria**: cada avance exige una referencia verificable (acta,
  correo, fotografía, documento o enlace).
- **Archivos de respaldo**: el avance acepta adjuntos de cualquier tipo
  (fotografías, PDF, planillas, documentos, comprimidos, audio o video) con
  límites: **5 archivos**, **10 MB por archivo** y **25 MB por avance**. Se
  rechazan ejecutables y scripts (`.exe`, `.bat`, `.sh`, `.js`, `.php`,
  `.html`, etc.) y archivos vacíos. Si la transacción se revierte, los archivos
  ya escritos se borran del disco.
- **Descarga protegida**: los archivos se guardan con nombre aleatorio en
  `MEDIA_ROOT`, que no se publica; se descargan solo por
  `/gestion/adjuntos/<id>/descargar/`, que exige sesión, permiso y pertenecer a
  la delegación del compromiso.

### Ámbito por delegación

Los permisos indican **qué** puede hacer cada perfil; el ámbito indica **sobre
qué delegación** puede hacerlo (`tubo_gestionAPP/ambito.py`):

| Perfil | Compromisos que ve y opera |
|---|---|
| Administrador | Todos (visión global) |
| Supervisor | Los de su delegación y los aún sin asignar; solo asigna a servicios de su delegación |
| Administrativo | Solo los de su delegación |

- Se aplica en el tablero, la búsqueda, los paneles, la edición, la baja, T1,
  T2, el historial y la descarga de adjuntos. Fuera de ámbito se responde
  **403** con el motivo.
- En T1 y T2 el ámbito se vuelve a comprobar **dentro de la transacción**, con
  la fila bloqueada, por si el compromiso se reasignó mientras el usuario tenía
  el formulario abierto.
- Un Supervisor o Administrativo **sin delegación** no ve compromisos
  (denegación por defecto), y el formulario de usuarios exige delegación para
  esos perfiles.

### Límites de largo de los textos

| Campo | Máximo |
|---|---|
| Evidencia del avance | 2.000 caracteres |
| Observaciones (avance, asignación, detalle de período) | 1.000 caracteres |
| Descripción (catálogo, metas) | 1.000 caracteres |

El límite se valida en el formulario y en el modelo, y el HTML muestra un
contador de caracteres.

### Demostración preparada T1 → T2

La base de producción queda con un caso listo para mostrar el cambio de semáforo
en vivo:

- **Compromiso ID 1**: “Implementar plataforma de trámites en línea”, en **60 %**
  (amarillo), ya asignado por **T1** a **Delegación Centro / Trámites
  municipales**.
- Al ingresar como un **Administrativo de Delegación Centro** y registrar
  **95 %** por **T2** (con evidencia y, opcionalmente, archivos), el compromiso
  cambia automáticamente a **verde**. Por el ámbito por delegación, un
  Administrativo de otra delegación recibe **403**.
- La verificación de T2 se ejecutó en una transacción revertida: el registro de
  prueba no queda en la base y el compromiso permanece en 60 % para la revisión.

### Reglas de negocio

- **Semáforo automático de compromisos**: el estado se calcula desde el
  cumplimiento y no puede editarse a mano.
  - **Verde**: 90 % o más.
  - **Amarillo**: 60 % a 89 %.
  - **Rojo**: menos de 60 %.
- **Bloqueo de baja de delegaciones**: una delegación con servicios o
  compromisos activos no puede darse de baja hasta reasignarlos o desactivarlos.
- **Bloqueo de baja de servicios**: un servicio con compromisos activos
  asignados no puede darse de baja hasta reasignarlos o desactivarlos.
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
semáforo, cierre de `/admin/` y las dos transacciones atómicas de la Fase 4
(incluida la reversión completa cuando falla un paso). En total son **208
pruebas**; `tubo_gestionAPP/test_ambito_y_adjuntos.py` cubre el ámbito por
delegación, los límites de largo de texto y los archivos adjuntos (límites,
extensiones bloqueadas, limpieza ante reversión y descarga protegida).

- **167 pruebas en verde** en local (Django 5.2).
- **154 pruebas en verde** en el servidor con Django 4.2 para los módulos
  `tubo_gestionAPP`, `delegacionesAPP` y `seguridadAPP`.
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

La pauta exige, para un trabajo de **dos integrantes**, un mínimo de **cuatro
mantenedores y dos transacciones**. El proyecto entrega **siete mantenedores
completos y dos transacciones atómicas**, distribuidas así:

| Módulo / Transacción | Responsable |
|---|---|
| Delegaciones y Servicios | Ignacio Figueroa |
| Compromisos del Tubo de Gestión | Ignacio Figueroa |
| **T1: Asignación de compromisos a delegación y servicio** | Ignacio Figueroa |
| Catálogo de Actividades | Orlando Iribarren |
| Metas y Detalles de período | Orlando Iribarren |
| **T2: Registro de avance con evidencia** | Orlando Iribarren |
| Usuarios, Roles y Perfiles (transversal) | Ignacio Figueroa y Orlando Iribarren |

### Cobertura de la pauta

| Requisito de la pauta (2 integrantes) | Mínimo | Entregado |
|---|---|---|
| Mantenedores completos | 4 | **7** |
| Transacciones operacionales | 2 | **2** |
| Perfiles de usuario | 3 | **3** |
| Dashboards diferenciados | 3 | **3** |

## Cuentas de Demostración

| Perfil | Usuario (login) | Delegación | Acceso |
|---|---|---|---|
| Administrador | `21988036-7` | — (visión global) | Total |
| Supervisor | `21.345.678-4` | Delegación Centro | Intermedio |
| Administrativo | `22.456.789-8` | Delegación Av. del Mar | Mínimo |

- El ingreso es en `/seguridad/login/` con **RUT (con o sin puntos), usuario o
  correo**.
- **Las contraseñas no se publican en el repositorio.** Se entregan de forma
  privada y se muestran durante la revisión presencial.
- Las cuentas demo son cuentas reales con permisos reales; al término de la
  evaluación deben cambiarse sus contraseñas o darse de baja lógica.

## Evidencia de IA

El proyecto fue desarrollado con apoyo de herramientas de IA (**OpenCode**) usadas
como asistente técnico: revisión de seguridad, diseño de la baja lógica,
construcción de los mantenedores, redacción de pruebas automatizadas y resolución
de errores de despliegue en AWS.

Las respuestas de la IA fueron **revisadas, corregidas y validadas** contra la
pauta y contra el entorno real (Django 5.2 en local, Django 4.2 en el servidor).
La IA se documenta como evidencia de apoyo y **no reemplaza** los mecanismos
nativos de Django (autenticación, permisos, formularios, ORM y migraciones).

### Prompts representativos y su aplicación

| Área | Prompt (resumen) | Aplicación en el proyecto |
|---|---|---|
| Seguridad | "Revisa el repositorio y detecta secretos o llaves expuestas" | Rotación de la llave SSH, `.gitignore` ampliado y `SECURITY.md` |
| Perfiles | "Consolida 6 roles históricos en 3 perfiles sin perder usuarios" | Migración `0002_perfiles_acceso` y `seguridadAPP/roles.py` |
| Recuperación | "Implementa recuperación de contraseña con el flujo nativo de Django y SMTP" | 4 vistas, 7 plantillas y límite de solicitudes por IP |
| Baja lógica | "Ningún registro debe borrarse; solo desactivarse y reactivarse" | Campos `activo`, guardas de baja y pruebas por mantenedor |
| Fase 4 | "Implementa dos transacciones atómicas con `select_for_update` sobre `Compromiso`" | `compromiso_asignar` y `compromiso_avance`, con reversión total ante fallo |
| Pruebas | "Escribe pruebas de atomicidad que fallen después de la primera escritura" | 167 pruebas, incluidas las de rollback de T1 y T2 |

> En el documento técnico se incluyen los prompts completos, extractos de las
> respuestas y las capturas de la aplicación resultante.

---

*Primavera 2026*
