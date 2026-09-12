from django.core.management.base import BaseCommand

from narraciones.pictogramas_seed import cargar_pictogramas, actualizar_cuentos_demo


class Command(BaseCommand):
    help = "Genera pictogramas de ejemplo y completa los cuentos demo con su vocabulario."

    def handle(self, *args, **options):
        creados, existentes = cargar_pictogramas()
        cuentos_actualizados = actualizar_cuentos_demo()
        self.stdout.write(self.style.SUCCESS(
            f"Pictogramas nuevos: {creados} | ya existentes: {existentes} | "
            f"cuentos actualizados: {cuentos_actualizados}"
        ))
