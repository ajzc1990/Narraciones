from django.core.management.base import BaseCommand

from narraciones.ml_pictogramas import entrenar_modelo


class Command(BaseCommand):
    help = "Entrena la red neuronal supervisada (RNF-05) que reconoce pictogramas por voz."

    def handle(self, *args, **options):
        try:
            n_ejemplos, n_clases = entrenar_modelo()
        except ValueError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Modelo entrenado con {n_ejemplos} ejemplos y {n_clases} pictogramas distintos."
        ))
