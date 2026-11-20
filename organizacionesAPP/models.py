import re
import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from delegacionesAPP.models import Delegacion


MAX_OBSERVACIONES = 1000


def normalizar(texto):
    """Mayúsculas, sin tildes y con espacios simples: para comparar nombres."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.upper().split())


# ============================================================
# ORGANIZACIÓN COMUNITARIA
# ============================================================
# Registro de juntas de vecinos y organizaciones funcionales del
# territorio (leyes 19.418 y 20.500). La base inicial se importa del
# registro municipal «sin verificar»: cada organización queda pendiente de
# verificación hasta que un funcionario la revisa.

class OrganizacionComunitaria(models.Model):

    JUNTA_VECINOS = "JUNTA_VECINOS"
    ADULTO_MAYOR = "ADULTO_MAYOR"
    DEPORTIVA = "DEPORTIVA"
    CULTURAL = "CULTURAL"
    COMITE = "COMITE"
    FUNCIONAL = "FUNCIONAL"

    TIPOS = [
        (JUNTA_VECINOS, "Junta de vecinos"),
        (ADULTO_MAYOR, "Club de adulto mayor"),
        (DEPORTIVA, "Organización deportiva"),
        (CULTURAL, "Centro de madres, cultural o agrupación juvenil"),
        (COMITE, "Comité de vecinos, allegados o seguridad"),
        (FUNCIONAL, "Otra organización funcional"),
    ]

    nombre = models.CharField(
        max_length=255,
        verbose_name="Nombre de la organización",
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS,
        default=FUNCIONAL,
        db_index=True,
        verbose_name="Tipo de organización",
    )

    delegacion = models.ForeignKey(
        Delegacion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="organizaciones",
        verbose_name="Delegación",
    )

    territorio_origen = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Territorio en el registro original",
        help_text="Valor de la columna «TERRIT. DELEG.» del registro importado.",
    )

    domicilio = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Domicilio legal",
    )

    socios_activos = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Socios activos",
    )

    fecha_constitucion = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de constitución",
    )

    numero_registro = models.CharField(
        max_length=20,
        db_index=True,
        verbose_name="N° de registro de personalidad jurídica",
    )

    fecha_inscripcion = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de inscripción en el registro",
    )

    registro_directiva = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="N° de registro de la directiva",
    )

    verificada = models.BooleanField(
        default=False,
        verbose_name="Datos verificados",
        help_text="Marque cuando los datos se hayan confirmado con la organización.",
    )

    observaciones = models.TextField(
        blank=True,
        max_length=MAX_OBSERVACIONES,
        validators=[MaxLengthValidator(MAX_OBSERVACIONES)],
        verbose_name="Observaciones",
    )

    # Baja lógica: una organización disuelta se conserva como historial.
    activo = models.BooleanField(
        default=True,
        verbose_name="Vigente",
    )

    class Meta:
        verbose_name = "Organización comunitaria"
        verbose_name_plural = "Organizaciones comunitarias"
        ordering = ["nombre"]
        constraints = [
            # El registro de origen repite algunos números para
            # organizaciones distintas: la clave es número + nombre.
            models.UniqueConstraint(
                fields=["numero_registro", "nombre"],
                name="unique_organizacion_registro_nombre",
            )
        ]
        indexes = [
            models.Index(fields=["delegacion", "activo"], name="org_delegacion_activo_idx"),
        ]

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()

        self.nombre = " ".join((self.nombre or "").split())
        self.numero_registro = " ".join((self.numero_registro or "").split())

        if not self.nombre:
            raise ValidationError({"nombre": "El nombre es obligatorio."})

        if not self.numero_registro:
            raise ValidationError({
                "numero_registro": "El número de registro es obligatorio."
            })

        repetida = OrganizacionComunitaria.objects.exclude(pk=self.pk).filter(
            numero_registro__iexact=self.numero_registro
        )
        if any(normalizar(o.nombre) == normalizar(self.nombre) for o in repetida):
            raise ValidationError({
                "nombre": "Ya existe una organización con este nombre y número de registro."
            })


def tipo_por_nombre(nombre):
    """
    Clasifica la organización según palabras de su nombre. Es una
    sugerencia para la importación: el funcionario puede corregirla.
    """
    texto = normalizar(nombre)

    # Cada palabra debe coincidir desde el inicio de una palabra del
    # nombre («ARTE» no debe calzar con «PARTE»); las terminadas en «$»
    # deben ser la palabra completa («CAM» no calza con «CAMPO»).
    reglas = [
        (OrganizacionComunitaria.JUNTA_VECINOS, [
            "JUNTA DE VECINOS", "JUNTA VECINAL", "JJVV$", "JJ.VV", "UNION COMUNAL DE JUNTAS",
        ]),
        (OrganizacionComunitaria.ADULTO_MAYOR, [
            "ADULTO MAYOR", "ADULTOS MAYORES", "TERCERA EDAD", "CAM$", "CLUB AM$",
        ]),
        (OrganizacionComunitaria.DEPORTIVA, [
            "DEPORTIV", "FUTBOL", "BASQUET", "BASKET", "VOLEY", "VOLEI", "TENIS",
            "CICLIS", "ATLETI", "RAYUELA", "BOXEO", "KARATE", "TAEKWON", "RUGBY",
            "PATIN", "AJEDREZ", "SURF", "SKATE", "HANDBALL", "NATACION",
        ]),
        (OrganizacionComunitaria.COMITE, [
            "COMITE",
        ]),
        (OrganizacionComunitaria.CULTURAL, [
            "CENTRO DE MADRES", "CULTURAL", "ARTISTIC", "ARTE", "FOLCLOR", "FOLKLOR",
            "JUVENIL", "JOVENES", "MUSIC", "DANZA", "BAILE", "TEATRO", "CUECA",
        ]),
    ]

    def calza(palabra):
        completa = palabra.endswith("$")
        patron = r"(?<![A-Z0-9])" + re.escape(palabra.rstrip("$"))
        if completa:
            patron += r"(?![A-Z0-9])"
        return re.search(patron, texto) is not None

    for tipo, palabras in reglas:
        if any(calza(p) for p in palabras):
            return tipo

    return OrganizacionComunitaria.FUNCIONAL
