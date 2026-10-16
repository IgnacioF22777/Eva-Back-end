from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import PerfilUsuario, normalizar_rut, formatear_rut
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
            "11.111.111-1", "admin@laserena.cl", ["Administrador"]
        )
        cls.funcionario = crear_usuario(
            "12.345.678-5", "funcionario@laserena.cl", ["Funcionario"]
        )
        cls.inactivo = crear_usuario(
            "22.222.222-2", "inactivo@laserena.cl", ["Funcionario"], activo=False
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
        self.assertRedirects(respuesta, reverse("inicio"))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), self.funcionario.pk
        )

    def test_login_con_rut_sin_puntos(self):
        respuesta = self.login("123456785")
        self.assertRedirects(respuesta, reverse("inicio"))

    def test_login_con_correo(self):
        respuesta = self.login("FUNCIONARIO@laserena.cl")
        self.assertRedirects(respuesta, reverse("inicio"))

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
            "groups": [Group.objects.get(name="Verificador").pk],
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
        self.assertTrue(nuevo.groups.filter(name="Verificador").exists())

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
            groups=[Group.objects.get(name="Coordinador").pk],
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
            ["Coordinador"],
        )

    def test_no_puede_cambiar_sus_propios_roles(self):
        self.client.force_login(self.admin)
        datos = self.datos_usuario(
            rut="11.111.111-1",
            email="admin@laserena.cl",
            groups=[Group.objects.get(name="Consulta").pk],
        )
        del datos["password1"], datos["password2"]

        self.client.post(
            reverse("seguridad:usuario_editar", args=[self.admin.pk]), datos
        )
        self.assertTrue(self.admin.groups.filter(name="Administrador").exists())
        self.assertFalse(self.admin.groups.filter(name="Consulta").exists())

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
        permiso = self.admin.groups.get(name="Administrador").permissions.get(
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
            reverse("seguridad:rol_crear"), {"name": "funcionario"}
        )
        self.assertContains(respuesta, "Ya existe un rol con este nombre.")

    def test_no_elimina_rol_con_usuarios(self):
        self.client.force_login(self.admin)
        rol = Group.objects.get(name="Funcionario")
        self.client.post(reverse("seguridad:rol_eliminar", args=[rol.pk]))
        self.assertTrue(Group.objects.filter(pk=rol.pk).exists())

    def test_elimina_rol_sin_usuarios(self):
        self.client.force_login(self.admin)
        rol = Group.objects.get(name="Consulta")
        self.client.post(reverse("seguridad:rol_eliminar", args=[rol.pk]))
        self.assertFalse(Group.objects.filter(pk=rol.pk).exists())

    def test_formulario_de_rol_se_muestra(self):
        self.client.force_login(self.admin)
        rol = Group.objects.get(name="Coordinador")
        respuesta = self.client.get(reverse("seguridad:rol_editar", args=[rol.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Operaciones permitidas")
