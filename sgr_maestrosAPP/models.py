
from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxLengthValidator,
    MaxValueValidator,
    MinValueValidator,
)

from tubo_gestionAPP.validadores import (
    TIPO_GESTION_EJECUCION,
    TIPO_GESTION_PREPARATORIA,
    calcular_dias_computables,
    tipo_gestion_puntua,
    validar_codigo_unico_catalogo,
    validar_rango_fechas,
    validar_suma_ponderaciones,
    validar_suma_ponderaciones_por_cargo,
)

from .feriados import feriados_entre


# Largo máximo de los campos de texto libre. TextField no aplica el
# límite por sí solo: se declara max_length (formulario y maxlength del
# HTML) y MaxLengthValidator (validación del modelo).
MAX_DESCRIPCION = 1000
MAX_OBSERVACIONES = 1000


# ============================================================
# MODELO 1: CATÁLOGO DE ACTIVIDADES
# ============================================================

class CatalogoActividad(models.Model):

    # R5: coordinaciones, correos e invitaciones no dan punto; solo la
    # acción realizada. Ej.: "Coordinación de taller" = Preparatoria,
    # "Realización de taller" = Ejecución.
    TIPO_GESTION_OPCIONES = [
        (TIPO_GESTION_EJECUCION, "Ejecución (suma puntaje)"),
        (TIPO_GESTION_PREPARATORIA, "Preparatoria (no suma puntaje)"),
    ]

    codigo = models.CharField(
        max_length=40,
        unique=True
    )

    nombre = models.CharField(
        max_length=150
    )

    descripcion = models.TextField(
        blank=True,
        max_length=MAX_DESCRIPCION,
        validators=[MaxLengthValidator(MAX_DESCRIPCION)],
    )

    area = models.CharField(
        max_length=100,
        blank=True
    )

    tipo_gestion = models.CharField(
        max_length=12,
        choices=TIPO_GESTION_OPCIONES,
        default=TIPO_GESTION_EJECUCION,
        db_index=True,
        verbose_name="Tipo de gestión",
        help_text=(
            "Ejecución: la acción realizada, suma puntaje. Preparatoria: "
            "correos, coordinaciones e invitaciones, no suma puntaje."
        ),
    )

    activo = models.BooleanField(
        default=True
    )

    class Meta:
        verbose_name = "Actividad del catálogo"
        verbose_name_plural = "Catálogo de actividades"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    @property
    def puntua(self):
        """True si registrar esta actividad suma puntaje (R5)."""
        return tipo_gestion_puntua(self.tipo_gestion)

    def clean(self):
        super().clean()

        self.codigo = (self.codigo or "").strip().upper()
        self.nombre = (self.nombre or "").strip()

        if not self.codigo:
            raise ValidationError({
                "codigo": "El código es obligatorio."
            })

        if not self.nombre:
            raise ValidationError({
                "nombre": "El nombre es obligatorio."
            })

        codigos_existentes = [
            codigo.upper()
            for codigo in CatalogoActividad.objects.exclude(
                pk=self.pk
            ).values_list("codigo", flat=True)
        ]

        try:
            validar_codigo_unico_catalogo(self.codigo, codigos_existentes)
        except ValidationError:
            raise ValidationError({
                "codigo": "Ya existe una actividad con este código."
            })


# ============================================================
# MODELO 2: GESTIÓN DE PERÍODOS
# ============================================================

class Periodo(models.Model):

    codigo = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="Código"
    )

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre del período"
    )

    fecha_inicio = models.DateField(
        verbose_name="Fecha de inicio"
    )

    fecha_fin = models.DateField(
        verbose_name="Fecha de término"
    )

    cerrado = models.BooleanField(
        default=False,
        verbose_name="Período cerrado"
    )

    class Meta:
        verbose_name = "Período"
        verbose_name_plural = "Períodos"
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    # Valor centinela: distingue "no filtrar por cargo" de "metas sin
    # cargo" (cargo=None).
    TODOS_LOS_CARGOS = object()

    def ponderaciones_activas(self, excluir_meta=None, cargo=TODOS_LOS_CARGOS):
        """
        Ponderaciones de las metas activas del período. Con `cargo`, solo
        las de ese cargo (None = metas generales, sin cargo asignado).
        """
        if self.pk is None:
            return []

        metas = self.metas.filter(activo=True)

        if cargo is not self.TODOS_LOS_CARGOS:
            if cargo is None:
                metas = metas.filter(cargo__isnull=True)
            else:
                metas = metas.filter(cargo=cargo)

        if excluir_meta is not None:
            metas = metas.exclude(pk=excluir_meta)

        return list(metas.values_list("ponderacion", flat=True))

    def suma_ponderaciones(self, cargo=TODOS_LOS_CARGOS):
        return sum(self.ponderaciones_activas(cargo=cargo), Decimal("0"))

    GRUPO_SIN_CARGO = "Sin cargo"

    def _grupos_por_cargo(self):
        """
        {cargo_id: (etiqueta, [ponderaciones])} de las metas activas; las
        metas generales usan la clave None.

        Se agrupa por id y no por nombre: un cargo que se llame
        "Sin cargo" no debe mezclarse con las metas generales.
        """
        grupos = {}
        if self.pk is None:
            return grupos

        for cargo_id, nombre, ponderacion in self.metas.filter(
            activo=True
        ).order_by("cargo__nombre").values_list(
            "cargo_id", "cargo__nombre", "ponderacion"
        ):
            if cargo_id is None:
                etiqueta = self.GRUPO_SIN_CARGO
            elif nombre.strip().lower() == self.GRUPO_SIN_CARGO.lower():
                etiqueta = f"{nombre} (cargo)"
            else:
                etiqueta = nombre

            grupos.setdefault(cargo_id, (etiqueta, []))[1].append(ponderacion)

        return grupos

    def ponderaciones_por_cargo(self):
        """
        {etiqueta del cargo: [ponderaciones]} de las metas activas. Las
        metas sin cargo forman el grupo "Sin cargo".
        """
        return {
            etiqueta: ponderaciones
            for etiqueta, ponderaciones in self._grupos_por_cargo().values()
        }

    def resumen_ponderaciones_por_cargo(self):
        """
        Lista de {cargo, suma, completo, general} para mostrar en el
        listado.
        """
        return [
            {
                "cargo": etiqueta,
                "suma": sum(ponderaciones, Decimal("0")),
                "completo": sum(ponderaciones, Decimal("0")) == 100,
                "general": cargo_id is None,
            }
            for cargo_id, (etiqueta, ponderaciones)
            in self._grupos_por_cargo().items()
        ]

    def validar_cierre(self):
        """
        Un período solo puede cerrarse cuando las metas activas de CADA
        cargo suman exactamente 100%: así la evaluación de cada
        funcionario queda completa.
        """
        grupos = self.ponderaciones_por_cargo()
        solo_generales = list(self._grupos_por_cargo()) == [None]

        # Sin metas, o solo metas generales: regla original.
        if not grupos or solo_generales:
            try:
                validar_suma_ponderaciones(self.ponderaciones_activas())
            except ValidationError:
                raise ValidationError({
                    "cerrado": (
                        "No se puede cerrar el período: sus metas activas "
                        f"suman {self.suma_ponderaciones()}% y deben sumar "
                        "exactamente 100%."
                    )
                })
            return

        try:
            validar_suma_ponderaciones_por_cargo(grupos)
        except ValidationError as error:
            raise ValidationError({
                "cerrado": (
                    "No se puede cerrar el período. " + error.messages[0]
                )
            })

    def clean(self):
        super().clean()

        if self.fecha_inicio and self.fecha_fin:
            try:
                validar_rango_fechas(self.fecha_inicio, self.fecha_fin)
            except ValidationError as error:
                raise ValidationError({"fecha_fin": error.messages})


# ============================================================
# MODELO 3: DETALLE DE PERÍODO
# ============================================================

class DetallePeriodo(models.Model):

    periodo = models.ForeignKey(
        Periodo,
        on_delete=models.PROTECT,
        related_name="detalles",
        verbose_name="Período"
    )

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre del detalle"
    )

    fecha_inicio = models.DateField(
        verbose_name="Fecha de inicio"
    )

    fecha_fin = models.DateField(
        verbose_name="Fecha de término"
    )

    dias_computables = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name="Días computables",
        help_text=(
            "Se calcula automáticamente: días hábiles del rango, sin "
            "fines de semana ni feriados nacionales."
        )
    )

    observaciones = models.TextField(
        blank=True,
        max_length=MAX_OBSERVACIONES,
        validators=[MaxLengthValidator(MAX_OBSERVACIONES)],
        verbose_name="Observaciones"
    )

    # Baja logica: el detalle se conserva para no perder trazabilidad.
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )

    class Meta:
        verbose_name = "Detalle de período"
        verbose_name_plural = "Detalles de períodos"
        ordering = ["fecha_inicio"]

        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "nombre"],
                name="unique_detalle_nombre_periodo"
            )
        ]

    def __str__(self):
        return f"{self.periodo.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if self.fecha_inicio and self.fecha_fin:
            try:
                validar_rango_fechas(self.fecha_inicio, self.fecha_fin)
            except ValidationError as error:
                raise ValidationError({"fecha_fin": error.messages})

        if self.periodo_id:
            periodo = self.periodo

            if (
                self.fecha_inicio
                and self.fecha_inicio < periodo.fecha_inicio
            ):
                raise ValidationError({
                    "fecha_inicio": (
                        "El detalle no puede comenzar "
                        "antes del período principal."
                    )
                })

            if (
                self.fecha_fin
                and self.fecha_fin > periodo.fecha_fin
            ):
                raise ValidationError({
                    "fecha_fin": (
                        "El detalle no puede terminar "
                        "después del período principal."
                    )
                })

    def calcular_dias(self):
        """Días hábiles del rango, sin fines de semana ni feriados."""
        # Acepta también fechas en texto ("2026-01-31"), como las que se
        # pueden asignar desde el ORM antes de guardar.
        inicio = self._meta.get_field("fecha_inicio").to_python(self.fecha_inicio)
        fin = self._meta.get_field("fecha_fin").to_python(self.fecha_fin)

        if not (inicio and fin) or fin < inicio:
            return None

        return calcular_dias_computables(inicio, fin, feriados_entre(inicio, fin))

    def save(self, *args, **kwargs):
        # El valor nunca se escribe a mano: siempre se deriva del rango.
        self.dias_computables = self.calcular_dias()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"dias_computables"}

        super().save(*args, **kwargs)


# ============================================================
# MODELO 4: GESTIÓN DE METAS
# ============================================================

class Meta(models.Model):

    codigo = models.CharField(
        max_length=40,
        unique=True,
        verbose_name="Código de la meta"
    )

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre de la meta"
    )

    descripcion = models.TextField(
        blank=True,
        max_length=MAX_DESCRIPCION,
        validators=[MaxLengthValidator(MAX_DESCRIPCION)],
        verbose_name="Descripción"
    )

    periodo = models.ForeignKey(
        Periodo,
        on_delete=models.PROTECT,
        related_name="metas",
        verbose_name="Período de evaluación"
    )

    actividad = models.ForeignKey(
        CatalogoActividad,
        on_delete=models.PROTECT,
        related_name="metas",
        verbose_name="Actividad del catálogo"
    )

    # En la matriz real las metas son por cargo (Apoyo Administrativo,
    # Territorial OO.CC., Gestor Social, etc.). Null = meta general,
    # para conservar las metas creadas antes de este cambio.
    cargo = models.ForeignKey(
        "seguridadAPP.Cargo",
        on_delete=models.PROTECT,
        related_name="metas",
        null=True,
        blank=True,
        verbose_name="Cargo",
        help_text=(
            "Cargo al que se aplica la meta. Las ponderaciones deben "
            "sumar 100% por período y cargo."
        ),
    )

    valor_objetivo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01"))
        ],
        verbose_name="Valor objetivo",
        help_text="Cantidad que se espera alcanzar."
    )

    ponderacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00"))
        ],
        verbose_name="Ponderación (%)",
        help_text="Peso porcentual de la meta."
    )

    activo = models.BooleanField(
        default=True,
        verbose_name="Meta activa"
    )

    class Meta:
        verbose_name = "Meta"
        verbose_name_plural = "Metas"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def ponderacion_disponible(self):
        """Lo que queda para llegar a 100% en este período y cargo."""
        return 100 - sum(
            self.periodo.ponderaciones_activas(
                excluir_meta=self.pk,
                cargo=self.cargo if self.cargo_id else None,
            ),
            Decimal("0"),
        )

    def clean(self):
        super().clean()

        self.codigo = (self.codigo or "").strip().upper()
        self.nombre = (self.nombre or "").strip()

        errores = {}

        if not self.codigo:
            errores["codigo"] = "El código es obligatorio."

        if not self.nombre:
            errores["nombre"] = "El nombre es obligatorio."

        if self.codigo and Meta.objects.exclude(
            pk=self.pk
        ).filter(
            codigo__iexact=self.codigo
        ).exists():
            errores["codigo"] = (
                "Ya existe una meta con este código."
            )

        if (
            self.valor_objetivo is not None
            and self.valor_objetivo <= 0
        ):
            errores["valor_objetivo"] = (
                "El valor objetivo debe ser mayor que cero."
            )

        if self.ponderacion is not None:
            if (
                self.ponderacion < 0
                or self.ponderacion > 100
            ):
                errores["ponderacion"] = (
                    "La ponderación debe estar entre 0 y 100."
                )

        # Las metas activas de un mismo período y cargo no pueden
        # superar el 100%.
        if (
            "ponderacion" not in errores
            and self.ponderacion is not None
            and self.activo
            and self.periodo_id
        ):
            disponible = self.ponderacion_disponible()

            if self.ponderacion > disponible:
                if self.cargo_id:
                    errores["ponderacion"] = (
                        "Las metas activas del cargo "
                        f"'{self.cargo.nombre}' en este período "
                        "superarían el 100%. "
                        f"Ponderación disponible: {disponible}%."
                    )
                else:
                    errores["ponderacion"] = (
                        "Las metas activas del período superarían el "
                        f"100%. Ponderación disponible: {disponible}%."
                    )

        if errores:
            raise ValidationError(errores)


# ============================================================
# MODELO 6: ASIGNACIÓN DE METAS POR FUNCIONARIO Y TRIMESTRE
# ============================================================
# Separa el catálogo de metas (Meta: período, actividad, cargo, valor y
# ponderación de referencia) de su asignación a cada funcionario, con
# cantidad exigida y ponderación individuales (pauta Eva 3, Actividad 2).
#
# Sin asignación, el funcionario sigue usando la meta de su cargo tal como
# antes: el cálculo de «Mi matriz» solo cambia para quien tenga una
# asignación vigente.

class AsignacionMeta(models.Model):

    meta = models.ForeignKey(
        "sgr_maestrosAPP.Meta",
        on_delete=models.PROTECT,
        related_name="asignaciones",
        verbose_name="Meta del catálogo",
    )

    funcionario = models.ForeignKey(
        "seguridadAPP.PerfilUsuario",
        on_delete=models.PROTECT,
        related_name="metas_asignadas",
        verbose_name="Funcionario",
    )

    cantidad_exigida = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Cantidad exigida",
        help_text="Cantidad que se le exige a este funcionario en el trimestre.",
    )

    ponderacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("100.00")),
        ],
        verbose_name="Ponderación individual (%)",
        help_text="Las metas del funcionario en el trimestre no pueden superar el 100%.",
    )

    observacion = models.TextField(
        blank=True,
        max_length=MAX_OBSERVACIONES,
        validators=[MaxLengthValidator(MAX_OBSERVACIONES)],
        verbose_name="Observación",
    )

    activo = models.BooleanField(default=True, verbose_name="Asignación vigente")

    class Meta:
        verbose_name = "Asignación de meta"
        verbose_name_plural = "Asignaciones de metas"
        ordering = ["meta__periodo__codigo", "funcionario__usuario__first_name", "meta__codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["meta", "funcionario"],
                condition=models.Q(activo=True),
                name="unique_asignacion_meta_vigente",
            ),
        ]
        indexes = [
            models.Index(fields=["funcionario", "activo"], name="asig_funcionario_activo_idx"),
        ]

    def __str__(self):
        return f"{self.meta.codigo} - {self.funcionario}"

    @property
    def periodo(self):
        return self.meta.periodo

    def clean(self):
        super().clean()
        errores = {}

        if not self.meta_id or not self.funcionario_id:
            return

        meta = self.meta

        # Se consulta en la base: el período pudo cerrarse mientras el
        # formulario estaba abierto.
        if Periodo.objects.filter(pk=meta.periodo_id, cerrado=True).exists():
            errores["meta"] = "El período de la meta está cerrado: no admite asignaciones."
        elif not meta.activo:
            errores["meta"] = "La meta está dada de baja."

        if meta.cargo_id and self.funcionario.cargo_id != meta.cargo_id:
            errores["funcionario"] = (
                f"La meta es del cargo «{meta.cargo.nombre}» y el funcionario "
                "tiene otro cargo (o ninguno)."
            )

        if self.activo and AsignacionMeta.objects.filter(
            meta_id=self.meta_id, funcionario_id=self.funcionario_id, activo=True
        ).exclude(pk=self.pk).exists():
            errores["meta"] = "El funcionario ya tiene esta meta asignada."

        if self.activo and self.ponderacion is not None and "funcionario" not in errores:
            otras = sum(
                (item.ponderacion for item in metas_del_funcionario(self.funcionario, meta.periodo)
                 if item.meta.pk != meta.pk),
                Decimal("0"),
            )
            disponible = Decimal("100") - otras
            if self.ponderacion > disponible:
                errores["ponderacion"] = (
                    "Las metas del funcionario en el trimestre superarían el 100%. "
                    f"Ponderación disponible: {disponible}%."
                )

        if errores:
            raise ValidationError(errores)


class MetaDelFuncionario:
    """Meta que se le aplica a un funcionario, con su objetivo y ponderación."""

    __slots__ = ("meta", "objetivo", "ponderacion", "asignacion")

    def __init__(self, meta, asignacion=None):
        self.meta = meta
        self.asignacion = asignacion
        self.objetivo = asignacion.cantidad_exigida if asignacion else meta.valor_objetivo
        self.ponderacion = asignacion.ponderacion if asignacion else meta.ponderacion

    @property
    def individual(self):
        return self.asignacion is not None


def metas_del_funcionario(funcionario, periodo):
    """
    Metas que se le aplican al funcionario en el período:

    - Las metas activas de su cargo, con la cantidad y ponderación de la
      asignación individual cuando existe.
    - Las metas asignadas individualmente que no son de su cargo (metas
      generales).
    """
    asignaciones = {
        asignacion.meta_id: asignacion
        for asignacion in AsignacionMeta.objects.filter(
            funcionario=funcionario,
            activo=True,
            meta__periodo=periodo,
            meta__activo=True,
        ).select_related("meta__actividad", "meta__cargo")
    }

    metas = []
    if funcionario.cargo_id:
        metas = list(
            Meta.objects.filter(
                periodo=periodo, cargo_id=funcionario.cargo_id, activo=True,
            ).select_related("actividad", "cargo")
        )

    incluidas = {meta.pk for meta in metas}
    metas += [a.meta for meta_id, a in asignaciones.items() if meta_id not in incluidas]
    metas.sort(key=lambda meta: meta.codigo)

    return [MetaDelFuncionario(meta, asignaciones.get(meta.pk)) for meta in metas]
