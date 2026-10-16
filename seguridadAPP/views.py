from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import (
    LoginForm,
    UsuarioForm,
    RestablecerPasswordForm,
    RolForm,
)
from .models import normalizar_rut


User = get_user_model()

MAX_INTENTOS_LOGIN = 5
MINUTOS_BLOQUEO = 15


# ============================================================
# INICIO DE SESIÓN (RUT O CORREO)
# ============================================================

def clave_intentos(identificador):
    identificador = (identificador or "").strip().lower()

    if identificador and "@" not in identificador:
        identificador = normalizar_rut(identificador)

    return f"login_intentos:{identificador}"


class IniciarSesionView(LoginView):
    """
    Login con RUT o correo. Tras MAX_INTENTOS_LOGIN intentos fallidos
    la cuenta queda bloqueada temporalmente para frenar ataques de
    fuerza bruta.
    """

    template_name = "seguridad/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        clave = clave_intentos(request.POST.get("username"))

        if cache.get(clave, 0) >= MAX_INTENTOS_LOGIN:
            # No se valida el formulario: así ni siquiera se comprueba
            # la contraseña mientras dure el bloqueo.
            form = self.get_form_class()(
                self.request,
                initial={"username": request.POST.get("username", "")}
            )
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    error_bloqueo=(
                        "Demasiados intentos fallidos. Intente "
                        f"nuevamente en {MINUTOS_BLOQUEO} minutos."
                    )
                ),
                status=429
            )

        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        cache.delete(clave_intentos(form.cleaned_data.get("username")))

        respuesta = super().form_valid(form)

        # Sin "recordar sesión", la sesión termina al cerrar el navegador.
        if not form.cleaned_data.get("recordar"):
            self.request.session.set_expiry(0)

        return respuesta

    def form_invalid(self, form):
        clave = clave_intentos(self.request.POST.get("username"))
        cache.set(clave, cache.get(clave, 0) + 1, MINUTOS_BLOQUEO * 60)

        return super().form_invalid(form)


# ============================================================
# CRUD 1: USUARIOS
# ============================================================

def verificar_puede_gestionar(editor, usuario):
    """Solo un superusuario puede modificar a otro superusuario."""
    if usuario.is_superuser and not editor.is_superuser:
        raise PermissionDenied(
            "No tiene permisos para modificar a este usuario."
        )


@login_required
@permission_required("auth.view_user", raise_exception=True)
def usuario_lista(request):
    usuarios = User.objects.select_related(
        "perfil",
        "perfil__delegacion",
    ).prefetch_related(
        "groups"
    ).order_by(
        "last_name",
        "first_name",
    )

    busqueda = request.GET.get("q", "").strip()
    rol = request.GET.get("rol", "")
    estado = request.GET.get("estado", "")

    if busqueda:
        usuarios = usuarios.filter(
            Q(first_name__icontains=busqueda)
            | Q(last_name__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(username__icontains=busqueda)
            | Q(perfil__rut__icontains=normalizar_rut(busqueda))
        ).distinct()

    if rol:
        usuarios = usuarios.filter(groups__pk=rol)

    if estado == "activos":
        usuarios = usuarios.filter(is_active=True)
    elif estado == "inactivos":
        usuarios = usuarios.filter(is_active=False)

    return render(
        request,
        "seguridad/usuario_lista.html",
        {
            "usuarios": usuarios,
            "roles": Group.objects.order_by("name"),
            "busqueda": busqueda,
            "rol_seleccionado": rol,
            "estado": estado,
        }
    )


@login_required
@permission_required("auth.add_user", raise_exception=True)
def usuario_crear(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST, editor=request.user)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Usuario registrado correctamente."
            )
            return redirect("seguridad:usuario_lista")
    else:
        form = UsuarioForm(editor=request.user)

    return render(
        request,
        "seguridad/usuario_form.html",
        {
            "form": form,
            "titulo": "Registrar usuario",
        }
    )


@login_required
@permission_required("auth.change_user", raise_exception=True)
def usuario_editar(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    verificar_puede_gestionar(request.user, usuario)

    if request.method == "POST":
        form = UsuarioForm(
            request.POST,
            instance=usuario,
            editor=request.user
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Usuario actualizado correctamente."
            )
            return redirect("seguridad:usuario_lista")
    else:
        form = UsuarioForm(instance=usuario, editor=request.user)

    return render(
        request,
        "seguridad/usuario_form.html",
        {
            "form": form,
            "titulo": "Editar usuario",
            "usuario_editado": usuario,
        }
    )


@login_required
@permission_required("auth.change_user", raise_exception=True)
def usuario_password(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    verificar_puede_gestionar(request.user, usuario)

    if request.method == "POST":
        form = RestablecerPasswordForm(usuario, request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Contraseña restablecida correctamente."
            )
            return redirect("seguridad:usuario_lista")
    else:
        form = RestablecerPasswordForm(usuario)

    return render(
        request,
        "seguridad/usuario_password.html",
        {
            "form": form,
            "usuario_editado": usuario,
        }
    )


@login_required
@permission_required("auth.change_user", raise_exception=True)
@require_POST
def usuario_cambiar_estado(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    verificar_puede_gestionar(request.user, usuario)

    if usuario.pk == request.user.pk:
        messages.error(
            request,
            "No puede desactivar su propia cuenta."
        )
        return redirect("seguridad:usuario_lista")

    # Baja lógica: el usuario se conserva para mantener su historial.
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])

    messages.success(
        request,
        "Estado del usuario actualizado correctamente."
    )

    return redirect("seguridad:usuario_lista")


@login_required
@permission_required("auth.delete_user", raise_exception=True)
def usuario_eliminar(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    verificar_puede_gestionar(request.user, usuario)

    if usuario.pk == request.user.pk:
        messages.error(
            request,
            "No puede eliminar su propia cuenta."
        )
        return redirect("seguridad:usuario_lista")

    if request.method == "POST":
        usuario.delete()
        messages.success(
            request,
            "Usuario eliminado correctamente."
        )
        return redirect("seguridad:usuario_lista")

    return render(
        request,
        "seguridad/confirmar_eliminar.html",
        {
            "objeto": usuario.get_full_name() or usuario.username,
            "tipo": "usuario",
            "aviso": (
                "Se recomienda desactivar el usuario en lugar de "
                "eliminarlo, para conservar su historial."
            ),
            "url_cancelar": "seguridad:usuario_lista",
        }
    )


# ============================================================
# CRUD 2: ROLES (GRUPOS Y PERMISOS)
# ============================================================

@login_required
@permission_required("auth.view_group", raise_exception=True)
def rol_lista(request):
    roles = Group.objects.annotate(
        total_usuarios=Count("user", distinct=True),
        total_permisos=Count("permissions", distinct=True),
    ).order_by("name")

    return render(
        request,
        "seguridad/rol_lista.html",
        {"roles": roles}
    )


@login_required
@permission_required("auth.add_group", raise_exception=True)
def rol_crear(request):
    if request.method == "POST":
        form = RolForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Rol registrado correctamente."
            )
            return redirect("seguridad:rol_lista")
    else:
        form = RolForm()

    return render(
        request,
        "seguridad/rol_form.html",
        {
            "form": form,
            "titulo": "Registrar rol",
        }
    )


@login_required
@permission_required("auth.change_group", raise_exception=True)
def rol_editar(request, pk):
    rol = get_object_or_404(Group, pk=pk)

    if request.method == "POST":
        form = RolForm(request.POST, instance=rol)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Rol actualizado correctamente."
            )
            return redirect("seguridad:rol_lista")
    else:
        form = RolForm(instance=rol)

    return render(
        request,
        "seguridad/rol_form.html",
        {
            "form": form,
            "titulo": f"Editar rol: {rol.name}",
        }
    )


@login_required
@permission_required("auth.delete_group", raise_exception=True)
def rol_eliminar(request, pk):
    rol = get_object_or_404(Group, pk=pk)

    # Igual que con los cargos: no se elimina un rol en uso.
    if rol.user_set.exists():
        messages.error(
            request,
            "No es posible eliminar el rol porque tiene "
            "usuarios asignados."
        )
        return redirect("seguridad:rol_lista")

    if request.method == "POST":
        rol.delete()
        messages.success(
            request,
            "Rol eliminado correctamente."
        )
        return redirect("seguridad:rol_lista")

    return render(
        request,
        "seguridad/confirmar_eliminar.html",
        {
            "objeto": rol.name,
            "tipo": "rol",
            "url_cancelar": "seguridad:rol_lista",
        }
    )
