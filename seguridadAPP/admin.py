from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import PerfilUsuario


User = get_user_model()


# ============================================================
# PERFIL (RUT, DELEGACIÓN, CARGO) DENTRO DEL ADMIN DE USUARIOS
# ============================================================

class PerfilUsuarioInline(admin.StackedInline):

    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = "Perfil del funcionario"


class UsuarioAdmin(UserAdmin):

    inlines = (PerfilUsuarioInline,)

    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_staff",
    )

    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "perfil__rut",
    )


admin.site.unregister(User)
admin.site.register(User, UsuarioAdmin)


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):

    list_display = (
        "rut",
        "usuario",
        "delegacion",
        "cargo",
    )

    search_fields = (
        "rut",
        "usuario__first_name",
        "usuario__last_name",
        "usuario__email",
    )

    list_filter = (
        "delegacion",
    )

    list_select_related = (
        "usuario",
        "delegacion",
    )
