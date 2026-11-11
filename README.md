# SGR — Sistema de Gestión de Resultados (Municipalidad de La Serena)

Proyecto desarrollado para las asignaturas **Programación Back End (TI3041)**
(Evaluación Sumativa #3: Aplicación Web con CRUD) y **Proyecto Integrado**
(Evaluación 3) de la carrera de Ingeniería en Informática / Analista Programador.

El caso de la Municipalidad de La Serena se usa como contexto académico: la
solución se plantea para su posterior presentación como propuesta de práctica.

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
Detalles de período, Usuarios y Cargos** incluyen crear, buscar, listar,
modificar, dar de baja y reactivar. Ningún registro se elimina definitivamente: la baja es
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
| Catálogo de Actividades | `/maestros/catalogo/` | Búsqueda por código, nombre, área o descripción; filtro por tipo de gestión (Ejecución/Preparatoria) |
| Metas | `/maestros/metas/` | Búsqueda por código, nombre, período, actividad o cargo; filtro por cargo o "sin cargo" |
| Detalles de período | `/maestros/detalle-periodos/` | Baja lógica; bloqueado en períodos cerrados; días computables automáticos |
| Períodos de medición | `/maestros/periodos/` | Búsqueda por código o nombre y filtro abierto/cerrado; muestra la suma de ponderaciones de cada cargo; se elimina solo sin detalles ni metas |
| Usuarios | `/seguridad/usuarios/` | Baja lógica y reactivación |
| Roles | `/seguridad/roles/` | Búsqueda por nombre; se elimina solo si no tiene usuarios y no es un perfil base |
| Cargos | `/seguridad/cargos/` | Búsqueda; baja lógica; se elimina solo sin funcionarios ni metas asociadas |

### Evaluación 3 (Proyecto Integrado): catálogo y metas por cargo

Integrado en `main` mediante el PR #6 (`feature/eva3-catalogo-metas`):

- **Tipo de gestión del catálogo (R5)**: cada actividad es de **Ejecución**
  (la acción realizada, suma puntaje) o **Preparatoria** (correos,
  coordinaciones e invitaciones, no suma). Por defecto es Ejecución, también
  para las actividades existentes (`CatalogoActividad.tipo_gestion`).
- **Metas por cargo**: cada meta puede asociarse a un cargo
  (`Meta.cargo`). Las metas activas de un mismo período y cargo no pueden
  superar el 100 %, y el formulario informa la ponderación disponible. Las
  metas sin cargo ("metas generales") forman un grupo aparte.
- **Cierre de período por cargo**: un período solo se cierra cuando las metas
  activas de **cada** cargo suman exactamente 100 % (`Periodo.validar_cierre`);
  el mensaje de error nombra el cargo incompleto.

Los demás requerimientos de la Evaluación 3 (actividades diarias R1–R4,
puntaje R7, alertas R6, felicitaciones y reclamos R8, ausencias R9, puntaje del
equipo R10, organizaciones comunitarias, atención social, carga de cargos y
metas reales) se integran por Pull Request a medida que cada integrante los
termina. Su estado se registra en la matriz de trazabilidad del informe de la
Evaluación 3.

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
- **Ponderación de metas**: las metas activas de un mismo período y cargo no
  pueden superar el 100 %, y el período solo puede cerrarse cuando cada cargo
  suma exactamente 100 % (`validar_suma_ponderaciones` y
  `validar_suma_ponderaciones_por_cargo`). Si el período solo tiene metas
  generales (sin cargo), se aplica la regla original sobre el total.
- **Tipo de gestión (R5)**: solo las actividades de Ejecución suman puntaje
  (`tipo_gestion_puntua`); un tipo desconocido se rechaza.
- **Días computables automáticos**: cada detalle de período calcula sus días
  hábiles descontando fines de semana y feriados nacionales de fecha fija y
  Semana Santa (`calcular_dias_computables`); ya no se escriben a mano.
- **Bloqueo de inicio de sesión compartido**: los intentos fallidos y las
  solicitudes de recuperación se cuentan en una caché guardada en la base de
  datos (`sgr_cache`), común a los 3 workers de Gunicorn. Así el bloqueo ocurre
  al quinto intento, lo atienda el worker que lo atienda. La tabla se crea sola
  con `migrate`.
- **Actividades con metas activas**: no se pueden dar de baja hasta dar de baja
  o reasignar esas metas.
- **Cargos protegidos**: un cargo con funcionarios o metas no se elimina
  (`verificar_eliminacion_cargo`); se da de baja lógica (`desactivar_cargo`).
- Los validadores de `tubo_gestionAPP/validadores.py` se usan en el sistema,
  no solo en las pruebas: login (`validar_credenciales`), RUT, ámbito por
  delegación, fechas, código único de catálogo, ponderaciones, días y cargos.

## API RESTful (`apiAPP`)

La app `apiAPP` expone los datos del SGR en formato JSON para que otros
sistemas puedan consumirlos. Está construida con **Django REST Framework**
usando **vistas basadas en funciones** (`@api_view`) y serializadores,
protegida con **JWT** y documentada con **Swagger / ReDoc**
(`drf-spectacular`).

### Cómo usarla

1. Obtener el token con el mismo usuario de la web (RUT, correo o usuario):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/token/ -H "Content-Type: application/json" -d '{"username": "12.345.678-5", "password": "su_clave"}'
   ```
   La respuesta trae `access` (dura 30 minutos) y `refresh` (dura 8 horas).
2. Enviar el token `access` en cada solicitud:
   ```bash
   curl http://127.0.0.1:8000/api/delegaciones/ -H "Authorization: Bearer <access>"
   ```
3. O usar la documentación interactiva en `/api/swagger/`: presionar
   **Authorize**, pegar el token `access` y probar cada operación.
   También está disponible en `/api/redoc/` y el esquema OpenAPI en
   `/api/schema/`.

### Rutas

| Recurso | Colección (GET listar, POST crear) | Detalle (GET, PUT, PATCH, DELETE) | Reactivar (POST) |
|---|---|---|---|
| Autenticación | `POST /api/token/`, `POST /api/token/refresh/`, `GET /api/yo/` | — | — |
| Delegaciones | `/api/delegaciones/` | `/api/delegaciones/<id>/` | `/api/delegaciones/<id>/reactivar/` |
| Servicios | `/api/servicios/` | `/api/servicios/<id>/` | `/api/servicios/<id>/reactivar/` |
| Compromisos | `/api/compromisos/` | `/api/compromisos/<id>/` | `/api/compromisos/<id>/reactivar/` |
| Catálogo de actividades | `/api/catalogo/` | `/api/catalogo/<id>/` | `/api/catalogo/<id>/reactivar/` |
| Períodos | `/api/periodos/` | `/api/periodos/<id>/` | — |
| Metas | `/api/metas/` | `/api/metas/<id>/` | `/api/metas/<id>/reactivar/` |

Los listados aceptan filtros en la URL: `?estado=activos|inactivos|todos`
(por defecto `activos`), `?q=texto` para buscar, y según el recurso
`?delegacion=<id>`, `?semaforo=verde|amarillo|rojo`,
`?tipo=EJECUCION|PREPARATORIA`, `?periodo=<id>` o `?cargo=<id>|sin`.

### Reglas que respeta

La API no tiene reglas propias: aplica las mismas que la aplicación web.

- **Mismas validaciones**: cada serializador valida con el formulario del
  mantenedor web (y este con el modelo), por lo que la ponderación por cargo,
  el cierre de períodos, el código único del catálogo, el RUT, las fechas o
  los duplicados se controlan igual en la web y en la API.
- **Mismos permisos**: cada operación exige el permiso de Django del perfil
  (Administrador, Supervisor o Administrativo). Sin token responde `401`;
  sin permiso, `403`.
- **Mismo ámbito por delegación** en los compromisos: un Administrativo solo
  ve y opera los de su delegación (`403` fuera de ámbito).
- **Baja lógica**: `DELETE` deja el registro con `activo=false` y se puede
  reactivar. La única excepción es el período, que se elimina solo si no
  tiene detalles ni metas, igual que en la web.
- **Campos protegidos**: el cumplimiento y el semáforo de un compromiso no se
  editan por la API; solo cambian con el registro de avance (T2). `activo`
  solo cambia con `DELETE` o `/reactivar/`.
- **Reglas de negocio** que impiden una operación válida (ej. dar de baja una
  delegación con servicios activos o modificar un período cerrado) responden
  `409` con el motivo.

## Stack Tecnológico

- **Lenguaje:** Python 3.13
- **Framework:** Django 5.2 LTS (soporte de seguridad hasta abril de 2028)
- **API:** Django REST Framework 3.18, Simple JWT 5.5 y drf-spectacular 0.30
  (Swagger / ReDoc)
- **Servidor Web:** Nginx + Gunicorn
- **Base de Datos:** MySQL / MariaDB
- **Infraestructura:** AWS EC2 (Amazon Linux 2023)
- **Control de Versiones:** Git + GitHub

## Instalación y Despliegue Local

**Requisitos previos:** Git, Python 3.13 y un servidor MySQL 8 o MariaDB 10.5+
instalado y en ejecución (por ejemplo, MariaDB Community Server o XAMPP en
Windows).

0. Crear la base de datos y su usuario (en la consola de MySQL/MariaDB):
   ```sql
   CREATE DATABASE evaluacion_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'usuario'@'localhost' IDENTIFIED BY 'clave';
   GRANT ALL PRIVILEGES ON evaluacion_db.* TO 'usuario'@'localhost';
   -- Solo para ejecutar las pruebas (crean una base test_evaluacion_db):
   GRANT ALL PRIVILEGES ON test_evaluacion_db.* TO 'usuario'@'localhost';
   FLUSH PRIVILEGES;
   ```
1. Clonar el repositorio y entrar a la carpeta:
   ```bash
   git clone https://github.com/IgnacioF22777/Eva-Back-end.git
   cd Eva-Back-end
   ```
2. Crear y activar el entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```
3. Instalar dependencias (las mismas versiones exactas que producción):
   ```bash
   pip install -r requirements.txt
   ```
   `requirements.txt` refleja lo que corre en la EC2 (Python 3.13, Django
   5.2.19). Si el entorno tiene otra versión instalada, `manage.py check`,
   `runserver`, `migrate` y las pruebas lo advierten (`sgr.W002`), sin
   detener la aplicación.
4. Crear el archivo `.env` en la carpeta del proyecto (junto a `manage.py`):
   ```
   SECRET_KEY=tu_clave_secreta
   DB_NAME=evaluacion_db
   DB_USER=usuario
   DB_PASSWORD=clave
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DEBUG=True
   ```
   En un equipo local se usa `DEBUG=True`: con `DEBUG=False`, `runserver` no
   entrega los archivos estáticos y la página se ve sin estilos de Bootstrap.
   En el servidor de producción va `DEBUG=False` (Nginx entrega los
   estáticos). Sin las variables `EMAIL_*`, los correos de recuperación de
   contraseña se muestran en la consola en lugar de enviarse.
5. Aplicar migraciones y cargar datos:
   ```bash
   python manage.py migrate
   python manage.py import_data
   ```
6. Crear los roles y permisos base:
   ```bash
   python manage.py crear_roles
   ```
7. Crear el primer usuario (superusuario = perfil Administrador). Sin este
   paso la base no tiene usuarios y nadie puede iniciar sesión:
   ```bash
   python manage.py createsuperuser
   ```
   Desde su panel se crean los demás usuarios con RUT, delegación y perfil.
8. Ejecutar el servidor de desarrollo y abrir
   `http://127.0.0.1:8000/seguridad/login/`:
   ```bash
   python manage.py runserver
   ```

## Pruebas Automatizadas

```bash
python manage.py test
```

La suite cubre autenticación, recuperación de contraseña, permisos por perfil,
CRUD de los mantenedores, búsqueda, duplicados, baja lógica, reactivación,
semáforo, cierre de `/admin/`, las dos transacciones atómicas de la Fase 4
(incluida la reversión completa cuando falla un paso), las reglas de la
Evaluación 3 y la API RESTful. En total son **313 pruebas** en 9 archivos:

| Archivo | Pruebas | Cubre |
|---|---|---|
| `tubo_gestionAPP/tests.py` | 61 | Validadores, semáforo, compromisos, T1 y T2 |
| `tubo_gestionAPP/test_ambito_y_adjuntos.py` | 41 | Ámbito por delegación, largo de textos y archivos adjuntos (límites, extensiones bloqueadas, limpieza ante reversión y descarga protegida) |
| `seguridadAPP/tests.py` | 69 | Login, recuperación de contraseña, perfiles, usuarios y roles |
| `seguridadAPP/test_cache_compartida.py` | 5 | Bloqueo de login compartido entre workers |
| `delegacionesAPP/tests.py` | 27 | Mantenedores de delegaciones y servicios |
| `sgr_maestrosAPP/tests.py` | 13 | Búsqueda y baja lógica de las tablas maestras |
| `sgr_maestrosAPP/test_reglas_y_mantenedores.py` | 27 | Ponderaciones, días computables, Períodos y Cargos |
| `sgr_maestrosAPP/test_eva3_catalogo_metas.py` | 24 | Tipo de gestión (R5) y metas por cargo (Evaluación 3) |
| `apiAPP/tests.py` | 47 | API: tokens JWT, bloqueo por intentos, revocación, permisos por perfil, ámbito, validaciones, baja lógica y Swagger (casos CP-API-001 a 035) |

- Las pruebas usan la base configurada en `.env` (MySQL/MariaDB) y crean una
  base temporal `test_<DB_NAME>`, por eso el usuario necesita el permiso del
  paso 0 de la instalación.
- **313 pruebas en verde** el 11-11-2026 en un equipo local (Python 3.12,
  Django 5.2.19, base SQLite temporal). Falta repetirlas sobre MariaDB en el
  servidor después del despliegue.
- **266 pruebas en verde** el 06-11-2026 (commit `e097d04`), con Python 3.13
  y Django 5.2.19. La versión anterior de la suite (242 pruebas) se ejecutó
  en el servidor contra MariaDB 10.5 el 03-11-2026.
- Verificación de extremo a extremo con los tres perfiles en producción,
  ejecutada dentro de una transacción revertida para no dejar datos de prueba.

## Seguridad

- `DEBUG` se controla por variable de entorno y por defecto es `False`.
- Credenciales y secretos viven en `.env`, excluido de Git y con permisos `600`.
- Contraseñas protegidas con los hashers de Django y validadores de robustez.
- Control de acceso en el servidor con `@login_required` y
  `@permission_required`; un permiso faltante responde `403`.
- Todos los formularios POST usan `{% csrf_token %}`.
- API con tokens JWT de corta duración (30 minutos). El token deja de servir
  si la cuenta se desactiva o si cambia la contraseña, y `/api/token/`
  comparte el bloqueo de 15 minutos tras 5 intentos fallidos del login web.
- Los detalles del incidente de la llave SSH y las medidas aplicadas están en
  [`SECURITY.md`](SECURITY.md).

## Despliegue en AWS

- Instancia EC2 con Amazon Linux 2023.
- Python 3.13 (paquete `python3.13` de Amazon Linux) en el entorno virtual
  `venv313`. El Python 3.9 del sistema se conserva porque lo usa `dnf`.
- Gunicorn como servidor de aplicación sobre socket Unix.
- Nginx como proxy inverso, con `X-Real-IP` para el control de solicitudes.
- MariaDB escuchando solo en `127.0.0.1`.
- Despliegue validado con respaldo previo de la base, migraciones, recolección
  de estáticos y reinicio de Gunicorn.

## Estructura del Proyecto

| App | Contenido |
|---|---|
| `config/` | Configuración, rutas principales y comprobación de versiones (`sgr.W001`/`sgr.W002`) |
| `apiAPP` | API RESTful: serializadores, vistas `@api_view`, permisos, rutas JWT y documentación Swagger/ReDoc (sin modelos propios) |
| `delegacionesAPP` | Delegaciones y servicios; comando `import_data` (datos iniciales de `data/`) |
| `tubo_gestionAPP` | Compromisos, asignaciones (T1), avances y adjuntos (T2); ámbito por delegación y validadores de reglas de negocio |
| `sgr_maestrosAPP` | Catálogo de actividades, períodos, detalles de período (feriados y días computables) y metas |
| `seguridadAPP` | Login con RUT o correo, recuperación de contraseña, perfiles, usuarios, roles y cargos; comando `crear_roles` |
| `emergenciasTerritorialesAPP` | Modelos de zonas de riesgo, alertas y contactos de emergencia (sin interfaz propia; alcance por definir) |
| `reportesCiudadanosAPP` | Modelo de reportes ciudadanos (sin interfaz propia; alcance por definir) |
| `templates/`, `static/` | Plantillas Django y Bootstrap |
| `docs/` | Diagrama de despliegue en AWS y registro de la demostración T1 → T2 |

## Equipo (Proyecto Integrado)

| Integrante | Rol | Responsabilidades de la Evaluación 3 |
|---|---|---|
| Camilo Villalobos | Seguridad y líder | Ausencias (R9), felicitaciones y reclamos (R8), regalos para niños, semáforo por funcionario, permisos, revisión de Pull Requests |
| José Ignacio Villalobos | Desarrollo | Actividades diarias (R1–R4), puntaje «Mi matriz» (R7), tubo de trabajo, resumen de ingresos |
| Orlando Iribarren | Infraestructura | Organizaciones comunitarias y juntas de vecinos, tubo de cartas, alertas de registros sospechosos (R6), despliegue, respaldo y prueba de estrés |
| Ignacio Figueroa | Documentación | Tipo de gestión (R5), metas por cargo, tipos de atención social, carga de cargos y metas reales, puntaje del equipo (R10), informe |

Todo cambio entra a `main` por rama y Pull Request revisado por el líder.

## Autoría por Módulo (Programación Back End)

La pauta exige, para un trabajo de **dos integrantes**, un mínimo de **cuatro
mantenedores y dos transacciones**. El proyecto entrega **diez mantenedores
completos y dos transacciones atómicas**; los módulos evaluados se
distribuyen así:

| Módulo / Transacción | Responsable |
|---|---|
| Delegaciones y Servicios | Ignacio Figueroa |
| Compromisos del Tubo de Gestión | Ignacio Figueroa |
| **T1: Asignación de compromisos a delegación y servicio** | Ignacio Figueroa |
| Catálogo de Actividades | Orlando Iribarren |
| Metas y Detalles de período | Orlando Iribarren |
| **T2: Registro de avance con evidencia** | Orlando Iribarren |
| Usuarios, Roles y Perfiles (transversal) | Ignacio Figueroa y Orlando Iribarren |
| API RESTful con JWT y Swagger (`apiAPP`) | Ignacio Figueroa |

### Cobertura de la pauta

| Requisito de la pauta (2 integrantes) | Mínimo | Entregado |
|---|---|---|
| Mantenedores completos (crear, buscar, listar, modificar, eliminar) | 4 | **10** |
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
de errores de despliegue en AWS. La API RESTful (`apiAPP`) se desarrolló con
apoyo de **Claude Code**, siguiendo las guías de la asignatura (API con
`JsonResponse`, Django REST Framework con funciones, Swagger y JWT).

Las respuestas de la IA fueron **revisadas, corregidas y validadas** contra la
pauta y contra el entorno real (Python 3.13 y Django 5.2 tanto en local como en el servidor).
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
| API RESTful | "Crea una app Django con la API RESTful del proyecto, con DRF por funciones, JWT y Swagger, respetando permisos y reglas de la web" | `apiAPP`: 6 recursos más autenticación, validación con los formularios web, bloqueo de login compartido y 47 pruebas |

> En el documento técnico se incluyen los prompts completos, extractos de las
> respuestas y las capturas de la aplicación resultante.

---

*Primavera 2026*
