from django.contrib import admin
from .models import ZonaRiesgo, Alerta, ContactoEmergencia

@admin.register(ZonaRiesgo)
class ZonaRiesgoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'delegacion', 'nivel_peligro')
    list_filter = ('delegacion', 'nivel_peligro')
    search_fields = ('nombre', 'descripcion_riesgo')

@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ('tipo_evento', 'nivel', 'zona', 'fecha_inicio', 'estado')
    list_filter = ('nivel', 'estado', 'zona__delegacion')
    search_fields = ('tipo_evento', 'descripcion')
    date_hierarchy = 'fecha_inicio'
    
    fieldsets = (
        ('Datos de la Alerta', {
            'fields': ('tipo_evento', 'nivel', 'zona', 'estado')
        }),
        ('Detalles', {
            'fields': ('descripcion', 'fecha_inicio', 'fecha_fin'),
        }),
    )
    readonly_fields = ('fecha_inicio',)

@admin.register(ContactoEmergencia)
class ContactoEmergenciaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cargo', 'delegacion', 'telefono')
    list_filter = ('delegacion',)
    search_fields = ('nombre', 'cargo')
