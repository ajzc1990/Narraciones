from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Pictograma, Sinonimo, Cuento, Nino, ResultadoNarracion, PerfilUsuario, Jardin, RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'usuario', 'accion', 'detalle', 'jardin')
    list_filter = ('accion', 'jardin', 'fecha')
    search_fields = ('usuario__username', 'detalle')
    readonly_fields = ('usuario', 'accion', 'detalle', 'jardin', 'fecha')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Jardin)
class JardinAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'activo', 'direccion', 'telefono', 'total_usuarios', 'total_ninos', 'creado_en')
    list_filter = ('activo',)
    search_fields = ('razon_social', 'cuil')
    readonly_fields = ('aprobado_en',)
    actions = ['aprobar_jardines']

    def total_usuarios(self, obj):
        return obj.usuarios.count()
    total_usuarios.short_description = 'Usuarios'

    def total_ninos(self, obj):
        return obj.ninos.count()
    total_ninos.short_description = 'Niños'

    @admin.action(description="Aprobar instituciones seleccionadas (habilita el acceso a sus usuarios)")
    def aprobar_jardines(self, request, queryset):
        pendientes = queryset.filter(activo=False)
        cantidad = pendientes.count()
        for jardin in pendientes:
            jardin.aprobar()
        self.message_user(request, f"{cantidad} institución(es) aprobada(s).")


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'edad', 'jardin', 'es_admin_jardin')
    list_filter = ('jardin', 'es_admin_jardin')
    list_editable = ('es_admin_jardin',)
    search_fields = ('usuario__username', 'usuario__first_name', 'usuario__last_name')


# --- INLINE DE SINÓNIMOS ---

class SinonimoInline(admin.TabularInline):
    """Permite asociar palabras clave y sinónimos directamente al pictograma."""
    model = Sinonimo
    extra = 2
    fields = ('palabra',)


# --- CONFIGURACIÓN DE PICTOGRAMAS Y SINÓNIMOS ---

@admin.register(Pictograma)
class PictogramaAdmin(admin.ModelAdmin):
    inlines = [SinonimoInline]
    list_display = ('nombre_identificador', 'tipo_imagen', 'mostrar_imagen', 'estado_moderacion', 'revisado', 'total_sinonimos', 'creado_en')
    list_filter = ('tipo_imagen', 'revisado', 'validacion_tecnica_ok', 'creado_en')
    list_editable = ('revisado',)
    search_fields = ('nombre_identificador', 'sinonimos__palabra')
    readonly_fields = ('validacion_tecnica_ok', 'alerta_contenido')
    ordering = ('nombre_identificador',)

    def mostrar_imagen(self, obj):
        if obj.imagen:
            return format_html(
                '<img src="{}" style="width: 48px; height: 48px; object-fit: cover; border-radius: 6px; border: 1px solid #e2e8f0;" />',
                obj.imagen.url
            )
        return mark_safe('<span style="color: #94a3b8; font-size: 12px;">Sin imagen</span>')
    mostrar_imagen.short_description = 'Vista Previa'

    def estado_moderacion(self, obj):
        if not obj.validacion_tecnica_ok:
            return mark_safe(
                f'<span style="background-color: #fee2e2; color: #b91c1c; padding: 3px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">⛔ {obj.alerta_contenido or "Rechazado"}</span>'
            )
        if not obj.revisado:
            return mark_safe(
                '<span style="background-color: #fef9c3; color: #854d0e; padding: 3px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">⏳ Pendiente de revisión</span>'
            )
        return mark_safe(
            '<span style="background-color: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">✅ Apto para menores</span>'
        )
    estado_moderacion.short_description = 'Moderación (RF-05)'

    def total_sinonimos(self, obj):
        count = obj.sinonimos.count()
        return format_html('<span style="font-weight: 600; color: #475569;">{} palabra(s)</span>', count)
    total_sinonimos.short_description = 'Sinónimos'


@admin.register(Sinonimo)
class SinonimoAdmin(admin.ModelAdmin):
    list_display = ('palabra', 'pictograma_asociado')
    search_fields = ('palabra', 'pictograma__nombre_identificador')
    list_select_related = ('pictograma',)

    def pictograma_asociado(self, obj):
        return obj.pictograma.nombre_identificador
    pictograma_asociado.short_description = 'Pictograma'


# --- CONFIGURACIÓN DE CUENTOS ---

@admin.register(Cuento)
class CuentoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'categoria_edad', 'ver_portada', 'ver_imagen_final', 'creado_en')
    list_filter = ('categoria_edad', 'creado_en')
    search_fields = ('titulo', 'descripcion', 'cuerpo_cuento')
    prepopulated_fields = {'slug': ('titulo',)}
    fieldsets = (
        ('Información Principal', {
            'fields': ('titulo', 'slug', 'categoria_edad', 'descripcion', 'cuerpo_cuento')
        }),
        ('Recursos Visuales', {
            'fields': ('imagen_portada', 'imagen_final')
        }),
    )

    def ver_portada(self, obj):
        if obj.imagen_portada:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; border: 1px solid #e2e8f0;" />',
                obj.imagen_portada.url
            )
        return mark_safe('<span style="color: #94a3b8; font-size: 12px;">Sin portada</span>')
    ver_portada.short_description = 'Portada'

    def ver_imagen_final(self, obj):
        if obj.imagen_final:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 6px; border: 1px solid #e2e8f0;" />',
                obj.imagen_final.url
            )
        return mark_safe('<span style="color: #94a3b8; font-size: 12px;">Sin imagen final</span>')
    ver_imagen_final.short_description = 'Premio Final'


# --- CONFIGURACIÓN DE NIÑOS ---

@admin.register(Nino)
class NinoAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'dni', 'edad', 'jardin', 'autorizacion_parental', 'tutor', 'total_sesiones', 'creado_en')
    list_filter = ('jardin', 'autorizacion_parental', 'edad', 'institucion_o_sala')
    search_fields = ('nombre', 'apellido', 'institucion_o_sala', 'dni')
    readonly_fields = ('autorizacion_registrada_en',)

    def nombre_completo(self, obj):
        return f"{obj.apellido}, {obj.nombre}"
    nombre_completo.short_description = 'Alumno'

    def total_sesiones(self, obj):
        return obj.resultados.count()
    total_sesiones.short_description = 'Sesiones'


# --- CONFIGURACIÓN DE SESIONES / RESULTADOS ---

@admin.register(ResultadoNarracion)
class ResultadoNarracionAdmin(admin.ModelAdmin):
    list_display = ('nino_display', 'cuento', 'fecha_formateada', 'duracion_display', 'voto_visual')
    list_filter = ('le_gusto', 'fecha', 'cuento')
    search_fields = ('nino__nombre', 'nino__apellido', 'cuento__titulo')
    list_select_related = ('nino', 'cuento')
    readonly_fields = ('nino', 'cuento', 'le_gusto', 'duracion_segundos', 'fecha')

    def nino_display(self, obj):
        return f"{obj.nino.nombre} {obj.nino.apellido}" if obj.nino else "Anónimo"
    nino_display.short_description = 'Alumno'

    def fecha_formateada(self, obj):
        return obj.fecha.strftime('%d/%m/%Y %H:%M')
    fecha_formateada.short_description = 'Fecha y Hora'

    def duracion_display(self, obj):
        if obj.duracion_segundos:
            minutos = obj.duracion_segundos // 60
            segundos = obj.duracion_segundos % 60
            return f"{minutos}m {segundos}s"
        return "-"
    duracion_display.short_description = 'Duración'

    def voto_visual(self, obj):
        if obj.le_gusto:
            return mark_safe(
                '<span style="background-color: #dcfce7; color: #15803d; padding: 4px 10px; border-radius: 9999px; font-weight: bold; font-size: 12px;">👍 Positivo</span>'
            )
        return mark_safe(
            '<span style="background-color: #fee2e2; color: #b91c1c; padding: 4px 10px; border-radius: 9999px; font-weight: bold; font-size: 12px;">👎 A mejorar</span>'
        )
    voto_visual.short_description = 'Calificación'