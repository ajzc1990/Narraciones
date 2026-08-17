from django.urls import path
from . import views

app_name = 'narraciones'

urlpatterns = [
    # Portada y aplicación principal
    path('', views.landing, name='landing'),
    path('app/', views.index, name='index'),
    path('finalizar/<int:cuento_id>/', views.finalizar_cuento, name='finalizar_cuento'),

    # Endpoints API / Asíncronos
    path('buscar-pictograma/', views.buscar_pictograma, name='buscar_pictograma'),
    path('palabras-clave/', views.lista_palabras_clave, name='lista_palabras_clave'),
    path('registrar-voto/', views.registrar_voto, name='registrar_voto'),

    # Dashboard docente y gestión de sesiones
    path('historial/', views.historial_sesiones, name='historial_sesiones'),
    path('eliminar-sesion/<int:sesion_id>/', views.eliminar_sesion, name='eliminar_sesion'),
    path('exportar-pdf/<int:nino_id>/', views.exportar_pdf_nino, name='exportar_pdf'),

    # Carga de datos iniciales
    path('cargar-datos/', views.cargar_datos_ejemplo, name='cargar_datos_ejemplo'),
]