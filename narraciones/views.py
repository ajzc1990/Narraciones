import json
import string
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.text import slugify
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm

from .models import Pictograma, Sinonimo, Cuento, Nino, ResultadoNarracion, RegistroAuditoria, PerfilUsuario
from .forms import RegistroUsuarioForm, NinoForm
from .ml_pictogramas import predecir_pictograma


def registro(request):
    """Registrar Usuario (RF-02)."""
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            # Usuario recién creado sin pasar por authenticate(): con django-axes
            # sumado como backend de autenticación hay que indicar explícitamente
            # cuál validó las credenciales.
            auth_login(request, usuario, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('narraciones:menu')
    else:
        form = RegistroUsuarioForm()
    return render(request, 'narraciones/registro.html', {'form': form})


def _jardin_de(usuario):
    """Institución del usuario logueado, o None si no tiene perfil/jardín asignado."""
    perfil = getattr(usuario, 'perfil', None)
    return perfil.jardin if perfil else None


def _es_admin_jardin(usuario):
    perfil = getattr(usuario, 'perfil', None)
    return bool(perfil and perfil.es_admin_jardin)


@login_required
def menu(request):
    """Menú Principal tras iniciar sesión."""
    return render(request, 'narraciones/menu.html', {
        'jardin': _jardin_de(request.user),
        'es_admin_jardin': _es_admin_jardin(request.user),
    })


@login_required
def jardin_pendiente(request):
    """
    Se muestra en vez de la app mientras la institución del usuario está
    pendiente de aprobación (alta de institución por autoservicio).
    """
    jardin = _jardin_de(request.user)
    if jardin is None or jardin.activo:
        return redirect('narraciones:menu')
    return render(request, 'narraciones/jardin_pendiente.html', {'jardin': jardin})


@login_required
def demo_agotada(request):
    """Se muestra en vez de la app cuando una cuenta de demostración agotó sus usos permitidos."""
    perfil = getattr(request.user, 'perfil', None)
    if perfil is None or not perfil.demo_agotada:
        return redirect('narraciones:menu')
    return render(request, 'narraciones/demo_agotada.html', {'perfil': perfil})


@login_required
@require_GET
def jardin_equipo(request):
    """Panel del administrador de institución: ver y gestionar los docentes de su jardín."""
    jardin = _jardin_de(request.user)
    if not _es_admin_jardin(request.user):
        messages.error(request, "Esa sección es solo para el administrador de la institución.")
        return redirect('narraciones:menu')

    perfiles = (
        jardin.usuarios.select_related('usuario').order_by('usuario__first_name', 'usuario__last_name')
        if jardin else []
    )
    return render(request, 'narraciones/jardin_equipo.html', {'jardin': jardin, 'perfiles': perfiles})


@login_required
@require_POST
def jardin_equipo_actualizar(request, usuario_id):
    """Promueve/revoca administrador o activa/desactiva el acceso de un docente de la propia institución."""
    if not _es_admin_jardin(request.user):
        messages.error(request, "Esa acción es solo para el administrador de la institución.")
        return redirect('narraciones:menu')

    jardin = _jardin_de(request.user)
    perfil = get_object_or_404(PerfilUsuario, usuario_id=usuario_id, jardin=jardin)
    accion = request.POST.get('accion')

    if accion == 'hacer_admin':
        perfil.es_admin_jardin = True
        perfil.save(update_fields=['es_admin_jardin'])
    elif accion == 'quitar_admin':
        if perfil.usuario_id == request.user.id:
            messages.error(request, "No podés quitarte a vos mismo el rol de administrador.")
            return redirect('narraciones:jardin_equipo')
        perfil.es_admin_jardin = False
        perfil.save(update_fields=['es_admin_jardin'])
    elif accion == 'desactivar':
        if perfil.usuario_id == request.user.id:
            messages.error(request, "No podés desactivar tu propia cuenta.")
            return redirect('narraciones:jardin_equipo')
        User.objects.filter(id=perfil.usuario_id).update(is_active=False)
    elif accion == 'reactivar':
        User.objects.filter(id=perfil.usuario_id).update(is_active=True)

    return redirect('narraciones:jardin_equipo')


@login_required
@require_GET
def nino_lista(request):
    """Buscar/gestionar niños registrados (soporte de Modificar/Baja usuario). Solo los del jardín del usuario."""
    q = request.GET.get('q', '').strip()
    ninos = Nino.objects.filter(jardin=_jardin_de(request.user))
    if q:
        ninos = ninos.filter(Q(nombre__icontains=q) | Q(apellido__icontains=q) | Q(dni__icontains=q))

    pagina = Paginator(ninos, 20).get_page(request.GET.get('page'))
    return render(request, 'narraciones/nino_list.html', {'ninos': pagina, 'q': q})


@login_required
def nino_alta(request):
    """Alta de niño (RF-07)."""
    if request.method == 'POST':
        form = NinoForm(request.POST)
        if form.is_valid():
            nino = form.save(commit=False)
            nino.tutor = request.user
            nino.jardin = _jardin_de(request.user)
            nino.save()
            RegistroAuditoria.registrar(request.user, 'crear_nino', f"{nino.nombre} {nino.apellido} (DNI {nino.dni or 's/d'})")
            return redirect('narraciones:nino_lista')
    else:
        form = NinoForm()
    return render(request, 'narraciones/nino_form.html', {'form': form, 'modo': 'alta'})


@login_required
def nino_editar(request, nino_id):
    """Modificación de niño (solo si pertenece al jardín del usuario)."""
    nino = get_object_or_404(Nino, id=nino_id, jardin=_jardin_de(request.user))
    if request.method == 'POST':
        form = NinoForm(request.POST, instance=nino)
        if form.is_valid():
            form.save()
            RegistroAuditoria.registrar(request.user, 'editar_nino', f"{nino.nombre} {nino.apellido} (DNI {nino.dni or 's/d'})")
            return redirect('narraciones:nino_lista')
    else:
        form = NinoForm(instance=nino)
    return render(request, 'narraciones/nino_form.html', {'form': form, 'modo': 'editar', 'nino': nino})


@login_required
@require_http_methods(["GET", "POST"])
def nino_eliminar(request, nino_id):
    """Baja de niño (solo si pertenece al jardín del usuario)."""
    nino = get_object_or_404(Nino, id=nino_id, jardin=_jardin_de(request.user))
    if request.method == 'POST':
        detalle = f"{nino.nombre} {nino.apellido} (DNI {nino.dni or 's/d'})"
        nino.delete()
        RegistroAuditoria.registrar(request.user, 'eliminar_nino', detalle)
        return redirect('narraciones:nino_lista')
    return render(request, 'narraciones/nino_confirm_delete.html', {'nino': nino})


@login_required
@require_GET
def index(request):
    """Panel principal de narración interactiva."""
    cuentos = Cuento.objects.all().order_by('titulo')
    ninos = Nino.objects.filter(jardin=_jardin_de(request.user)).order_by('apellido', 'nombre')
    return render(request, 'narraciones/index.html', {
        'cuentos': cuentos,
        'ninos': ninos
    })


@require_GET
def buscar_pictograma(request):
    """
    Busca una imagen basada en la palabra detectada o sus sinónimos.
    Limpia signos de puntuación y espacios en blanco.
    """
    palabra_raw = request.GET.get('palabra', '')
    # Limpiamos puntuación básica de reconocimiento de voz (comas, puntos, etc.)
    palabra_limpia = palabra_raw.strip().lower().translate(str.maketrans('', '', string.punctuation))

    if not palabra_limpia:
        return JsonResponse({'error': 'No se proporcionó una palabra válida'}, status=400)

    # 1. Intentar coincidencia directa por Sinónimo (diccionario exacto)
    sinonimo = Sinonimo.objects.filter(palabra=palabra_limpia).select_related('pictograma').first()
    if sinonimo and sinonimo.pictograma.imagen and sinonimo.pictograma.apto_para_narracion:
        return JsonResponse({
            'encontrado': True,
            'url': sinonimo.pictograma.imagen.url,
            'nombre': sinonimo.pictograma.nombre_identificador,
            'tipo': sinonimo.pictograma.tipo_imagen,
            'origen': 'diccionario'
        })

    # 2. Fallback: Intentar coincidencia directa por nombre identificador del Pictograma
    pictograma = Pictograma.objects.filter(nombre_identificador__iexact=palabra_limpia).first()
    if pictograma and pictograma.imagen and pictograma.apto_para_narracion:
        return JsonResponse({
            'encontrado': True,
            'url': pictograma.imagen.url,
            'nombre': pictograma.nombre_identificador,
            'tipo': pictograma.tipo_imagen,
            'origen': 'diccionario'
        })

    # 3. Fallback: red neuronal supervisada (RNF-05) para variantes no cargadas manualmente
    prediccion = predecir_pictograma(palabra_limpia)
    if prediccion:
        nombre_predicho, confianza = prediccion
        pictograma_ml = Pictograma.objects.filter(nombre_identificador=nombre_predicho).first()
        if pictograma_ml and pictograma_ml.imagen and pictograma_ml.apto_para_narracion:
            return JsonResponse({
                'encontrado': True,
                'url': pictograma_ml.imagen.url,
                'nombre': pictograma_ml.nombre_identificador,
                'tipo': pictograma_ml.tipo_imagen,
                'origen': 'red_neuronal',
                'confianza': round(confianza, 2)
            })

    return JsonResponse({'encontrado': False, 'error': 'No existe pictograma para esta palabra'}, status=404)


@login_required
@require_GET
def finalizar_cuento(request, cuento_id):
    """Pantalla de recompensa/finalización de lectura."""
    cuento = get_object_or_404(Cuento, id=cuento_id)
    nino_id = request.GET.get('nino_id')
    nino = Nino.objects.filter(id=nino_id, jardin=_jardin_de(request.user)).first() if nino_id else None

    return render(request, 'narraciones/final.html', {
        'cuento': cuento,
        'nino': nino,
        'nino_id': nino_id
    })


@login_required
@require_GET
def finalizar_libre(request):
    """Pantalla de recompensa al terminar una narración libre (RF-09: 'narrar mi propia historia')."""
    nino_id = request.GET.get('nino_id')
    nino = Nino.objects.filter(id=nino_id, jardin=_jardin_de(request.user)).first() if nino_id else None

    return render(request, 'narraciones/final.html', {
        'cuento': None,
        'nino': nino,
        'nino_id': nino_id
    })


@login_required
@require_POST
def registrar_voto(request):
    """API para registrar el resultado o feedback de la sesión."""
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest(JsonResponse({'status': 'error', 'mensaje': 'JSON inválido'}))

    cuento_id = data.get('cuento_id')
    nino_id = data.get('nino_id')
    voto = data.get('voto')
    duracion = data.get('duracion_segundos')

    if voto is None:
        return HttpResponseBadRequest(JsonResponse({'status': 'error', 'mensaje': 'Faltan parámetros obligatorios'}))

    # cuento_id puede venir vacío: la sesión fue una narración libre (RF-09).
    cuento = get_object_or_404(Cuento, id=cuento_id) if cuento_id else None
    nino = Nino.objects.filter(id=nino_id, jardin=_jardin_de(request.user)).first() if nino_id else None

    resultado = ResultadoNarracion.objects.create(
        cuento=cuento,
        nino=nino,
        le_gusto=bool(voto),
        duracion_segundos=int(duracion) if duracion is not None else None
    )

    return JsonResponse({'status': 'ok', 'id': resultado.id})


@login_required
@require_GET
def historial_sesiones(request):
    """Dashboard docente con analíticas y listado de sesiones. Solo del jardín del usuario."""
    resultados = ResultadoNarracion.objects.filter(
        nino__jardin=_jardin_de(request.user)
    ).select_related('nino', 'cuento').order_by('-fecha')
    total = resultados.count()
    likes = resultados.filter(le_gusto=True).count()
    porcentaje_positivo = round((likes / total * 100), 1) if total > 0 else 0

    pagina = Paginator(resultados, 50).get_page(request.GET.get('page'))

    return render(request, 'narraciones/historial.html', {
        'resultados': pagina,
        'total': total,
        'likes': likes,
        'porcentaje_positivo': porcentaje_positivo
    })


@login_required
@require_http_methods(["POST", "DELETE"])
def eliminar_sesion(request, sesion_id):
    """Elimina un registro específico del historial (solo si pertenece al jardín del usuario)."""
    sesion = get_object_or_404(ResultadoNarracion, id=sesion_id, nino__jardin=_jardin_de(request.user))
    sesion.delete()
    return JsonResponse({'status': 'deleted'})


@login_required
@require_GET
def exportar_pdf_nino(request, nino_id):
    """Genera informe pedagógico individual en formato PDF (solo si pertenece al jardín del usuario)."""
    nino = get_object_or_404(Nino, id=nino_id, jardin=_jardin_de(request.user))
    resultados = ResultadoNarracion.objects.filter(nino=nino).select_related('cuento').order_by('-fecha')
    RegistroAuditoria.registrar(request.user, 'exportar_pdf', f"{nino.nombre} {nino.apellido} (DNI {nino.dni or 's/d'})")

    response = HttpResponse(content_type='application/pdf')
    nombre_archivo = slugify(f"Reporte_{nino.nombre}_{nino.apellido}")
    response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    def dibujar_encabezado():
        p.setFillColor(colors.HexColor("#2563eb"))
        p.rect(0, h - 3.2 * cm, w, 3.2 * cm, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 18)
        p.drawString(1.5 * cm, h - 1.6 * cm, "Informe de Progreso Lingüístico")
        p.setFont("Helvetica", 10)
        p.drawString(1.5 * cm, h - 2.3 * cm, "Proyecto Narraciones Interactivas | Seguimiento Pedagógico")

    dibujar_encabezado()

    # Información del Alumno
    p.setFillColor(colors.HexColor("#1e293b"))
    p.setFont("Helvetica-Bold", 13)
    p.drawString(1.5 * cm, h - 4.2 * cm, f"Alumno: {nino.nombre} {nino.apellido}")
    p.setFont("Helvetica", 10)
    p.drawString(1.5 * cm, h - 4.8 * cm, f"Edad: {nino.edad} años | Institución/Sala: {nino.institucion_o_sala or 'No especificada'}")
    p.drawString(1.5 * cm, h - 5.4 * cm, f"Total de narraciones registradas: {resultados.count()}")

    # Cabecera de la tabla
    y = h - 6.8 * cm
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(colors.HexColor("#475569"))
    p.drawString(1.5 * cm, y, "CUENTO")
    p.drawString(9.0 * cm, y, "FECHA")
    p.drawString(14.5 * cm, y, "EVALUACIÓN")
    p.setStrokeColor(colors.HexColor("#cbd5e1"))
    p.setLineWidth(0.5)
    p.line(1.5 * cm, y - 0.2 * cm, w - 1.5 * cm, y - 0.2 * cm)

    y -= 0.8 * cm
    p.setFont("Helvetica", 9)

    for r in resultados:
        if y < 2.5 * cm:
            p.showPage()
            dibujar_encabezado()
            y = h - 4.5 * cm
            p.setFont("Helvetica-Bold", 10)
            p.setFillColor(colors.HexColor("#475569"))
            p.drawString(1.5 * cm, y, "CUENTO")
            p.drawString(9.0 * cm, y, "FECHA")
            p.drawString(14.5 * cm, y, "EVALUACIÓN")
            p.line(1.5 * cm, y - 0.2 * cm, w - 1.5 * cm, y - 0.2 * cm)
            y -= 0.8 * cm
            p.setFont("Helvetica", 9)

        p.setFillColor(colors.black)
        titulo_fila = r.cuento.titulo if r.cuento else "Historia libre"
        p.drawString(1.5 * cm, y, titulo_fila[:42])
        p.drawString(9.0 * cm, y, r.fecha.strftime('%d/%m/%Y %H:%M'))

        if r.le_gusto:
            p.setFillColor(colors.HexColor("#16a34a"))
            p.drawString(14.5 * cm, y, "Positiva (Le gustó)")
        else:
            p.setFillColor(colors.HexColor("#dc2626"))
            p.drawString(14.5 * cm, y, "A mejorar")

        y -= 0.65 * cm

    p.showPage()
    p.save()
    return response


@require_GET
def lista_palabras_clave(request):
    """Retorna listado de palabras indexadas para soporte docente."""
    palabras = Sinonimo.objects.values_list('palabra', flat=True).order_by('palabra')
    return JsonResponse({
        'total': palabras.count(),
        'palabras_disponibles': list(palabras)
    })


@require_GET
def ayuda(request):
    """Manual de ayuda accesible en cualquier momento (RNF-02)."""
    return render(request, 'narraciones/ayuda.html')


@require_GET
def privacidad(request):
    """Política de Privacidad (Ley 25.326)."""
    return render(request, 'narraciones/privacidad.html')


@require_GET
def terminos(request):
    """Términos de Uso."""
    return render(request, 'narraciones/terminos.html')


def landing(request):
    """Página de bienvenida y presentación institucional del proyecto."""
    total_cuentos = Cuento.objects.count()
    total_pictogramas = Pictograma.objects.count()
    total_sesiones = ResultadoNarracion.objects.count()
    return render(request, 'narraciones/landing.html', {
        'total_cuentos': total_cuentos,
        'total_pictogramas': total_pictogramas,
        'total_sesiones': total_sesiones,
    })