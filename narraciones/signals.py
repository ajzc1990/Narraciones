from django.contrib.auth.signals import user_logged_in
from django.db.models import F
from django.dispatch import receiver


@receiver(user_logged_in)
def contar_login_de_cuenta_demo(sender, request, user, **kwargs):
    """Incrementa el contador de usos de las cuentas de demostración (con límite configurado)."""
    from .models import PerfilUsuario

    PerfilUsuario.objects.filter(
        usuario=user, limite_logins_demo__isnull=False
    ).update(logins_demo_usados=F('logins_demo_usados') + 1)
