from django.apps import AppConfig


class NarracionesConfig(AppConfig):
    name = 'narraciones'

    def ready(self):
        from . import signals  # noqa: F401
