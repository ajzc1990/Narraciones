from django.core.management.base import BaseCommand

from narraciones.models import Nino
from narraciones.pictogramas_seed import cargar_pictogramas, actualizar_cuentos_demo
from narraciones.ml_pictogramas import entrenar_modelo


class Command(BaseCommand):
    """
    Reemplaza al viejo endpoint público '/cargar-datos/' (sin autenticación,
    accesible por cualquiera) por un comando de administración: carga niños,
    pictogramas y cuentos de ejemplo, y entrena el modelo de ML.

    Uso: python manage.py cargar_datos_demo
    """
    help = "Carga niños, pictogramas y cuentos de ejemplo, y entrena el modelo de ML (solo para demo/desarrollo)."

    def handle(self, *args, **options):
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

        pictogramas_creados, pictogramas_existentes = cargar_pictogramas()
        cuentos_completados = actualizar_cuentos_demo()

        try:
            n_ejemplos, n_clases = entrenar_modelo()
        except ValueError:
            n_ejemplos, n_clases = 0, 0

        self.stdout.write(self.style.SUCCESS(
            f"Niños de ejemplo: {len(ninos_data)} | "
            f"Pictogramas nuevos: {pictogramas_creados} (ya existentes: {pictogramas_existentes}) | "
            f"Cuentos actualizados: {cuentos_completados} | "
            f"Modelo ML: {n_ejemplos} ejemplos, {n_clases} clases"
        ))
