from django.shortcuts import redirect
from django.urls import reverse

# Rutas accesibles aunque la institución del usuario esté pendiente de
# aprobación, o la cuenta sea una demo con los usos agotados: cerrar sesión,
# páginas institucionales/legales, ayuda y las propias pantallas de bloqueo
# (para no generar un loop de redirects).
_NOMBRES_URL_PERMITIDOS = {
    'narraciones:landing',
    'narraciones:logout',
    'narraciones:ayuda',
    'narraciones:privacidad',
    'narraciones:terminos',
    'narraciones:jardin_pendiente',
    'narraciones:demo_agotada',
}


class JardinActivoMiddleware:
    """
    Bloquea el uso de la aplicación mientras la institución (Jardin) del
    usuario logueado esté pendiente de aprobación (RF: alta de institución
    por autoservicio con aprobación manual de un administrador), o mientras
    una cuenta de demostración con límite de usos ya lo haya agotado.

    No afecta rutas fuera de la app (/admin/, estáticos, media) ni a
    usuarios sin institución asignada o sin sesión iniciada.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._rutas_permitidas = None

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            return self.get_response(request)

        usuario = getattr(request, 'user', None)
        if usuario is not None and usuario.is_authenticated and not usuario.is_superuser:
            perfil = getattr(usuario, 'perfil', None)

            if self._rutas_permitidas is None:
                self._rutas_permitidas = {reverse(nombre) for nombre in _NOMBRES_URL_PERMITIDOS}
            permitido = request.path in self._rutas_permitidas

            if not permitido and perfil is not None and perfil.demo_agotada:
                return redirect('narraciones:demo_agotada')

            jardin = perfil.jardin if perfil else None
            if not permitido and jardin is not None and not jardin.activo:
                return redirect('narraciones:jardin_pendiente')

        return self.get_response(request)
