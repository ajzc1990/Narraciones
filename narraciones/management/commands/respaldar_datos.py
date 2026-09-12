import io
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand
from django.apps import apps


class Command(BaseCommand):
    help = (
        "Genera un respaldo completo (base de datos + imágenes subidas) en un único .zip. "
        "Pensado para ejecutarse periódicamente (cron / tarea programada del hosting)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--destino', default=None,
            help="Carpeta donde guardar el .zip (por defecto: <proyecto>/backups/)."
        )

    def handle(self, *args, **options):
        destino = Path(options['destino']) if options['destino'] else Path(settings.BASE_DIR) / 'backups'
        destino.mkdir(parents=True, exist_ok=True)

        marca_tiempo = datetime.now().strftime('%Y%m%d_%H%M%S')
        ruta_zip = destino / f'respaldo_{marca_tiempo}.zip'

        # Serializa todos los datos de la app (no las tablas internas de Django/axes/sessions).
        modelos = apps.get_app_config('narraciones').get_models()
        objetos = []
        for modelo in modelos:
            objetos.extend(modelo.objects.all())

        buffer_datos = io.StringIO()
        serializers.serialize('json', objetos, stream=buffer_datos, indent=2)

        with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('datos.json', buffer_datos.getvalue())

            media_root = Path(settings.MEDIA_ROOT)
            if media_root.exists():
                for archivo in media_root.rglob('*'):
                    if archivo.is_file():
                        zf.write(archivo, arcname=str(Path('media') / archivo.relative_to(media_root)))

        tamanio_mb = ruta_zip.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"Respaldo creado: {ruta_zip} ({tamanio_mb:.1f} MB, {len(objetos)} registros)"
        ))
