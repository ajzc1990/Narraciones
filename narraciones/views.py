import json
import string
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.utils.text import slugify
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm

from .models import Pictograma, Sinonimo, Cuento, Nino, ResultadoNarracion


@require_GET
def index(request):
    """Panel principal de narración interactiva."""
    cuentos = Cuento.objects.all().order_by('titulo')
    ninos = Nino.objects.all().order_by('apellido', 'nombre')
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

    # 1. Intentar coincidencia directa por Sinónimo
    sinonimo = Sinonimo.objects.filter(palabra=palabra_limpia).select_related('pictograma').first()
    if sinonimo and sinonimo.pictograma.imagen:
        return JsonResponse({
            'encontrado': True,
            'url': sinonimo.pictograma.imagen.url,
            'nombre': sinonimo.pictograma.nombre_identificador,
            'tipo': sinonimo.pictograma.tipo_imagen
        })

    # 2. Fallback: Intentar coincidencia directa por nombre identificador del Pictograma
    pictograma = Pictograma.objects.filter(nombre_identificador__iexact=palabra_limpia).first()
    if pictograma and pictograma.imagen:
        return JsonResponse({
            'encontrado': True,
            'url': pictograma.imagen.url,
            'nombre': pictograma.nombre_identificador,
            'tipo': pictograma.tipo_imagen
        })

    return JsonResponse({'encontrado': False, 'error': 'No existe pictograma para esta palabra'}, status=404)


@require_GET
def finalizar_cuento(request, cuento_id):
    """Pantalla de recompensa/finalización de lectura."""
    cuento = get_object_or_404(Cuento, id=cuento_id)
    nino_id = request.GET.get('nino_id')
    nino = Nino.objects.filter(id=nino_id).first() if nino_id else None

    return render(request, 'narraciones/final.html', {
        'cuento': cuento,
        'nino': nino,
        'nino_id': nino_id
    })


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

    if cuento_id is None or voto is None:
        return HttpResponseBadRequest(JsonResponse({'status': 'error', 'mensaje': 'Faltan parámetros obligatorios'}))

    cuento = get_object_or_404(Cuento, id=cuento_id)
    nino = Nino.objects.filter(id=nino_id).first() if nino_id else None

    resultado = ResultadoNarracion.objects.create(
        cuento=cuento,
        nino=nino,
        le_gusto=bool(voto),
        duracion_segundos=int(duracion) if duracion is not None else None
    )

    return JsonResponse({'status': 'ok', 'id': resultado.id})


@require_GET
def historial_sesiones(request):
    """Dashboard docente con analíticas y listado de sesiones."""
    resultados = ResultadoNarracion.objects.select_related('nino', 'cuento').order_by('-fecha')
    total = resultados.count()
    likes = resultados.filter(le_gusto=True).count()
    porcentaje_positivo = round((likes / total * 100), 1) if total > 0 else 0

    return render(request, 'narraciones/historial.html', {
        'resultados': resultados,
        'total': total,
        'likes': likes,
        'porcentaje_positivo': porcentaje_positivo
    })


@require_http_methods(["POST", "DELETE"])
def eliminar_sesion(request, sesion_id):
    """Elimina un registro específico del historial."""
    sesion = get_object_or_404(ResultadoNarracion, id=sesion_id)
    sesion.delete()
    return JsonResponse({'status': 'deleted'})


@require_GET
def exportar_pdf_nino(request, nino_id):
    """Genera informe pedagógico individual en formato PDF."""
    nino = get_object_or_404(Nino, id=nino_id)
    resultados = ResultadoNarracion.objects.filter(nino=nino).select_related('cuento').order_by('-fecha')

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
        p.drawString(1.5 * cm, y, r.cuento.titulo[:42])
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
def cargar_datos_ejemplo(request):
    """Carga alumnos y cuentos base con las opciones canónicas del modelo."""
    ninos_data = [
        {'nombre': 'Juan', 'apellido': 'Pérez', 'edad': 6, 'institucion_o_sala': 'Sala Roja'},
        {'nombre': 'María', 'apellido': 'García', 'edad': 5, 'institucion_o_sala': 'Sala Amarilla'},
        {'nombre': 'Liam', 'apellido': 'Rodríguez', 'edad': 7, 'institucion_o_sala': '1° Grado'},
    ]
    for n in ninos_data:
        Nino.objects.get_or_create(
            nombre=n['nombre'],
            apellido=n['apellido'],
            defaults={'edad': n['edad'], 'institucion_o_sala': n['institucion_o_sala']}
        )

    cuentos_data = [
        {
            'titulo': 'Caperucita Roja',
            'cuerpo_cuento': 'Había una vez una niña llamada Caperucita Roja que vivía cerca de un gran bosque...',
            'categoria_edad': '6-8'
        },
        {
            'titulo': 'Los Tres Cerditos',
            'cuerpo_cuento': 'Tres cerditos decidieron construir sus propias casas en el bosque...',
            'categoria_edad': '3-5'
        }
    ]
    for c in cuentos_data:
        Cuento.objects.get_or_create(
            titulo=c['titulo'],
            defaults={
                'cuerpo_cuento': c['cuerpo_cuento'],
                'categoria_edad': c['categoria_edad']
            }
        )

    return JsonResponse({
        'status': 'éxito',
        'mensaje': 'Datos de prueba cargados correctamente.'
    })


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