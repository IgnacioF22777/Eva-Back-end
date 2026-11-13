import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


ZONA_CHILE = ZoneInfo("America/Santiago")


def normalizar_telefono(numero):
    """Deja nueve dígitos chilenos sin el prefijo internacional +56."""
    digitos = re.sub(r"\D", "", numero or "")
    if digitos.startswith("56") and len(digitos) == 11:
        digitos = digitos[2:]
    return digitos


def nombre_comparable(nombre):
    return " ".join((nombre or "").casefold().split())


def fecha_cierre_semana(fecha):
    """La actividad de lunes a domingo puede ingresarse hasta el lunes siguiente."""
    lunes_esta_semana = fecha - timedelta(days=fecha.weekday())
    return lunes_esta_semana + timedelta(days=7)


def rango_dia_chile(fecha):
    """Límites [inicio, fin) del día local (sin conversión SQL por zona)."""
    inicio = datetime.combine(fecha, time.min, tzinfo=ZONA_CHILE)
    fin = datetime.combine(fecha + timedelta(days=1), time.min, tzinfo=ZONA_CHILE)
    return inicio, fin


class RegistroActividad(models.Model):
    TIPO_VECINO = "VECINO"
    TIPO_DELEGADO = "DELEGADO"
    TIPOS_SOLICITANTE = [
        (TIPO_VECINO, "Vecino/a o usuario/a"),
        (TIPO_DELEGADO, "Delegado/a"),
    ]

    funcionario = models.ForeignKey(
        "seguridadAPP.PerfilUsuario",
        on_delete=models.PROTECT,
        related_name="actividades_registradas",
        verbose_name="Funcionario que registra",
    )
    actividad = models.ForeignKey(
        "sgr_maestrosAPP.CatalogoActividad",
        on_delete=models.PROTECT,
        related_name="registros_diarios",
        verbose_name="Actividad del catálogo",
    )
    fecha_actividad = models.DateField(verbose_name="Fecha de la actividad")
    solicitante_tipo = models.CharField(
        max_length=12,
        choices=TIPOS_SOLICITANTE,
        default=TIPO_VECINO,
        verbose_name="Tipo de solicitante",
    )
    nombre_usuario = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Nombre del usuario/a",
    )
    telefono_usuario = models.CharField(
        max_length=24,
        blank=True,
        verbose_name="Teléfono del usuario/a",
    )
    detalle = models.TextField(blank=True, max_length=1000)
    fecha_ingreso = models.DateTimeField(
        default=timezone.now,
        editable=False,
        db_index=True,
        verbose_name="Fecha y hora del ingreso",
    )
    puntua = models.BooleanField(default=False, editable=False)
    motivo_sin_puntaje = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-fecha_ingreso", "-id"]
        verbose_name = "Registro de actividad"
        verbose_name_plural = "Registros de actividades"
        indexes = [
            models.Index(fields=["funcionario", "fecha_ingreso"], name="act_func_ingreso_idx"),
            models.Index(fields=["fecha_actividad", "activo"], name="act_fecha_activo_idx"),
        ]

    def __str__(self):
        return f"{self.fecha_actividad} - {self.actividad} - {self.funcionario}"

    def tiene_datos_contacto(self):
        return bool(self.nombre_usuario.strip()) and len(normalizar_telefono(self.telefono_usuario)) == 9

    def es_gestion_del_delegado(self):
        if self.solicitante_tipo == self.TIPO_DELEGADO:
            return True

        if not self.funcionario_id:
            return False

        delegacion = self.funcionario.delegacion
        if not delegacion:
            return False

        if (
            nombre_comparable(self.nombre_usuario)
            and nombre_comparable(self.nombre_usuario) == nombre_comparable(delegacion.encargado)
        ):
            return True

        telefono = normalizar_telefono(self.telefono_usuario)
        telefonos_delegacion = (
            normalizar_telefono(delegacion.telefono),
            normalizar_telefono(delegacion.celular),
        )
        return bool(telefono and telefono in telefonos_delegacion)

    def actualizar_puntaje(self):
        """R1, R2 y R5: el puntaje se calcula, nunca se recibe del formulario."""
        if not self.activo:
            motivo = "Registro inactivo"
        elif self.es_gestion_del_delegado():
            motivo = "Otra gestión: el usuario es el delegado"
        elif not self.tiene_datos_contacto():
            motivo = "Sin nombre o teléfono válido del usuario"
        elif not self.actividad.puntua:
            motivo = "Gestión preparatoria: no suma puntaje"
        else:
            motivo = ""

        self.puntua = not bool(motivo)
        self.motivo_sin_puntaje = motivo

    def clean(self):
        super().clean()
        if not self.fecha_actividad:
            return

        hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
        if self.fecha_actividad > hoy:
            raise ValidationError({"fecha_actividad": "No puedes registrar actividades con fecha futura."})
        if hoy > fecha_cierre_semana(self.fecha_actividad):
            raise ValidationError({"fecha_actividad": "La semana de esta actividad ya está cerrada."})

    def save(self, *args, **kwargs):
        """Valida en el servidor y bloquea por funcionario para aplicar R3 sin carreras."""
        from seguridadAPP.models import PerfilUsuario

        with transaction.atomic():
            anterior = None
            if self.pk:
                anterior = type(self).objects.select_for_update().filter(pk=self.pk).first()
                if anterior:
                    if anterior.funcionario_id != self.funcionario_id:
                        raise ValidationError("No puedes cambiar el funcionario de un registro existente.")
                    if anterior.fecha_ingreso != self.fecha_ingreso:
                        raise ValidationError("La fecha de ingreso no se puede modificar.")
                    hoy = timezone.localdate(timezone.now(), timezone=ZONA_CHILE)
                    if hoy > fecha_cierre_semana(anterior.fecha_actividad):
                        raise ValidationError("Este registro ya no puede editarse: su semana está cerrada.")
            else:
                # La fecha de ingreso siempre la fija el servidor (R3).
                self.fecha_ingreso = timezone.now()

            # Bloqueo por funcionario para serializar ingresos simultáneos.
            PerfilUsuario.objects.select_for_update().get(pk=self.funcionario_id)
            self.full_clean()
            self.actualizar_puntaje()

            # Al crear o reactivar, contar los registros activos del día de ingreso.
            entra_al_cupo = self.activo and (anterior is None or not anterior.activo)
            if entra_al_cupo:
                fecha_local = timezone.localtime(self.fecha_ingreso, ZONA_CHILE).date()
                inicio, fin = rango_dia_chile(fecha_local)
                existentes = type(self).objects.filter(
                    funcionario_id=self.funcionario_id,
                    activo=True,
                    fecha_ingreso__gte=inicio,
                    fecha_ingreso__lt=fin,
                )
                if anterior is not None:
                    existentes = existentes.exclude(pk=self.pk)
                limite = getattr(settings, "MAX_INGRESOS_DIARIOS", 7)
                if existentes.count() >= limite:
                    raise ValidationError(
                        f"Ya registraste {limite} actividades ese día; el máximo diario es {limite}."
                    )

            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "puntua", "motivo_sin_puntaje"
                }
            return super().save(*args, **kwargs)
