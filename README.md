# SGR — Sistema de Gestión de Resultados (Municipalidad de La Serena)

Proyecto desarrollado para las asignaturas **Programación Back End (TI3041)**
(Evaluación Sumativa #3: Aplicación Web con CRUD) y **Proyecto Integrado**
(Evaluación 3) de la carrera de Ingeniería en Informática / Analista Programador.

El caso de la Municipalidad de La Serena se usa como contexto académico: la
solución se plantea para su posterior presentación como propuesta de práctica.

> **Proyecto universitario.** No es un sistema oficial de la Municipalidad de
> La Serena ni está en uso por ella. Los datos de demostración son ficticios
> (salvo los nombres de las delegaciones, que son públicos) y el servidor AWS
> es un entorno académico de pruebas.

## Índice

- [Descripción del Proyecto](#descripción-del-proyecto)
- [Funcionalidades](#funcionalidades)
- [API RESTful (`apiAPP`)](#api-restful-apiapp)
- [Emergencias territoriales y reportes ciudadanos](#emergencias-territoriales-y-reportes-ciudadanos)
- [Exportación a Excel y PDF](#exportación-a-excel-y-pdf)
- [Stack Tecnológico](#stack-tecnológico)
- [Instalación y Despliegue Local](#instalación-y-despliegue-local)
- [Pruebas Automatizadas](#pruebas-automatizadas)
- [Seguridad](#seguridad)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Despliegue en AWS](#despliegue-en-aws)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Equipo (Proyecto Integrado)](#equipo-proyecto-integrado)
- [Autoría por Módulo (Programación Back End)](#autoría-por-módulo-programación-back-end)
- [Cuentas de Demostración](#cuentas-de-demostración)
- [Evidencia de IA](#evidencia-de-ia)

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

### Evaluación 3: verificación, tubo de seguimiento, dashboard y contraseña temporal

| Requisito de la pauta | Implementación | Ruta |
|---|---|---|
| Flujo de verificación (pendiente, aprobada, rechazada, más antecedentes) | El delegado (Supervisor) verifica los registros de su equipo; rechazar o pedir antecedentes exige observación; nadie se verifica a sí mismo | `/actividades/verificacion/` |
| Un registro aprobado no se modifica | Bloqueo en el modelo (`save`), en la edición, en la baja lógica y en el tubo | — |
| Solo suman a la meta los registros aprobados | `actividadesAPP/puntajes.py` cuenta solo `APROBADA` | `/actividades/matriz/` |
| Evidencias con control de acceso | Archivo PDF/JPG/PNG (10 MB) con nombre aleatorio; lo descargan la dueña, su delegado y el Administrador | `/actividades/<id>/evidencia/` |
| Tubo de seguimiento por delegación | Toda la delegación consulta; cada funcionario actualiza solo lo propio mientras no esté aprobado | `/actividades/tubo/` |
| Búsqueda dinámica al escribir | Por código, RUT o nombre del solicitante (`fetch` con las mismas reglas de ámbito); filtros por funcionario, fechas y estado | `/actividades/tubo/` |
| Códigos y fechas automáticos | `ACT-AAAA-000000` y fecha de ingreso los asigna el servidor | — |
| Metas automáticas | «Soluciones de ingresos al tubo» (% solucionado vs. 80 %) y «Emergencia» | `/actividades/matriz/` |
| Ausencias ajustan la meta (R9) y felicitaciones/reclamos (R8) | Integradas en «Mi matriz», puntaje del equipo y semáforo | `/puntaje-equipo/` |
| Dashboard con filtros y gráficos | Cumplimiento por funcionario con semáforo, verificación, carga de trabajo, tendencia semanal, tubo y compromisos | `/puntaje-equipo/dashboard/` |
| Contraseña temporal y cambio obligatorio | Usuario creado o restablecido por el administrador debe cambiarla en su primer ingreso (middleware) | `/seguridad/cambiar-password/` |

**Datos de demostración** (ficticios, sobre las delegaciones reales):

```bash
python manage.py cargar_datos_demo --clave "<clave de las cuentas demo>"
python manage.py cargar_datos_demo --clave "<clave>" --reiniciar   # regenera
```

Crea equipos en la Delegación Centro y en Las Compañías (un funcionario por
cargo de la matriz), el período 2026-T4 con sus metas, actividades de
octubre y noviembre con verificación y tubo, ausencias, felicitaciones,
reclamos, cartas, atenciones sociales, zonas de riesgo y reportes. La clave
nunca queda en el repositorio; una cuenta queda con contraseña temporal para
demostrar el cambio obligatorio.

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
| Zonas de riesgo | `/api/zonas-riesgo/` | `/api/zonas-riesgo/<id>/` | `/api/zonas-riesgo/<id>/reactivar/` |
| Contactos de emergencia | `/api/contactos-emergencia/` | `/api/contactos-emergencia/<id>/` | `/api/contactos-emergencia/<id>/reactivar/` |
| Reportes ciudadanos | `/api/reportes/` | `/api/reportes/<id>/` | `/api/reportes/<id>/reactivar/` |
| Avances (transacción T2) | `/api/avances/` (GET historial, POST registrar) | `/api/avances/<id>/` (PUT corregir evidencia, DELETE anular con motivo) | — |
| Derivaciones (transacción) | `/api/derivaciones/` (GET historial, POST derivar) | `/api/derivaciones/<id>/` (PUT modificar, DELETE anular) | `POST /api/reportes/<id>/resolver/` |

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

### Transacción T2 por API (`/api/avances/`)

La lógica de T2 está en `tubo_gestionAPP/transacciones.py` y la comparten la
web y la API (bloqueo `select_for_update()`, ámbito, asignación vigente,
avance que no retrocede, evidencia obligatoria, archivos y limpieza del disco
si se revierte).

- **POST** registra el avance (JSON, o `multipart/form-data` con `adjuntos`).
  Lo hace el Administrativo.
- **PUT/PATCH** corrige la evidencia o la observación del **último** avance
  vigente; el porcentaje no se corrige.
- **DELETE** anula el último avance (baja lógica, motivo obligatorio): queda
  en el historial como anulado y el cumplimiento vuelve al avance vigente
  anterior (o 0 %). Así se corrige un porcentaje mal informado sin perder
  trazabilidad. Corregir y anular lo hace el Supervisor.
- El nombre del funcionario que registró o anuló solo lo recibe el
  Administrador. El historial web marca los avances anulados con su motivo.

## Emergencias territoriales y reportes ciudadanos

Las apps `emergenciasTerritorialesAPP` y `reportesCiudadanosAPP` tienen
interfaz web (menú **Emergencias**) y API propia:

| Módulo | Web | API |
|---|---|---|
| Mantenedor 1: Zonas de riesgo | `/emergencias/zonas/` | `/api/zonas-riesgo/` |
| Mantenedor 2: Contactos de emergencia | `/emergencias/contactos/` | `/api/contactos-emergencia/` |
| Reportes ciudadanos | `/reportes/` | `/api/reportes/` |
| **Transacción: derivación del reporte** | `/reportes/<id>/` (derivar, modificar, anular, resolver) | `/api/derivaciones/` |

- **Transacción atómica** (`reportesCiudadanosAPP/transaccion.py`, la usan la
  web y la API): bloquea el reporte con `select_for_update()`, vuelve a
  comprobar el ámbito, valida que la zona y el contacto estén activos y sean
  de la delegación del reporte, deja la derivación anterior como historial y
  marca el reporte como derivado. Si un paso falla, se revierte todo.
- **Datos sensibles por perfil**: en la API, teléfono y correo de los
  contactos, coordenadas de las zonas, datos del vecino y nombre del
  funcionario que derivó solo los recibe el **Administrador**; para
  Supervisor y Administrativo esos campos no se envían.
- **Baja lógica e integridad**: los registros tienen `activo` y las
  relaciones usan `PROTECT` (antes `CASCADE`): borrar una delegación ya no
  arrastra zonas, alertas, contactos ni reportes.
- **Ámbito por delegación**: Supervisor y Administrativo solo ven y operan
  los registros de su delegación (`403` fuera de ámbito).
- **Perfiles**: el Supervisor administra zonas, contactos y reportes y
  ejecuta la transacción; el Administrativo consulta y registra reportes.
- Tras desplegar se debe ejecutar `python manage.py migrate` y
  `python manage.py crear_roles` para crear los permisos nuevos.

## Exportación a Excel y PDF

Los listados principales tienen los botones **Exportar a PDF** y **Exportar a
Excel**. El archivo contiene exactamente lo que se ve en pantalla: usa los
mismos filtros (búsqueda, estado, tipo, cargo, semáforo), los mismos permisos
y el mismo ámbito por delegación que el listado.

| Listado | Excel | PDF |
|---|---|---|
| Delegaciones | `/delegaciones/exportar/excel/` | `/delegaciones/exportar/pdf/` |
| Compromisos (tubo de gestión) | `/gestion/compromisos/exportar/excel/` | `/gestion/compromisos/exportar/pdf/` |
| Catálogo de actividades | `/maestros/catalogo/exportar/excel/` | `/maestros/catalogo/exportar/pdf/` |
| Períodos de evaluación | `/maestros/periodos/exportar/excel/` | `/maestros/periodos/exportar/pdf/` |
| Metas | `/maestros/metas/exportar/excel/` | `/maestros/metas/exportar/pdf/` |
| Mis actividades diarias | `/actividades/exportar/excel/` | `/actividades/exportar/pdf/` |

- **Excel (`openpyxl`)**: título, institución, fecha y usuario que lo genera,
  encabezados con estilo, encabezados fijos al desplazarse, filtros
  automáticos y ancho de columnas según el contenido. Números y fechas quedan
  como números y fechas (se pueden sumar y ordenar). Un texto que comienza con
  `=` se guarda como texto, no como fórmula.
- **PDF (`ReportLab`)**: encabezado con institución, fecha, usuario y filtros
  aplicados, logo municipal, título, tabla con estilo (el encabezado se repite
  en cada página) y pie de página con **«Página X de Y»** (`NumberedCanvas`).
- La lógica compartida está en `config/exportar.py`; cada app solo arma las
  columnas y las filas en su `views.py`.
- Sin sesión redirige al login; sin permiso de lectura del listado responde
  `403`. Un Administrativo exporta solo los compromisos de su delegación y
  cada funcionario solo sus propias actividades.

## Stack Tecnológico

- **Lenguaje:** Python 3.13
- **Framework:** Django 5.2 LTS (soporte de seguridad hasta abril de 2028)
- **API:** Django REST Framework 3.18, Simple JWT 5.5 y drf-spectacular 0.30
  (Swagger / ReDoc)
- **Reportes:** openpyxl 3.1 (Excel) y ReportLab 5.1 (PDF)
- **Servidor Web:** Nginx + Gunicorn
- **Base de Datos:** MySQL / MariaDB
- **Infraestructura:** AWS EC2 (Amazon Linux 2023)
- **Control de Versiones:** Git + GitHub

## Instalación y Despliegue Local

**Requisitos previos:** Git, Python 3.13 y un servidor MySQL 8 o MariaDB 10.5+
instalado y en ejecución (por ejemplo, MariaDB Community Server o XAMPP en
Windows).

> La guía detallada (instalación local, servidor EC2, actualización, respaldo
> y verificación) está en [`docs/GUIA_INSTALACION.md`](docs/GUIA_INSTALACION.md).
> Aquí va el resumen.

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
4. Crear el archivo `.env` a partir del ejemplo versionado
   [`.env.example`](.env.example), que documenta todas las variables
   (Django, base de datos, correo, adjuntos y reglas de la matriz) sin
   credenciales reales:
   ```bash
   cp .env.example .env            # Linux/Mac
   copy .env.example .env          # Windows
   ```
   Luego reemplazar como mínimo `SECRET_KEY`, `DB_USER` y `DB_PASSWORD`.
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
   Opcional (Evaluación 3): cargar los 8 cargos del descriptor de funciones y
   sus metas reales de la matriz SGR del tercer trimestre de 2026. Se puede
   ejecutar varias veces sin duplicar; `--dry-run` muestra el resultado sin
   guardar y `--periodo CODIGO` carga las metas en un período existente:
   ```bash
   python manage.py cargar_cargos_metas --dry-run
   python manage.py cargar_cargos_metas
   ```
   Opcional (Evaluación 3): importar el registro municipal de juntas de
   vecinos y organizaciones comunitarias (planilla .xlsx, 2.709 registros).
   La planilla no se versiona en el repositorio. Se puede ejecutar varias
   veces sin duplicar y no modifica organizaciones ya verificadas:
   ```bash
   python manage.py importar_organizaciones "ruta/base datos JJVV.xlsx" --dry-run
   python manage.py importar_organizaciones "ruta/base datos JJVV.xlsx"
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

Sin MariaDB ni archivo `.env` (por ejemplo, en el equipo de un evaluador),
la batería completa se ejecuta con SQLite en memoria:

```bash
python manage.py test --settings=config.settings_pruebas
```

### Último resultado registrado

**775 pruebas OK** (21-11-2026, SQLite con `config.settings_pruebas`), con
`main` más las ramas `ci/github-actions`, `feature/eva3-alertas-r6`,
`docs/mejoras-readme` y `feature/eva3-faltantes-pauta` integradas.

- Antes de esas ramas: 691 pruebas OK en `feature/eva3-alertas-r6` y
  637 OK en `main` (20-11-2026, también sobre MariaDB en la EC2).
- Desde que se integra `ci/github-actions`, GitHub Actions ejecuta la
  batería en cada Pull Request y en cada push a `main`.

> Falta repetir la batería sobre MariaDB en la EC2 después del despliegue.

La suite cubre autenticación, recuperación de contraseña, permisos por perfil,
CRUD de los mantenedores, búsqueda, duplicados, baja lógica, reactivación,
semáforo, cierre de `/admin/`, las dos transacciones atómicas de la Fase 4
(incluida la reversión completa cuando falla un paso), las reglas de la
Evaluación 3, la API RESTful y la exportación a Excel y PDF.

### Desglose por archivo (al 17-11-2026, antes de la integración Eva 3)

La tabla siguiente corresponde a `main` antes de integrar la Evaluación 3
(**329 pruebas** en 10 archivos). Las pruebas agregadas después están en
archivos nuevos como `actividadesAPP/test_verificacion_tubo.py`,
`seguridadAPP/test_password_temporal.py`, `puntajeEquipoAPP/test_dashboard.py`
y `puntajeEquipoAPP/test_datos_demo.py`, además de los `tests.py` de cada app
de la Evaluación 3.

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
| `config/test_exportar.py` | 16 | Exportación a Excel y PDF: permisos, contenido, filtros, ámbito por delegación, registros propios, listado vacío, textos con `<` o `=`, varias páginas y «Página X de Y» (casos CP-EXP-001 a 016) |

- Las pruebas usan la base configurada en `.env` (MySQL/MariaDB) y crean una
  base temporal `test_<DB_NAME>`, por eso el usuario necesita el permiso del
  paso 0 de la instalación.

**Historial de ejecuciones anteriores:**

- **586 pruebas OK** el 20-11-2026, en la rama `integracion/eva3`, antes de
  sumar la verificación, el tubo, el dashboard y la contraseña temporal.
- **329 pruebas en verde** el 17-11-2026 en un equipo local (Python 3.12,
  Django 5.2.19, base SQLite temporal), tras agregar la exportación a Excel
  y PDF.
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

## Limitaciones conocidas

Por tratarse de un entorno académico, estas mejoras quedan fuera del alcance
actual y se proponen como trabajo futuro:

- **Sin HTTPS**: el servidor de pruebas se atiende por HTTP en una IP sin
  dominio. En un despliegue real se debe instalar un certificado TLS y activar
  `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` y HSTS.
- **Historial de Git**: la llave SSH antigua sigue recuperable desde el
  historial, aunque ya fue revocada (ver [`SECURITY.md`](SECURITY.md)).
- **Integración continua**: las pruebas se ejecutan manualmente; no hay un
  flujo automático (por ejemplo, GitHub Actions) en cada Pull Request.
- **Registro de errores**: no hay una configuración `LOGGING` propia; los
  errores quedan en la salida de Gunicorn.

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
| `config/` | Configuración, rutas principales, comprobación de versiones (`sgr.W001`/`sgr.W002`) y exportación compartida a Excel y PDF (`exportar.py`) |
| `apiAPP` | API RESTful: serializadores, vistas `@api_view`, permisos, rutas JWT y documentación Swagger/ReDoc (sin modelos propios) |
| `delegacionesAPP` | Delegaciones y servicios; comando `import_data` (datos iniciales de `data/`) |
| `tubo_gestionAPP` | Compromisos, asignaciones (T1), avances y adjuntos (T2); ámbito por delegación y validadores de reglas de negocio |
| `sgr_maestrosAPP` | Catálogo de actividades, períodos, detalles de período (feriados y días computables) y metas |
| `seguridadAPP` | Login con RUT o correo, recuperación de contraseña, contraseña temporal, perfiles, usuarios, roles y cargos; comando `crear_roles` |
| `emergenciasTerritorialesAPP` | Zonas de riesgo, alertas y contactos de emergencia, con interfaz web (`/emergencias/`) y API |
| `reportesCiudadanosAPP` | Reportes ciudadanos y transacción de derivación, con interfaz web (`/reportes/`) y API |
| `actividadesAPP` | Registro diario de actividades (R1–R4), verificación, evidencias, tubo de seguimiento y «Mi matriz» (R7) |
| `matrizAPP` | Ausencias (R9), felicitaciones y reclamos (R8) y configuración de las reglas de la matriz |
| `puntajeEquipoAPP` | Puntaje del equipo (R10) y dashboard; comando `cargar_datos_demo` |
| `beneficiosAPP` | Campañas de regalos para niños e inscripción (`/regalos/`) |
| `organizacionesAPP` | Organizaciones comunitarias y juntas de vecinos; comando `importar_organizaciones` |
| `oficinaPartesAPP` | Tubo de cartas de la Oficina de Partes |
| `atencionSocialAPP` | Tipos de atención social (RC-05) |
| `templates/`, `static/` | Plantillas Django y Bootstrap |
| `tools/` | Prueba de estrés (`prueba_estres.py`) |
| `docs/` | [Guía de instalación](docs/GUIA_INSTALACION.md), [demostración y limpieza](docs/DEMOSTRACION_Y_LIMPIEZA.md) y diagrama de despliegue en AWS |

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
| Exportación de listados a Excel y PDF | Ignacio Figueroa |
| Zonas de riesgo y Contactos de emergencia (`emergenciasTerritorialesAPP`) | Orlando Iribarren |
| **Derivación de reportes ciudadanos** (`reportesCiudadanosAPP`) | Orlando Iribarren |

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
