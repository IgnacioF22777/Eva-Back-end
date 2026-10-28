from django.db import migrations


# Los valores se repiten aquí a propósito: una migración debe seguir
# funcionando aunque roles.py cambie en el futuro.
PERFILES = ("Administrador", "Supervisor", "Administrativo")

MAPEO = {
    "Administrador": "Administrador",
    "Coordinador": "Supervisor",
    "Delegado": "Supervisor",
    "Verificador": "Supervisor",
    "Funcionario": "Administrativo",
    "Consulta": "Administrativo",
}

OBSOLETOS = ("Coordinador", "Delegado", "Funcionario", "Verificador", "Consulta")


def aplicar(apps, schema_editor):
    """Consolida los seis roles históricos en los tres perfiles."""
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    for nombre in PERFILES:
        Group.objects.get_or_create(name=nombre)

    for usuario in User.objects.prefetch_related("groups"):
        nombres = {grupo.name for grupo in usuario.groups.all()}
        destinos = {MAPEO[nombre] for nombre in nombres if nombre in MAPEO}

        if not destinos:
            # Un superusuario sin rol debe conservar acceso total.
            if usuario.is_superuser and not (nombres & set(PERFILES)):
                usuario.groups.add(Group.objects.get(name="Administrador"))
            continue

        # Si tuviera varios roles históricos, se conserva el de mayor
        # privilegio según el orden de PERFILES.
        perfil = sorted(destinos, key=PERFILES.index)[0]

        usuario.groups.add(Group.objects.get(name=perfil))

        for nombre in OBSOLETOS:
            if nombre in nombres:
                usuario.groups.remove(Group.objects.get(name=nombre))

    # Solo se eliminan los roles históricos que quedaron sin usuarios.
    for nombre in OBSOLETOS:
        grupo = Group.objects.filter(name=nombre).first()

        if grupo is not None and not User.objects.filter(groups=grupo).exists():
            grupo.delete()


def revertir(apps, schema_editor):
    """
    Reversión aproximada: los seis roles históricos se recrean y los
    usuarios vuelven a Coordinador (Supervisor) o Funcionario
    (Administrativo). No es posible reconstruir la asignación exacta.
    """
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")

    for nombre in OBSOLETOS:
        Group.objects.get_or_create(name=nombre)

    equivalencias = {
        "Supervisor": "Coordinador",
        "Administrativo": "Funcionario",
    }

    for usuario in User.objects.prefetch_related("groups"):
        for perfil, legado in equivalencias.items():
            if usuario.groups.filter(name=perfil).exists():
                usuario.groups.remove(Group.objects.get(name=perfil))
                usuario.groups.add(Group.objects.get(name=legado))

    for nombre in ("Supervisor", "Administrativo"):
        grupo = Group.objects.filter(name=nombre).first()

        if grupo is not None and not User.objects.filter(groups=grupo).exists():
            grupo.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("seguridadAPP", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(aplicar, revertir),
    ]
