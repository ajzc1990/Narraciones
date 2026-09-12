from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'narraciones'

urlpatterns = [
    # Portada y aplicación principal
    path('', views.landing, name='landing'),
    path('app/', views.index, name='index'),
    path('menu/', views.menu, name='menu'),
    path('ayuda/', views.ayuda, name='ayuda'),
    path('privacidad/', views.privacidad, name='privacidad'),
    path('terminos/', views.terminos, name='terminos'),
    path('finalizar/<int:cuento_id>/', views.finalizar_cuento, name='finalizar_cuento'),
    path('finalizar-libre/', views.finalizar_libre, name='finalizar_libre'),

    # Autenticación (RF-01 / RF-02)
    path('login/', auth_views.LoginView.as_view(template_name='narraciones/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='narraciones:landing'), name='logout'),
    path('registro/', views.registro, name='registro'),

    # Recuperación de contraseña
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='narraciones/password_reset_form.html',
        email_template_name='narraciones/password_reset_email.html',
        subject_template_name='narraciones/password_reset_subject.txt',
        success_url=reverse_lazy('narraciones:password_reset_done'),
    ), name='password_reset'),
    path('password-reset/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='narraciones/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/confirmar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='narraciones/password_reset_confirm.html',
        success_url=reverse_lazy('narraciones:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('password-reset/hecho/', auth_views.PasswordResetCompleteView.as_view(
        template_name='narraciones/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Gestión de niños (RF-07: alta, modificación, baja)
    path('ninos/', views.nino_lista, name='nino_lista'),
    path('ninos/alta/', views.nino_alta, name='nino_alta'),
    path('ninos/<int:nino_id>/editar/', views.nino_editar, name='nino_editar'),
    path('ninos/<int:nino_id>/eliminar/', views.nino_eliminar, name='nino_eliminar'),

    # Endpoints API / Asíncronos
    path('buscar-pictograma/', views.buscar_pictograma, name='buscar_pictograma'),
    path('palabras-clave/', views.lista_palabras_clave, name='lista_palabras_clave'),
    path('registrar-voto/', views.registrar_voto, name='registrar_voto'),

    # Dashboard docente y gestión de sesiones
    path('historial/', views.historial_sesiones, name='historial_sesiones'),
    path('eliminar-sesion/<int:sesion_id>/', views.eliminar_sesion, name='eliminar_sesion'),
    path('exportar-pdf/<int:nino_id>/', views.exportar_pdf_nino, name='exportar_pdf'),
]
