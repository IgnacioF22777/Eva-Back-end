# Evaluación Sumativa #2: Aplicación Web con Django Admin

Proyecto desarrollado para la asignatura **Programación Back End (TI3041)**.

## Descripción del Proyecto
Este proyecto es una plataforma web modular diseñada para la gestión de delegaciones municipales y el seguimiento de compromisos operativos mediante un "Tubo de Gestión". La aplicación ha sido evolucionada desde un prototipo basado en archivos JSON hacia una arquitectura profesional con persistencia en base de datos relacional (MySQL).

## Características Principales
*   **Backend:** Django Framework.
*   **Base de Datos:** MySQL (con migración de datos desde JSON).
*   **Persistencia:** Gestión completa mediante Django ORM.
*   **Administración:** Panel Django Admin configurado para operaciones CRUD completas (Crear, Leer, Actualizar, Eliminar).
*   **Seguridad:** Implementación de variables de entorno mediante `.env`.
*   **Despliegue:** Desplegado en AWS EC2 (Linux/Nginx/Gunicorn).
*   **Control de Versiones:** Repositorio en GitHub con historial de desarrollo.

## Stack Tecnológico
*   **Lenguaje:** Python 3.9+
*   **Framework:** Django 4.2
*   **Servidor Web:** Nginx + Gunicorn
*   **Base de Datos:** MySQL / MariaDB
*   **Infraestructura:** AWS EC2 (Amazon Linux 2023)

## Instalación y Despliegue Local
1. Clonar el repositorio:
   `git clone https://github.com/IgnacioF22777/Eva-Back-end.git`
2. Crear entorno virtual:
   `python -m venv venv`
   `source venv/bin/activate` (Linux/Mac) o `venv\Scripts\activate` (Windows)
3. Instalar dependencias:
   `pip install -r requirements.txt`
4. Configurar variables de entorno (crear archivo `.env`):
   ```
   SECRET_KEY=tu_clave_secreta
   DB_NAME=evaluacion_db
   DB_USER=root
   DB_PASSWORD=
   DB_HOST=127.0.0.1
   DB_PORT=3306
   ```
5. Aplicar migraciones e importar datos:
   `python manage.py migrate`
   `python manage.py import_data`

## Evidencia de IA
Este proyecto ha sido desarrollado con el apoyo de herramientas de IA (OpenCode/Gemini) para la estructuración de la arquitectura, resolución de errores de despliegue en AWS, configuración de variables de entorno y optimización del panel administrativo.

---
*Desarrollado por: [Nombre Estudiante]*
*Primavera 2026*
