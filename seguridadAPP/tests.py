from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import PerfilUsuario, normalizar_rut, formatear_rut
from .perfiles import ADMINISTRADOR, ADMINISTRATIVO, SUPERVISOR
from .roles import sincronizar_roles


User = get_user_model()

CLAVE = "ClaveSegura#2026"


def crear_usuario(rut, email, roles=(), activo=True):
    usuario = User.objects.create_user(
        username=normalizar_rut(rut),
        email=email,
        password=CLAVE,
        first_name="Funcionario",
        last_name="Prueba",
        is_active=activo,
    )
    PerfilUsuario.objects.create(usuario=usuario, rut=normalizar_rut(rut))

    for nombre in roles:
        usuario.groups.add(Group.objects.get(name=nombre))

    return usuario


class PruebasSeguridad(TestCase):

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", [ADMINISTRADOR]
        )
        cls.funcionario = crear_usuario(
            "12.345.678-5", "funcionario@laserena.cl", [ADMINISTRATIVO]
        )
        cls.inactivo = crear_usuario(
            "22.222.222-2", "inactivo@laserena.cl", [ADMINISTRATIVO], activo=False
        )

    def setUp(self):
        cache.clear()

    def login(self, identificador, clave=CLAVE):
        return self.client.post(
            reverse("seguridad:login"),
            {"username": identificador, "password": clave},
        )

    # --- UTILIDADES DE RUT ---
    def test_normalizar_y_formatear_rut(self):
        self.assertEqual(normalizar_rut("12.345.678-k"), "12345678-K")
        self.assertEqual(formatear_rut("12345678-K"), "12.345.678-K")

    # --- LOGIN (CP-LOG-001 a CP-LOG-003) ---
    def test_login_con_rut_con_puntos(self):
        respuesta = self.login("12.345.678-5")
        self.assertRedirects(
            respuesta,
            reverse("seguridad:panel"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), self.funcionario.pk
        )

    def test_login_con_rut_sin_puntos(self):
        respuesta = self.login("123456785")
        self.assertRedirects(
            respuesta,
            reverse("seguridad:panel"),
            fetch_redirect_response=False,
        )

    def test_login_con_correo(self):
        respuesta = self.login("FUNCIONARIO@laserena.cl")
        self.assertRedirects(
            respuesta,
            reverse("seguridad:panel"),
            fetch_redirect_response=False,
        )

    def test_login_clave_incorrecta(self):
        respuesta = self.login("12.345.678-5", "otra-clave")
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(respuesta, "incorrectos")

    def test_login_usuario_inactivo(self):
        respuesta = self.login("inactivo@laserena.cl")
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bloqueo_tras_intentos_fallidos(self):
        for _ in range(5):
            self.login("12.345.678-5", "incorrecta")

        # Aunque la clave sea correcta, la cuenta queda bloqueada.
        respuesta = self.login("12.345.678-5")
        self.assertEqual(respuesta.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sesion_sin_recordar_expira_al_cerrar_navegador(self):
        self.login("12.345.678-5")
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_logout(self):
        self.client.force_login(self.funcionario)
        respuesta = self.client.post(reverse("seguridad:logout"))
        self.assertRedirects(respuesta, reverse("seguridad:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    # --- CONTROL DE ACCESO (RBAC) ---
    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self.client.get(reverse("seguridad:usuario_lista"))
        self.assertRedirects(
            respuesta,
            f"{reverse('seguridad:login')}?next={reverse('seguridad:usuario_lista')}"
        )

    def test_funcionario_no_accede_a_usuarios_ni_roles(self):
        self.client.force_login(self.funcionario)

        for nombre_url in ["usuario_lista", "usuario_crear", "rol_lista", "rol_crear"]:
            respuesta = self.client.get(reverse(f"seguridad:{nombre_url}"))
            self.assertEqual(respuesta.status_code, 403, nombre_url)

    def test_permisos_vienen_del_rol(self):
        self.assertTrue(self.admin.has_perm("auth.add_user"))
        self.assertFalse(self.funcionario.has_perm("auth.add_user"))
        self.assertTrue(self.funcionario.has_perm("tubo_gestionAPP.add_compromiso"))

    def test_administrador_accede_a_usuarios(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("seguridad:usuario_lista"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "12.345.678-5")

    # --- CRUD DE USUARIOS ---
    def datos_usuario(self, **cambios):
        datos = {
            "rut": "9.876.543-3",
            "first_name": "Ana",
            "last_name": "Rojas",
            "email": "ana.rojas@laserena.cl",
            "cargo": "Encargada territorial",
            "groups": [Group.objects.get(name=SUPERVISOR).pk],
            "password1": CLAVE,
            "password2": CLAVE,
            "is_active": "on",
        }
        datos.update(cambios)
        return datos

    def test_crear_usuario(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"), self.datos_usuario()
        )
        self.assertRedirects(respuesta, reverse("seguridad:usuario_lista"))

        nuevo = User.objects.get(email="ana.rojas@laserena.cl")
        self.assertEqual(nuevo.perfil.rut, "9876543-3")
        self.assertEqual(nuevo.username, "9876543-3")
        self.assertTrue(nuevo.check_password(CLAVE))
        self.assertTrue(nuevo.groups.filter(name=SUPERVISOR).exists())

    def test_crear_usuario_sin_perfil_es_rechazado(self):
        self.client.force_login(self.admin)

        grupo = Group.objects.create(name="Auditor")

        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"),
            self.datos_usuario(groups=[grupo.pk]),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "al menos uno de los perfiles")
        self.assertFalse(
            User.objects.filter(email="ana.rojas@laserena.cl").exists()
        )

    def test_crear_usuario_rut_invalido(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"),
            self.datos_usuario(rut="9.876.543-1"),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(User.objects.filter(email="ana.rojas@laserena.cl").exists())

    def test_crear_usuario_rut_o_correo_duplicado(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"),
            self.datos_usuario(rut="12.345.678-5"),
        )
        self.assertContains(respuesta, "Ya existe un usuario registrado con este RUT.")

        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"),
            self.datos_usuario(email="funcionario@laserena.cl"),
        )
        self.assertContains(respuesta, "Ya existe un usuario registrado con este correo.")

    def test_crear_usuario_contrasena_debil(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("seguridad:usuario_crear"),
            self.datos_usuario(password1="123", password2="123"),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(User.objects.filter(email="ana.rojas@laserena.cl").exists())

    def test_editar_usuario_y_cambiar_rol(self):
        self.client.force_login(self.admin)
        datos = self.datos_usuario(
            rut="12.345.678-5",
            email="funcionario@laserena.cl",
            groups=[Group.objects.get(name=SUPERVISOR).pk],
        )
        del datos["password1"], datos["password2"]

        respuesta = self.client.post(
            reverse("seguridad:usuario_editar", args=[self.funcionario.pk]), datos
        )
        self.assertRedirects(respuesta, reverse("seguridad:usuario_lista"))

        self.funcionario.refresh_from_db()
        self.assertEqual(self.funcionario.first_name, "Ana")
        self.assertEqual(
            list(self.funcionario.groups.values_list("name", flat=True)),
            [SUPERVISOR],
        )

    def test_no_puede_cambiar_sus_propios_roles(self):
        self.client.force_login(self.admin)
        datos = self.datos_usuario(
            rut="11.111.111-1",
            email="admin@laserena.cl",
            groups=[Group.objects.get(name=ADMINISTRATIVO).pk],
        )
        del datos["password1"], datos["password2"]

        self.client.post(
            reverse("seguridad:usuario_editar", args=[self.admin.pk]), datos
        )
        self.assertTrue(self.admin.groups.filter(name=ADMINISTRADOR).exists())
        self.assertFalse(self.admin.groups.filter(name=ADMINISTRATIVO).exists())

    def test_desactivar_usuario(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("seguridad:usuario_cambiar_estado", args=[self.funcionario.pk])
        )
        self.funcionario.refresh_from_db()
        self.assertFalse(self.funcionario.is_active)

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("seguridad:usuario_cambiar_estado", args=[self.admin.pk])
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_restablecer_contrasena(self):
        self.client.force_login(self.admin)
        nueva = "OtraClave#Segura99"
        self.client.post(
            reverse("seguridad:usuario_password", args=[self.funcionario.pk]),
            {"new_password1": nueva, "new_password2": nueva},
        )
        self.funcionario.refresh_from_db()
        self.assertTrue(self.funcionario.check_password(nueva))

    def test_eliminar_usuario(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("seguridad:usuario_eliminar", args=[self.inactivo.pk])
        )
        self.assertRedirects(respuesta, reverse("seguridad:usuario_lista"))
        self.assertFalse(User.objects.filter(pk=self.inactivo.pk).exists())

    def test_admin_no_superusuario_no_modifica_superusuario(self):
        superusuario = User.objects.create_superuser(
            "root", "root@laserena.cl", CLAVE
        )
        self.client.force_login(self.admin)
        respuesta = self.client.get(
            reverse("seguridad:usuario_editar", args=[superusuario.pk])
        )
        self.assertEqual(respuesta.status_code, 403)

    # --- CRUD DE ROLES ---
    def test_crear_rol_con_permisos(self):
        self.client.force_login(self.admin)
        permiso = self.admin.groups.get(name=ADMINISTRADOR).permissions.get(
            codename="view_user"
        )
        respuesta = self.client.post(
            reverse("seguridad:rol_crear"),
            {"name": "Auditor", "permissions": [permiso.pk]},
        )
        self.assertRedirects(respuesta, reverse("seguridad:rol_lista"))
        self.assertTrue(
            Group.objects.get(name="Auditor").permissions.filter(pk=permiso.pk).exists()
        )

    def test_rol_nombre_duplicado(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse("seguridad:rol_crear"), {"name": "administrativo"}
        )
        self.assertContains(respuesta, "Ya existe un rol con este nombre.")

    def test_no_elimina_rol_con_usuarios(self):
        self.client.force_login(self.admin)
        rol = Group.objects.get(name=ADMINISTRATIVO)
        self.client.post(reverse("seguridad:rol_eliminar", args=[rol.pk]))
        self.assertTrue(Group.objects.filter(pk=rol.pk).exists())

    def test_elimina_rol_sin_usuarios(self):
        self.client.force_login(self.admin)
        rol = Group.objects.create(name="Rol temporal")
        self.client.post(reverse("seguridad:rol_eliminar", args=[rol.pk]))
        self.assertFalse(Group.objects.filter(pk=rol.pk).exists())

    def test_formulario_de_rol_se_muestra(self):
        self.client.force_login(self.admin)
        rol = Group.objects.get(name=SUPERVISOR)
        respuesta = self.client.get(reverse("seguridad:rol_editar", args=[rol.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Operaciones permitidas")


class PruebasPerfilesYPaneles(TestCase):
    """Cada perfil solo puede abrir su propio panel."""

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.admin = crear_usuario(
            "11.111.111-1", "admin@laserena.cl", [ADMINISTRADOR]
        )
        cls.supervisor = crear_usuario(
            "12.345.678-5", "supervisor@laserena.cl", [SUPERVISOR]
        )
        cls.administrativo = crear_usuario(
            "22.222.222-2", "administrativo@laserena.cl", [ADMINISTRATIVO]
        )
        cls.sin_perfil = User.objects.create_user(
            username="33333333-3",
            email="sinperfil@laserena.cl",
            password=CLAVE,
        )

    def setUp(self):
        cache.clear()

    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self.client.get(reverse("seguridad:panel"))
        self.assertRedirects(
            respuesta,
            f"{reverse('seguridad:login')}?next={reverse('seguridad:panel')}",
        )

    def test_panel_redirige_al_panel_del_perfil(self):
        casos = [
            (self.admin, "panel_administrador"),
            (self.supervisor, "panel_supervisor"),
            (self.administrativo, "panel_administrativo"),
        ]

        for usuario, nombre_url in casos:
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse("seguridad:panel"))
            self.assertRedirects(
                respuesta,
                reverse(f"seguridad:{nombre_url}"),
                fetch_redirect_response=False,
            )

    def test_cada_perfil_ve_su_propio_panel(self):
        casos = [
            (self.admin, "panel_administrador", "Resumen general del sistema"),
            (self.supervisor, "panel_supervisor", "Supervisión operativa"),
            (self.administrativo, "panel_administrativo", "Mi espacio de trabajo"),
        ]

        for usuario, nombre_url, texto in casos:
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse(f"seguridad:{nombre_url}"))
            self.assertEqual(respuesta.status_code, 200, nombre_url)
            self.assertContains(respuesta, texto)

    def test_no_puede_abrir_el_panel_de_otro_perfil(self):
        casos = [
            (self.supervisor, ["panel_administrador", "panel_administrativo"]),
            (self.administrativo, ["panel_administrador", "panel_supervisor"]),
            (self.admin, ["panel_supervisor", "panel_administrativo"]),
        ]

        for usuario, paneles_ajenos in casos:
            self.client.force_login(usuario)

            for nombre_url in paneles_ajenos:
                respuesta = self.client.get(reverse(f"seguridad:{nombre_url}"))
                self.assertEqual(respuesta.status_code, 403, nombre_url)

    def test_usuario_sin_perfil_no_entra_al_panel(self):
        self.client.force_login(self.sin_perfil)
        respuesta = self.client.get(reverse("seguridad:panel"))
        self.assertEqual(respuesta.status_code, 403)

    def test_superusuario_es_administrador(self):
        superusuario = User.objects.create_superuser(
            "root", "root@laserena.cl", CLAVE
        )
        self.client.force_login(superusuario)
        respuesta = self.client.get(reverse("seguridad:panel_administrador"))
        self.assertEqual(respuesta.status_code, 200)

    def test_vistas_operativas_requieren_sesion(self):
        from delegacionesAPP.models import Delegacion

        delegacion = Delegacion.objects.create(
            nombre="Delegación Centro",
            direccion="Av. Principal 123",
            encargado="Encargado",
            email="centro@laserena.cl",
            telefono="512345678",
            celular="912345678",
        )

        urls_privadas = [
            reverse("inicio"),
            reverse("lista"),
            reverse("tablero_metas"),
            reverse("seguridad:usuario_lista"),
        ]

        for url in urls_privadas:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertIn(reverse("seguridad:login"), respuesta["Location"])

        self.assertTrue(delegacion.pk)

    def test_menu_no_muestra_seguridad_al_administrativo(self):
        self.client.force_login(self.administrativo)
        respuesta = self.client.get(reverse("seguridad:panel_administrativo"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Gestión de Usuarios")

    def test_menu_muestra_seguridad_al_administrador(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("seguridad:usuario_lista"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Gestión de Usuarios")

    def test_administrador_accede_a_las_tablas_maestras(self):
        self.client.force_login(self.admin)

        for nombre_url in ["catalogo_lista", "periodo_lista", "meta_lista"]:
            respuesta = self.client.get(reverse(f"sgr_maestros:{nombre_url}"))
            self.assertEqual(respuesta.status_code, 200, nombre_url)

    def test_administrativo_solo_consulta_las_tablas_maestras(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(reverse("sgr_maestros:catalogo_lista"))
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(reverse("sgr_maestros:catalogo_crear"))
        self.assertEqual(respuesta.status_code, 403)

    def test_supervisor_puede_crear_actividad(self):
        self.client.force_login(self.supervisor)

        respuesta = self.client.get(reverse("sgr_maestros:catalogo_crear"))
        self.assertEqual(respuesta.status_code, 200)


class PruebasRecuperacionPassword(TestCase):
    """
    Fase 2: recuperación de contraseña con el flujo nativo de Django.
    """

    NUEVA_CLAVE = "NuevaClave#2026"

    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

        cls.usuario = crear_usuario(
            "12.345.678-5", "funcionario@laserena.cl", [ADMINISTRATIVO]
        )
        cls.inactivo = crear_usuario(
            "22.222.222-2", "inactivo@laserena.cl", [ADMINISTRATIVO], activo=False
        )

    def setUp(self):
        cache.clear()
        mail.outbox = []

    # --- UTILIDADES ---
    def solicitar(self, email="funcionario@laserena.cl"):
        return self.client.post(
            reverse("seguridad:password_reset"), {"email": email}
        )

    def enlace_del_correo(self):
        """Extrae la ruta del enlace de recuperación del último correo."""
        cuerpo = mail.outbox[-1].body

        for palabra in cuerpo.split():
            if "/password-reset/" in palabra:
                return urlparse(palabra).path

        self.fail("El correo no contiene un enlace de recuperación.")

    def abrir_formulario(self):
        """Solicita el correo, sigue el enlace y devuelve el formulario."""
        if not mail.outbox:
            self.solicitar()

        enlace = self.enlace_del_correo()

        respuesta = self.client.get(enlace)
        self.assertEqual(respuesta.status_code, 302, enlace)

        destino = respuesta["Location"]
        respuesta = self.client.get(destino)

        self.assertEqual(respuesta.status_code, 200, destino)

        return destino, respuesta

    # --- FORMULARIO ---
    def test_el_login_ofrece_el_enlace_de_recuperacion(self):
        respuesta = self.client.get(reverse("seguridad:login"))
        self.assertContains(respuesta, "¿Olvidó su contraseña?")
        self.assertContains(respuesta, reverse("seguridad:password_reset"))

    def test_formulario_de_recuperacion_se_muestra(self):
        respuesta = self.client.get(reverse("seguridad:password_reset"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Correo institucional")

    # --- ENVÍO DEL CORREO ---
    def test_envia_correo_con_enlace_a_usuario_existente(self):
        respuesta = self.solicitar()

        self.assertRedirects(
            respuesta, reverse("seguridad:password_reset_done")
        )
        self.assertEqual(len(mail.outbox), 1)

        correo = mail.outbox[0]
        self.assertIn("funcionario@laserena.cl", correo.to)
        self.assertIn("Municipalidad de La Serena", correo.body)
        self.assertIn("/password-reset/", correo.body)
        # El correo incluye versión HTML con el botón de validación.
        self.assertEqual(len(correo.alternatives), 1)
        self.assertIn("Validar y cambiar contraseña", correo.alternatives[0][0])

    def test_correo_inexistente_no_envia_ni_revela(self):
        respuesta = self.solicitar("nadie@laserena.cl")

        self.assertRedirects(
            respuesta, reverse("seguridad:password_reset_done")
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_usuario_inactivo_no_recibe_correo(self):
        self.solicitar("inactivo@laserena.cl")
        self.assertEqual(len(mail.outbox), 0)

    def test_correo_vacio_es_rechazado(self):
        respuesta = self.solicitar("")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    # --- CAMBIO DE CONTRASEÑA ---
    def test_el_enlace_muestra_el_boton_de_validar(self):
        _, respuesta = self.abrir_formulario()
        self.assertContains(respuesta, "Validar y cambiar contraseña")

    def test_el_enlace_permite_cambiar_la_contrasena(self):
        destino, _ = self.abrir_formulario()

        respuesta = self.client.post(destino, {
            "new_password1": self.NUEVA_CLAVE,
            "new_password2": self.NUEVA_CLAVE,
        })

        self.assertRedirects(
            respuesta, reverse("seguridad:password_reset_complete")
        )

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(self.NUEVA_CLAVE))

        # La contraseña nueva sirve para iniciar sesión.
        self.assertTrue(
            self.client.login(
                username="12.345.678-5", password=self.NUEVA_CLAVE
            )
        )

    def test_el_enlace_no_sirve_dos_veces(self):
        destino, _ = self.abrir_formulario()

        self.client.post(destino, {
            "new_password1": self.NUEVA_CLAVE,
            "new_password2": self.NUEVA_CLAVE,
        })

        enlace = self.enlace_del_correo()
        respuesta = self.client.get(enlace)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El enlace no es válido")

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_el_enlace_vencido_no_sirve(self):
        self.solicitar()
        enlace = self.enlace_del_correo()

        respuesta = self.client.get(enlace)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El enlace no es válido")

    def test_contrasena_debil_es_rechazada(self):
        destino, _ = self.abrir_formulario()

        respuesta = self.client.post(destino, {
            "new_password1": "123",
            "new_password2": "123",
        })

        self.assertEqual(respuesta.status_code, 200)

        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.check_password("123"))
        self.assertTrue(self.usuario.check_password(CLAVE))

    # --- LÍMITE DE SOLICITUDES ---
    def test_bloquea_tras_cinco_solicitudes(self):
        for _ in range(5):
            self.solicitar()

        respuesta = self.solicitar()

        self.assertEqual(respuesta.status_code, 429)
        self.assertContains(
            respuesta, "demasiados enlaces de recuperación", status_code=429
        )
