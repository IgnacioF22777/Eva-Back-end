# Guía de instalación del SGR

Guía paso a paso para instalar el Sistema de Gestión de Resultados (SGR) en un
equipo local y en un servidor AWS EC2, actualizarlo, respaldarlo y verificarlo.

Última actualización: 21-11-2026 (incluye `.env.example`, pruebas sin MariaDB,
datos de demostración y alertas de registros sospechosos R6).

> **Nunca** escribas contraseñas reales en este documento, en el repositorio ni
> en el informe. Donde aparece `<…>` va un valor que defines tú.

| Versión | Valor |
|---|---|
| Python | 3.13 |
| Django | 5.2 LTS (ver `requirements.txt`) |
| Base de datos | MariaDB 10.5+ o MySQL 8 |
| Servidor | Amazon Linux 2023, Nginx, Gunicorn |

---

## Parte A. Instalación local (Windows, Linux o macOS)

### A1. Requisitos

- Git
- Python 3.13 (en Windows marca «Add Python to PATH» al instalar)
- MariaDB 10.5+ o MySQL 8 instalado y en ejecución
  (en Windows sirve MariaDB Community Server o XAMPP)

### A2. Base de datos

Abre la consola de MariaDB/MySQL como administrador y ejecuta:

```sql
CREATE DATABASE evaluacion_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER '<usuario>'@'localhost' IDENTIFIED BY '<clave>';
GRANT ALL PRIVILEGES ON evaluacion_db.* TO '<usuario>'@'localhost';
-- Solo para correr las pruebas (crean y borran test_evaluacion_db):
GRANT ALL PRIVILEGES ON test_evaluacion_db.* TO '<usuario>'@'localhost';
FLUSH PRIVILEGES;
```

### A3. Código y dependencias

```bash
git clone https://github.com/IgnacioF22777/Eva-Back-end.git
cd Eva-Back-end
python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate         # Linux / macOS
pip install -r requirements.txt
```

### A4. Archivo `.env`

Copia la plantilla y completa los valores marcados como «reemplazar»:

```bash
copy .env.example .env           # Windows
cp .env.example .env             # Linux / macOS
```

Como mínimo:

```
SECRET_KEY=<cadena larga y aleatoria>
DB_NAME=evaluacion_db
DB_USER=<usuario>
DB_PASSWORD=<clave>
DB_HOST=127.0.0.1
DB_PORT=3306
DEBUG=True
```

`.env.example` documenta además las variables opcionales con su valor por
defecto: adjuntos (`ADJUNTOS_*`), reglas de la matriz (`SGR_BONO_FELICITACION`,
`SGR_DESCUENTO_RECLAMO`, `SGR_TOPE_CUMPLIMIENTO`) y umbrales de las alertas R6
(`SGR_ALERTA_*`). Si no se definen, se usan esos valores.

- En local va `DEBUG=True`: con `False`, `runserver` no entrega los archivos
  estáticos y la página se ve sin estilos.
- Sin las variables `EMAIL_*`, los correos de recuperación de contraseña se
  muestran en la consola en lugar de enviarse.
- Para generar `SECRET_KEY`:
  `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`

### A5. Tablas, roles y primer usuario

```bash
python manage.py migrate
python manage.py crear_roles
python manage.py createsuperuser
```

Sin `createsuperuser` la base no tiene usuarios y nadie puede iniciar sesión.

### A6. Datos (opcionales)

```bash
# Delegaciones, servicios y compromisos de ejemplo
python manage.py import_data

# 8 cargos del descriptor y sus metas reales (matriz SGR T3 2026)
python manage.py cargar_cargos_metas --dry-run
python manage.py cargar_cargos_metas

# Registro municipal de juntas de vecinos y organizaciones (2.709)
# La planilla no está en el repositorio: pídela al equipo.
python manage.py importar_organizaciones "ruta/base datos JJVV.xlsx" --dry-run
python manage.py importar_organizaciones "ruta/base datos JJVV.xlsx"
```

Los tres comandos se pueden ejecutar varias veces sin duplicar datos.
`import_data` debe ir **antes** de `importar_organizaciones`, porque las
organizaciones se asocian a las delegaciones.

Datos de demostración (equipos ficticios en Centro y Las Compañías, con
actividades, verificación, tubo, ausencias, felicitaciones, cartas y reportes):

```bash
python manage.py cargar_datos_demo --clave "<clave de las cuentas demo>"
python manage.py cargar_datos_demo --clave "<clave>" --reiniciar   # regenera
```

Requiere haber ejecutado antes `import_data`, `cargar_cargos_metas` y
`createsuperuser`; si falta alguno, el comando lo indica sin crear nada. La
clave se escribe en la consola y no queda en el repositorio.

### A7. Ejecutar y probar

```bash
python manage.py runserver
```

Abre `http://127.0.0.1:8000/seguridad/login/` y entra con el superusuario.

```bash
python manage.py check
python manage.py test                                  # sobre MariaDB (usa el .env)
python manage.py test --settings=config.settings_pruebas   # sin MariaDB ni .env (SQLite en memoria)
```

Resultado esperado al 21-11-2026: **691 pruebas OK**.

`check` no debe mostrar advertencias `sgr.W001`/`sgr.W002`; si aparecen, las
versiones instaladas no coinciden con `requirements.txt`
(`pip install -r requirements.txt`).

---

## Parte B. Instalación en un servidor AWS EC2

### B1. Instancia

1. Lanza una instancia **Amazon Linux 2023** (t3.micro es suficiente).
2. Grupo de seguridad:
   - SSH (22): solo desde tu IP.
   - HTTP (80): desde cualquier lugar.
   - **No** abras el 3306 (MariaDB) a internet.
3. Asocia una **IP elástica** para que la dirección no cambie al reiniciar.
4. Conéctate:

```bash
ssh -i "ruta/llave.pem" ec2-user@<IP elástica>
```

### B2. Paquetes

```bash
sudo dnf update -y
sudo dnf install -y git nginx mariadb105-server mariadb105-devel \
    python3.13 python3.13-devel gcc mariadb-connector-c-devel
sudo systemctl enable --now mariadb nginx
```

El Python 3.9 del sistema no se toca: lo usa `dnf`. El proyecto usa
`python3.13` en su propio entorno virtual.

### B3. MariaDB

```bash
sudo mariadb-secure-installation
sudo mariadb
```

Dentro de la consola ejecuta el mismo SQL del paso A2. MariaDB queda escuchando
solo en `127.0.0.1`.

### B4. Código, entorno y `.env`

```bash
cd ~
git clone https://github.com/IgnacioF22777/Eva-Back-end.git
cd Eva-Back-end
python3.13 -m venv venv313
venv313/bin/pip install --upgrade pip
venv313/bin/pip install -r requirements.txt
nano .env
```

Contenido del `.env` en el servidor:

```
SECRET_KEY=<cadena larga y aleatoria, distinta de la local>
DB_NAME=evaluacion_db
DB_USER=<usuario>
DB_PASSWORD=<clave>
DB_HOST=127.0.0.1
DB_PORT=3306
DEBUG=False
ALLOWED_HOSTS=<IP elástica>,localhost,127.0.0.1

# Recuperación de contraseña por correo (SMTP)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<servidor SMTP>
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<cuenta>
EMAIL_HOST_PASSWORD=<clave de aplicación>
DEFAULT_FROM_EMAIL=SGR La Serena <cuenta>
```

```bash
chmod 600 .env
```

### B5. Preparar Django

```bash
venv313/bin/python manage.py migrate
venv313/bin/python manage.py collectstatic --noinput
venv313/bin/python manage.py crear_roles
venv313/bin/python manage.py createsuperuser
mkdir -p media && chmod 750 media
venv313/bin/python manage.py check --deploy
```

`migrate` también crea la tabla de caché compartida `sgr_cache`.
Luego carga los datos del paso A6 con `venv313/bin/python`.

### B6. Gunicorn (servicio)

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=Gunicorn - SGR
After=network.target mariadb.service

[Service]
User=ec2-user
Group=nginx
WorkingDirectory=/home/ec2-user/Eva-Back-end
ExecStart=/home/ec2-user/Eva-Back-end/venv313/bin/gunicorn --workers 3 --bind unix:/home/ec2-user/Eva-Back-end/Eva-Back-end.sock config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
systemctl status gunicorn
```

### B7. Nginx

Amazon Linux no trae el archivo `proxy_params` que usa `eva.conf`; créalo:

```bash
sudo tee /etc/nginx/proxy_params > /dev/null <<'EOF'
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
EOF
```

`X-Real-IP` es necesario: el límite de solicitudes de recuperación de
contraseña cuenta por IP del cliente.

Copia la configuración del sitio, cambia la IP en `server_name` y valida:

```bash
sudo cp ~/Eva-Back-end/eva.conf /etc/nginx/conf.d/eva.conf
sudo nano /etc/nginx/conf.d/eva.conf      # server_name <IP elástica>;
chmod 711 /home/ec2-user                   # Nginx debe poder llegar al socket y a staticfiles
sudo nginx -t && sudo systemctl reload nginx
```

### B8. Verificación

| Comprobación | Resultado esperado |
|---|---|
| `http://<IP>/seguridad/login/` | 200, página con estilos |
| `http://<IP>/admin/` | 404 (Django Admin cerrado) |
| `http://<IP>/media/` | 404 (archivos subidos no públicos) |
| `http://<IP>/phpmyadmin/` (si existe) | 403 desde internet |
| Iniciar sesión con el superusuario | Panel del Administrador |
| 5 contraseñas erróneas seguidas | El 6.º intento responde 429 |
| `systemctl is-active nginx gunicorn mariadb` | `active` × 3 |
| `http://<IP>/api/swagger/` | 200, documentación de la API |
| `http://<IP>/alertas/` sin sesión | 302 hacia el login |

### B9. HTTPS con Let's Encrypt

Let's Encrypt entrega certificados para un nombre de dominio, no para una IP
sola. Si el proyecto no tiene dominio propio se usa **sslip.io**, un servicio
DNS gratuito que traduce `44-217-180-71.sslip.io` a `44.217.180.71` sin
registrar nada.

1. En la consola de AWS, en el **Security Group** de la instancia, abrir el
   puerto **443 (HTTPS)** a `0.0.0.0/0` (el 80 debe seguir abierto: Let's
   Encrypt lo usa para validar y Nginx para redirigir).
2. Agregar el nombre en `server_name` de `/etc/nginx/conf.d/eva.conf`:

   ```nginx
   server_name 44.217.180.71 44-217-180-71.sslip.io;
   ```

3. Instalar Certbot y pedir el certificado (Certbot edita `eva.conf`, agrega
   el bloque `listen 443 ssl` y la redirección desde HTTP):

   ```bash
   sudo dnf install -y certbot python3-certbot-nginx
   sudo nginx -t && sudo systemctl reload nginx
   sudo certbot --nginx -d 44-217-180-71.sslip.io --redirect \
        -m <correo del equipo> --agree-tos --no-eff-email
   ```

4. En el `.env` del servidor:

   ```ini
   ALLOWED_HOSTS=44-217-180-71.sslip.io,44.217.180.71,localhost,127.0.0.1
   USE_HTTPS=True
   CSRF_TRUSTED_ORIGINS=https://44-217-180-71.sslip.io
   SECURE_HSTS_SECONDS=3600
   ```

5. `sudo systemctl restart gunicorn`.
6. Renovación automática (el certificado dura 90 días):

   ```bash
   sudo systemctl enable --now certbot-renew.timer
   sudo certbot renew --dry-run
   ```

| Comprobación | Resultado esperado |
|---|---|
| `https://44-217-180-71.sslip.io/seguridad/login/` | 200 con candado |
| `http://44-217-180-71.sslip.io/` | 301 hacia `https://` |
| Iniciar sesión y enviar un formulario | Funciona (sin error 403 de CSRF) |
| Cookies `sessionid` y `csrftoken` en el navegador | Marcadas como *Secure* |

Si algo falla, volver a `USE_HTTPS=False` y reiniciar Gunicorn: el sitio
sigue funcionando por HTTP.

#### Cómo quedó aplicado en el servidor (24-11-2026)

HTTPS se activó siguiendo los pasos anteriores, con estos ajustes para no
dejar el sitio inaccesible en ningún momento:

1. **Respaldo previo** de `/etc/nginx/conf.d/eva.conf` (en `/root/`) y del
   `.env` (en `~/backups/`).
2. **Certificado sin que Certbot edite Nginx**:

   ```bash
   sudo certbot certonly --nginx -d 44-217-180-71.sslip.io \
        --agree-tos --register-unsafely-without-email -n
   ```

   Así el bloque `listen 443 ssl` se escribe a mano en `eva.conf` y el puerto
   80 sigue atendiendo el sitio hasta comprobar que el 443 responde.
3. **Bloque 443** en `eva.conf`: `listen 443 ssl`, `http2 on`, el certificado
   de `/etc/letsencrypt/live/44-217-180-71.sslip.io/`,
   `include /etc/letsencrypt/options-ssl-nginx.conf`, `client_max_body_size
   30M` y las mismas `location /static/` y `location /` del puerto 80.
4. **Comprobación desde fuera** (el Security Group `launch-wizard-1` debe
   tener el 443 abierto). Recién entonces el bloque del puerto 80 se cambia a:

   ```nginx
   location / {
       return 301 https://44-217-180-71.sslip.io$request_uri;
   }
   ```

   Se conserva `location /phpmyadmin` en el puerto 80 para que el túnel SSH
   siga funcionando.
5. **`.env`** con las variables del paso 4 y reinicio de Gunicorn.
6. **Renovación**: `sudo systemctl enable --now certbot-renew.timer` y un
   script que recarga Nginx con el certificado nuevo:

   ```bash
   printf '#!/bin/sh\nsystemctl reload nginx\n' | \
       sudo tee /etc/letsencrypt/renewal-hooks/deploy/recargar-nginx.sh
   sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/recargar-nginx.sh
   sudo certbot renew --dry-run
   ```

Resultado verificado: certificado válido hasta el 22-02-2027, HTTP → 301 a
HTTPS, cookies `Secure`, HSTS de 3600 s, login con CSRF sin errores y
renovación simulada correcta.

> En la red del laboratorio, `http://44-217-180-71.sslip.io` (sin la «s»)
> puede aparecer bloqueado por el filtro de la red del instituto; por
> `https://` funciona. Desde fuera del instituto la redirección funciona normal.

---

## Parte C. Actualizar el servidor (despliegue de una versión nueva)

Siempre en este orden: el login falla si Gunicorn arranca con código nuevo
antes de aplicar las migraciones.

```bash
cd ~/Eva-Back-end
# 1. Respaldo
mkdir -p ~/backups
mariadb-dump -u <usuario> -p --single-transaction --quick --hex-blob evaluacion_db \
    > ~/backups/evaluacion_db_$(date +%Y%m%d_%H%M%S).sql
# 2. Código y dependencias
git pull --ff-only origin main
venv313/bin/pip install -r requirements.txt
#    Si la versión trae variables nuevas, agrégalas al .env (compara con .env.example)
# 3. Base de datos y estáticos
venv313/bin/python manage.py migrate
venv313/bin/python manage.py crear_roles
venv313/bin/python manage.py collectstatic --noinput
venv313/bin/python manage.py check
# 4. Recién ahora reiniciar
sudo systemctl restart gunicorn
```

Luego repite la verificación B8.

### Volver atrás

```bash
git log --oneline -5                      # elegir el commit anterior
git checkout <commit>                     # o revertir el merge en GitHub
mariadb -u <usuario> -p evaluacion_db < ~/backups/<respaldo>.sql   # solo si las migraciones dañaron datos
sudo systemctl restart gunicorn
```

---

## Parte D. Respaldo y restauración

```bash
# Respaldo
mariadb-dump -u <usuario> -p --single-transaction --quick --hex-blob evaluacion_db \
    > ~/backups/evaluacion_db_$(date +%Y%m%d_%H%M%S).sql
# Comprobar que el respaldo está completo
tail -1 ~/backups/<respaldo>.sql          # debe decir «Dump completed»
# Restaurar en una base de prueba (nunca directo sobre producción)
sudo mariadb -e "CREATE DATABASE restauracion_prueba"
mariadb -u <usuario> -p restauracion_prueba < ~/backups/<respaldo>.sql
```

Respalda también la carpeta `media/` (evidencias subidas):
`tar czf ~/backups/media_$(date +%Y%m%d).tar.gz media/`.

---

## Parte E. Cierre: cambio de contraseñas

Al terminar la evaluación, cambia **todas** las credenciales que se usaron
durante la revisión:

1. Usuarios del SGR (superusuario y cuentas de demostración): desde
   Seguridad → Usuarios → «Restablecer contraseña».
2. Usuario de MariaDB:
   `ALTER USER '<usuario>'@'localhost' IDENTIFIED BY '<clave nueva>';`
   y actualiza `DB_PASSWORD` en el `.env`.
3. `SECRET_KEY` nueva en el `.env` (cierra todas las sesiones abiertas).
4. Clave de aplicación del correo, si se compartió.
5. `sudo systemctl restart gunicorn` y repite la verificación B8.

---

## Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `Can't connect to server on '127.0.0.1'` | MariaDB/MySQL no está instalado o encendido (A1, B2). |
| Página sin estilos en local | `DEBUG=False` en el `.env` local: usa `DEBUG=True`. |
| Página sin estilos en el servidor | Falta `collectstatic` o Nginx no puede leer `staticfiles` (`chmod 711 /home/ec2-user`). |
| `400 Bad Request` | La IP o el dominio no está en `ALLOWED_HOSTS` del `.env`. |
| `502 Bad Gateway` | Gunicorn detenido: `sudo journalctl -u gunicorn -n 50`. |
| `413 Request Entity Too Large` | Falta `client_max_body_size 30M` en `eva.conf`. |
| Advertencia `sgr.W002` | Versiones distintas a `requirements.txt`: reinstala dependencias. |
| `pip` no encuentra una versión | Se está usando un Python distinto de 3.13. |
| SSH con *timeout* | La instancia está apagada o tu IP no está permitida en el grupo de seguridad. |

---

## Registro de pruebas de esta guía

La guía debe probarla una persona distinta de quien la escribió.

| Parte | Probada por | Fecha | Resultado / observaciones |
|---|---|---|---|
| A. Local (Windows) | | | |
| B. Servidor nuevo | | | |
| C. Actualización | | | |
| D. Respaldo y restauración | | | |
