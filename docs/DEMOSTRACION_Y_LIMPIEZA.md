# Demostración T1 → T2 y limpieza de datos

**Fecha:** 2026-11-03  
**Entorno:** producción AWS EC2 (`44.217.180.71`)  
**Aplicación:** SGR — Sistema de Gestión de Resultados

## Respaldo previo

- **Servidor:** `/home/ec2-user/backups/evaluacion_db_pre_cleanup_20261103_122559.sql`
- **Copia local:** disponible en el equipo de trabajo.
- **SHA256:** `1DF39A2D9CB013661CA7113DC4AC7687BF2603AB798F8506DCDBA55A61DE8CAA`

## Limpieza aplicada

| Entidad | Antes | Después |
|---|---:|---:|
| Delegaciones | 13 | 6 |
| Servicios | 48 | 24 |
| Compromisos activos | 9 | 4 |
| Asignaciones vigentes | 1 | 2 |
| Avances | 1 | 1 |

- **Delegaciones:** se conservaron las IDs 1–6; se eliminaron las duplicadas 7–12 y la delegación de prueba “Don Juan” (ID 13).
- **Servicios:** se conservaron las IDs 1–24; se eliminaron los duplicados 25–48.
- **Compromisos:** se conservaron las IDs 1, 2, 3 y 9; se eliminaron 4, 5, 6, 7, 8 y 11, incluidos “barrer las calles random” y el registro con texto de relleno.
- **Correos:** no se modificaron correos de usuarios ni de delegaciones. Los correos de las delegaciones duplicadas eran idénticos a los de las canónicas.
- Se verificó la integridad referencial y la ausencia de duplicados de delegación, servicio y tarea.

## Caso preparado para la revisión

- **Compromiso ID 1:** “Implementar plataforma de trámites en línea”, en **60 % (amarillo)**.
- Asignado por **T1** a **Delegación Centro / Trámites municipales**.
- Al registrar **95 %** por **T2** (con evidencia), el semáforo cambia automáticamente a **verde**.
- La prueba de T2 se ejecutó dentro de una transacción revertida: el registro de prueba no queda en la base y el compromiso permanece en **60 %** para la demostración.

## Rutas de la demostración

| Acción | Ruta |
|---|---|
| Asignación T1 | `/gestion/compromisos/1/asignar/` |
| Registro de avance T2 | `/gestion/compromisos/1/avance/` |
| Historial del compromiso | `/gestion/compromisos/1/historial/` |
| Tablero de compromisos | `/gestion/compromisos/` |

## Verificación en producción

- Inicio de sesión con los tres perfiles: **OK**.
- Ruta `/admin/`: **404**.
- Sin “barrer las calles”, sin “Don Juan” y sin duplicados visibles.
- `python manage.py check`: sin observaciones.
- Nginx y Gunicorn: **activos**.

## Credenciales

Las credenciales de demostración **no se publican en el repositorio**. Se entregan
en el manual privado de demostración y se muestran durante la revisión presencial.
