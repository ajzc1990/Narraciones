"""
Validación automática de imágenes para pictogramas (RF-05).

La reglamentación exige que toda imagen sea apta para menores de 12 años.
Como el proyecto no puede depender de APIs de moderación pagas (RF-08), el
control se hace en dos pasos:

1. Validación técnica automática (formato, tamaño de archivo, resolución y
   proporción): se ejecuta sola al guardar el pictograma y descarta de forma
   automática archivos corruptos, demasiado pesados o con formatos no
   permitidos.
2. Aprobación humana explícita: un administrador debe marcar la casilla
   "Revisado / apto para menores" en el panel de administración. Mientras no
   esté marcada, el pictograma NUNCA se muestra durante una narración.
"""
from dataclasses import dataclass

from PIL import Image

FORMATOS_PERMITIDOS = {"JPEG", "PNG", "WEBP", "GIF"}
TAMANIO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5 MB
DIMENSION_MINIMA = 32
DIMENSION_MAXIMA = 4000
RELACION_ASPECTO_MAXIMA = 3.3  # evita imágenes recortadas de forma extrema


@dataclass
class ResultadoValidacion:
    valido: bool
    mensaje: str


def validar_imagen_tecnicamente(archivo_imagen) -> ResultadoValidacion:
    """Corre chequeos automáticos sobre el archivo de imagen de un pictograma."""
    try:
        archivo_imagen.seek(0)
        tamanio_bytes = archivo_imagen.size

        if tamanio_bytes > TAMANIO_MAXIMO_BYTES:
            return ResultadoValidacion(False, f"El archivo pesa {tamanio_bytes / 1_048_576:.1f}MB (máximo 5MB).")

        with Image.open(archivo_imagen) as img:
            formato = (img.format or "").upper()
            ancho, alto = img.size

            if formato not in FORMATOS_PERMITIDOS:
                return ResultadoValidacion(False, f"Formato '{formato}' no permitido (usar JPEG, PNG, WEBP o GIF).")

            if ancho < DIMENSION_MINIMA or alto < DIMENSION_MINIMA:
                return ResultadoValidacion(False, f"Imagen demasiado pequeña ({ancho}x{alto}px).")

            if ancho > DIMENSION_MAXIMA or alto > DIMENSION_MAXIMA:
                return ResultadoValidacion(False, f"Imagen demasiado grande ({ancho}x{alto}px).")

            relacion = max(ancho, alto) / max(min(ancho, alto), 1)
            if relacion > RELACION_ASPECTO_MAXIMA:
                return ResultadoValidacion(False, "Proporción de imagen demasiado extrema.")

        return ResultadoValidacion(True, "Validación técnica aprobada automáticamente.")

    except Exception as e:
        return ResultadoValidacion(False, f"No se pudo leer la imagen: {e}")
    finally:
        try:
            archivo_imagen.seek(0)
        except Exception:
            pass
