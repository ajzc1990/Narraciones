from django.shortcuts import redirect
from django.urls import reverse

# Rutas accesibles aunque la institución del usuario esté pendiente de
# aprobación: cerrar sesión, páginas institucionales/legales, ayuda y la
# propia pantalla de "pendiente de aprobación" (para no generar un loop).
_NOMBRES_URL_PERMITIDOS = {
    'narraciones:landing',
    'narraciones:logout',
    'narraciones:ayuda',
    'narraciones:privacidad',
    'narraciones:terminos',
    'narraciones:jardin_pendiente',
}


class JardinActivoMiddleware:
    """
    Bloquea el uso de la aplicación mientras la institución (Jardin) del
    usuario logueado esté pendiente de aprobación (RF: alta de institución
    por autoservicio con aprobación manual de un administrador).

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
        if usuario is not None and usuario.is_authenticated:
            perfil = getattr(usuario, 'perfil', None)
            jardin = perfil.jardin if perfil else None
            if jardin is not None and not jardin.activo:
                if self._rutas_permitidas is None:
                    self._rutas_permitidas = {reverse(nombre) for nombre in _NOMBRES_URL_PERMITIDOS}
                if request.path not in self._rutas_permitidas:
                    return redirect('narraciones:jardin_pendiente')

        return self.get_response(request)
