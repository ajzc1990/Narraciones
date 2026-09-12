from django.core.management.base import BaseCommand

from narraciones.models import Pictograma
from narraciones.moderacion import validar_imagen_tecnicamente
from narraciones.pictogramas_seed import PICTOGRAMAS_DATA


class Command(BaseCommand):
    help = "Corre la validación técnica automática (RF-05) sobre los pictogramas ya existentes."

    def handle(self, *args, **options):
        nombres_confiables = {nombre for nombre, *_ in PICTOGRAMAS_DATA}
        actualizados = 0

        for pictograma in Pictograma.objects.all():
            if not pictograma.imagen:
                continue

            resultado = validar_imagen_tecnicamente(pictograma.imagen.file)
            pictograma.validacion_tecnica_ok = resultado.valido
            pictograma.alerta_contenido = "" if resultado.valido else resultado.mensaje

            if resultado.valido and pictograma.nombre_identificador in nombres_confiables:
                pictograma.revisado = True

            pictograma.save(update_fields=["validacion_tecnica_ok", "alerta_contenido", "revisado"])
            actualizados += 1
            estado = "APROBADO" if pictograma.apto_para_narracion else "PENDIENTE/RECHAZADO"
            self.stdout.write(f"  {pictograma.nombre_identificador}: {estado}")

        self.stdout.write(self.style.SUCCESS(f"Pictogramas revalidados: {actualizados}"))
