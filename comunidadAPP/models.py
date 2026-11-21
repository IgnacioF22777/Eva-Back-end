from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from actividadesAPP.models import normalizar_telefono
from delegacionesAPP.models import Delegacion
from organizacionesAPP.models import OrganizacionComunitaria, normalizar
from seguridadAPP.models import formatear_rut, normalizar_rut
from tubo_gestionAPP.validadores import validar_rut_chileno


MAX_DESCRIPCION = 1000


# ============================================================
# TERRITORIO
# ============================================================
# Unidad vecinal, sector o villa dentro de una delegación. Agrupa a los
# vecinos, las juntas de vecinos y los hitos de la delegación.

class Territorio(models.Model):

    nombre = models.CharField(max_length=150, verbose_name="Nombre del territorio")

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="territorios",
        verbose_name="Delegación",
    )

    descripcion = models.TextField(
        blank=True,
        max_length=MAX_DESCRIPCION,
        validators=[MaxLengthValidator(MAX_DESCRIPCION)],
        verbose_name="Descripción o límites",
    )

    # Baja lógica.
    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Territorio"
        verbose_name_plural = "Territorios"
        ordering = ["delegacion__nombre", "nombre"]
        indexes = [
            models.Index(fields=["delegacion", "activo"], name="ter_delegacion_activo_idx"),
        ]

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        self.nombre = " ".join((self.nombre or "").split())

        if not self.nombre:
            raise ValidationError({"nombre": "El nombre es obligatorio."})

        if self.delegacion_id:
            repetidos = Territorio.objects.filter(
                delegacion_id=self.delegacion_id, activo=True
            ).exclude(pk=self.pk)
            if any(normalizar(t.nombre) == normalizar(self.nombre) for t in repetidos):
                raise ValidationError({
                    "nombre": "Ya existe un territorio vigente con este nombre en la delegación."
                })


# ============================================================
# VECINO
# ============================================================
# Registro único de cada vecino o vecina. Sus datos se reutilizan para
# autocompletar actividades y atenciones sociales (sin volver a escribirlos)
# y para registrar su membresía o dirigencia en las juntas de vecinos.

class Vecino(models.Model):

    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")

    nombre = models.CharField(max_length=150, verbose_name="Nombre completo")

    telefono = models.CharField(max_length=20, verbose_name="Teléfono")

    correo = models.EmailField(max_length=100, blank=True, verbose_name="Correo electrónico")

    direccion = models.CharField(max_length=255, blank=True, verbose_name="Dirección")

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="vecinos",
        verbose_name="Delegación",
    )

    territorio = models.ForeignKey(
        Territorio,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vecinos",
        verbose_name="Territorio",
    )

    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de registro")

    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Vecino/a"
        verbose_name_plural = "Vecinos/as"
        ordering = ["nombre"]
        indexes = [
            models.Index(fields=["delegacion", "activo"], name="vec_delegacion_activo_idx"),
            models.Index(fields=["nombre"], name="vec_nombre_idx"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.rut_formateado})"

    @property
    def rut_formateado(self):
        return formatear_rut(self.rut)

    def clean(self):
        super().clean()
        self.rut = normalizar_rut(self.rut)
        self.nombre = " ".join((self.nombre or "").split())
        self.telefono = (self.telefono or "").strip()

        try:
            validar_rut_chileno(self.rut)
        except ValidationError as error:
            raise ValidationError({"rut": error.messages})

        if not self.nombre:
            raise ValidationError({"nombre": "El nombre es obligatorio."})

        # Mismo criterio que la regla de puntaje de las actividades (R2):
        # nueve dígitos chilenos, con o sin +56.
        if len(normalizar_telefono(self.telefono)) != 9:
            raise ValidationError({"telefono": "Ingrese un teléfono chileno de 9 dígitos (con o sin +56)."})

        if self.territorio_id and self.delegacion_id and self.territorio.delegacion_id != self.delegacion_id:
            raise ValidationError({"territorio": "El territorio no pertenece a la delegación indicada."})

    def save(self, *args, **kwargs):
        self.rut = normalizar_rut(self.rut)
        super().save(*args, **kwargs)


# ============================================================
# MEMBRESÍA Y DIRIGENCIA EN JUNTAS DE VECINOS
# ============================================================
# Relación vecino <-> organización. Un vecino es socio de una junta y,
# además, puede integrar su directiva con un cargo (presidente,
# secretario, tesorero...). Al terminar el período la membresía se cierra
# con fecha de término: queda como historial y no se borra.

class MembresiaJunta(models.Model):

    SOCIO = "SOCIO"
    DIRIGENTE = "DIRIGENTE"
    TIPOS = [
        (SOCIO, "Socio/a"),
        (DIRIGENTE, "Dirigente (directiva)"),
    ]

    PRESIDENTE = "PRESIDENTE"
    VICEPRESIDENTE = "VICEPRESIDENTE"
    SECRETARIO = "SECRETARIO"
    TESORERO = "TESORERO"
    DIRECTOR = "DIRECTOR"
    CARGOS = [
        (PRESIDENTE, "Presidente/a"),
        (VICEPRESIDENTE, "Vicepresidente/a"),
        (SECRETARIO, "Secretario/a"),
        (TESORERO, "Tesorero/a"),
        (DIRECTOR, "Director/a"),
    ]
    # Cargos que solo puede ocupar una persona a la vez en cada organización.
    CARGOS_UNICOS = (PRESIDENTE, VICEPRESIDENTE, SECRETARIO, TESORERO)

    vecino = models.ForeignKey(
        Vecino,
        on_delete=models.PROTECT,
        related_name="membresias",
        verbose_name="Vecino/a",
    )

    organizacion = models.ForeignKey(
        OrganizacionComunitaria,
        on_delete=models.PROTECT,
        related_name="membresias",
        verbose_name="Organización",
    )

    tipo = models.CharField(max_length=10, choices=TIPOS, default=SOCIO, verbose_name="Tipo")

    cargo = models.CharField(
        max_length=15,
        choices=CARGOS,
        blank=True,
        verbose_name="Cargo en la directiva",
    )

    fecha_inicio = models.DateField(default=date.today, verbose_name="Fecha de inicio")

    fecha_termino = models.DateField(null=True, blank=True, verbose_name="Fecha de término")

    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Membresía en organización"
        verbose_name_plural = "Membresías en organizaciones"
        ordering = ["organizacion__nombre", "tipo", "cargo", "vecino__nombre"]
        # Un vecino tiene una sola membresía vigente por organización: se
        # valida en clean() (MariaDB no admite índices únicos condicionales).
        indexes = [
            models.Index(fields=["organizacion", "activo"], name="mem_organizacion_activo_idx"),
        ]

    def __str__(self):
        etiqueta = self.get_cargo_display() if self.tipo == self.DIRIGENTE else self.get_tipo_display()
        return f"{self.vecino.nombre} - {etiqueta} - {self.organizacion}"

    def clean(self):
        super().clean()
        errores = {}

        if self.tipo == self.DIRIGENTE and not self.cargo:
            errores["cargo"] = "Un dirigente debe tener un cargo en la directiva."
        if self.tipo == self.SOCIO:
            self.cargo = ""

        if self.fecha_termino and self.fecha_inicio and self.fecha_termino < self.fecha_inicio:
            errores["fecha_termino"] = "La fecha de término no puede ser anterior a la de inicio."

        if self.vecino_id and self.organizacion_id:
            if self.activo and MembresiaJunta.objects.filter(
                vecino_id=self.vecino_id, organizacion_id=self.organizacion_id, activo=True
            ).exclude(pk=self.pk).exists():
                errores["vecino"] = "Este vecino ya tiene una membresía vigente en la organización."

            if (
                self.organizacion.delegacion_id
                and self.vecino.delegacion_id != self.organizacion.delegacion_id
            ):
                errores["vecino"] = "El vecino no pertenece a la delegación de la organización."

        if (
            self.activo
            and self.tipo == self.DIRIGENTE
            and self.cargo in self.CARGOS_UNICOS
            and self.organizacion_id
            and MembresiaJunta.objects.filter(
                organizacion_id=self.organizacion_id,
                tipo=self.DIRIGENTE,
                cargo=self.cargo,
                activo=True,
            ).exclude(pk=self.pk).exists()
        ):
            errores["cargo"] = (
                f"La organización ya tiene un/a {self.get_cargo_display().lower()} vigente. "
                "Cierre esa membresía antes de asignar el cargo."
            )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if self.tipo == self.SOCIO:
            self.cargo = ""
        super().save(*args, **kwargs)


# ============================================================
# HITO
# ============================================================
# Hito de la gestión territorial (operativo, reunión con la junta,
# entrega de beneficios, inauguración...) con un funcionario responsable.

class Hito(models.Model):

    PENDIENTE = "PENDIENTE"
    EN_CURSO = "EN_CURSO"
    CUMPLIDO = "CUMPLIDO"
    CANCELADO = "CANCELADO"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (EN_CURSO, "En curso"),
        (CUMPLIDO, "Cumplido"),
        (CANCELADO, "Cancelado"),
    ]

    nombre = models.CharField(max_length=200, verbose_name="Nombre del hito")

    descripcion = models.TextField(
        blank=True,
        max_length=MAX_DESCRIPCION,
        validators=[MaxLengthValidator(MAX_DESCRIPCION)],
        verbose_name="Descripción",
    )

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        related_name="hitos",
        verbose_name="Delegación",
    )

    territorio = models.ForeignKey(
        Territorio,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="hitos",
        verbose_name="Territorio",
    )

    organizacion = models.ForeignKey(
        OrganizacionComunitaria,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="hitos",
        verbose_name="Organización relacionada",
    )

    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hitos_a_cargo",
        verbose_name="Funcionario responsable",
    )

    fecha_programada = models.DateField(verbose_name="Fecha programada")

    fecha_cumplimiento = models.DateField(null=True, blank=True, verbose_name="Fecha de cumplimiento")

    estado = models.CharField(
        max_length=10, choices=ESTADOS, default=PENDIENTE, db_index=True, verbose_name="Estado"
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hitos_creados",
        editable=False,
        null=True,
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    activo = models.BooleanField(default=True, verbose_name="Vigente")

    class Meta:
        verbose_name = "Hito"
        verbose_name_plural = "Hitos"
        ordering = ["fecha_programada", "nombre"]
        indexes = [
            models.Index(fields=["delegacion", "activo", "fecha_programada"], name="hito_deleg_fecha_idx"),
            models.Index(fields=["responsable", "estado"], name="hito_responsable_estado_idx"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.fecha_programada:%d-%m-%Y})"

    def clean(self):
        super().clean()
        errores = {}
        self.nombre = " ".join((self.nombre or "").split())

        if not self.nombre:
            errores["nombre"] = "El nombre es obligatorio."

        if self.territorio_id and self.delegacion_id and self.territorio.delegacion_id != self.delegacion_id:
            errores["territorio"] = "El territorio no pertenece a la delegación del hito."

        if (
            self.organizacion_id
            and self.delegacion_id
            and self.organizacion.delegacion_id
            and self.organizacion.delegacion_id != self.delegacion_id
        ):
            errores["organizacion"] = "La organización no pertenece a la delegación del hito."

        if self.responsable_id and self.delegacion_id:
            delegacion_responsable = getattr(
                getattr(self.responsable, "perfil", None), "delegacion_id", None
            )
            if not self.responsable.is_superuser and delegacion_responsable != self.delegacion_id:
                errores["responsable"] = "El responsable debe ser un funcionario de la delegación."

        if self.estado == self.CUMPLIDO and not self.fecha_cumplimiento:
            errores["fecha_cumplimiento"] = "Indique la fecha en que se cumplió el hito."
        if self.estado != self.CUMPLIDO and self.fecha_cumplimiento:
            errores["fecha_cumplimiento"] = "Solo un hito cumplido lleva fecha de cumplimiento."
        if self.fecha_cumplimiento and self.fecha_cumplimiento > date.today():
            errores["fecha_cumplimiento"] = "La fecha de cumplimiento no puede ser futura."

        if errores:
            raise ValidationError(errores)

    @property
    def atrasado(self):
        return (
            self.activo
            and self.estado in (self.PENDIENTE, self.EN_CURSO)
            and self.fecha_programada < date.today()
        )
