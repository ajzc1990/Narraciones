from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator


class Jardin(models.Model):
    """Institución/jardín de infantes que usa la plataforma (multi-institución)."""
    razon_social = models.CharField(max_length=150, unique=True)
    direccion = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    cuil = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text=(
            "Una institución que se autoregistra queda inactiva hasta que un administrador "
            "la aprueba; mientras tanto sus usuarios no pueden usar la aplicación."
        ),
    )
    aprobado_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jardín"
        verbose_name_plural = "Jardines"
        ordering = ['razon_social']

    def __str__(self):
        return self.razon_social

    def aprobar(self):
        from django.utils import timezone
        self.activo = True
        self.aprobado_en = timezone.now()
        self.save(update_fields=['activo', 'aprobado_en'])


class PerfilUsuario(models.Model):
    """Datos adicionales del tutor/usuario registrado (RF-02)."""
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil')
    edad = models.PositiveSmallIntegerField(validators=[MinValueValidator(16), MaxValueValidator(120)])
    jardin = models.ForeignKey(Jardin, on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios')
    es_admin_jardin = models.BooleanField(
        default=False,
        verbose_name="Administrador de la institución",
        help_text="Puede gestionar los demás usuarios (docentes) de su jardín, además de niños y sesiones.",
    )
    limite_logins_demo = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Límite de inicios de sesión (demo)",
        help_text=(
            "Si se completa, esta cuenta queda bloqueada despues de iniciar sesion esta "
            "cantidad de veces. Pensado para compartir un usuario de demostracion a varios "
            "prospectos sin que se use indefinidamente. Vacio = sin límite."
        ),
    )
    logins_demo_usados = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"

    def __str__(self):
        return f"Perfil de {self.usuario.username}"

    @property
    def demo_agotada(self):
        """True si esta cuenta tiene un límite de logins de demo y ya lo superó."""
        return self.limite_logins_demo is not None and self.logins_demo_usados > self.limite_logins_demo


class Pictograma(models.Model):
    TIPO_OPCIONES = [
        ('sustantivo', 'Sustantivo'),
        ('verbo', 'Verbo'),
        ('adjetivo', 'Adjetivo'),
        ('otro', 'Otro'),
    ]

    nombre_identificador = models.CharField(max_length=100, unique=True, help_text="Ej: Abuela")
    imagen = models.ImageField(upload_to='pictogramas/')
    tipo_imagen = models.CharField(max_length=45, choices=TIPO_OPCIONES, blank=True, default='sustantivo')
    revisado = models.BooleanField(
        default=False,
        verbose_name="Revisado y apto para menores",
        help_text="Un administrador debe confirmar esto manualmente antes de que el pictograma se use en narraciones (RF-05)."
    )
    validacion_tecnica_ok = models.BooleanField(default=False, editable=False)
    alerta_contenido = models.CharField(max_length=255, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pictograma"
        verbose_name_plural = "Pictogramas"
        ordering = ['nombre_identificador']

    def __str__(self):
        return self.nombre_identificador

    @property
    def apto_para_narracion(self):
        """Solo se proyecta durante una narración si pasó ambos controles (RF-05)."""
        return self.revisado and self.validacion_tecnica_ok

    def save(self, *args, **kwargs):
        from .moderacion import validar_imagen_tecnicamente

        self.nombre_identificador = self.nombre_identificador.strip()

        # No usamos imagen._committed para detectar una imagen nueva: cuando se
        # asigna con FieldFile.save(name, content, save=True) (como hace la carga
        # de pictogramas de ejemplo), Django ya marca _committed=True antes de
        # llamar a este save(), y la validación automática nunca se ejecutaría.
        # Comparamos contra el valor real guardado en la base de datos.
        if self.imagen:
            nombre_en_bd = (
                type(self).objects.filter(pk=self.pk).values_list('imagen', flat=True).first()
                if self.pk else None
            )
            imagen_es_nueva = self.imagen.name != nombre_en_bd
        else:
            imagen_es_nueva = False

        if imagen_es_nueva:
            resultado = validar_imagen_tecnicamente(self.imagen.file)
            self.validacion_tecnica_ok = resultado.valido
            self.alerta_contenido = "" if resultado.valido else resultado.mensaje
            if not resultado.valido:
                self.revisado = False

        super().save(*args, **kwargs)


class Sinonimo(models.Model):
    palabra = models.CharField(max_length=100, unique=True, db_index=True, help_text="Palabra clave o sinónimo (ej: abuelita)")
    pictograma = models.ForeignKey(Pictograma, on_delete=models.CASCADE, related_name='sinonimos')

    class Meta:
        verbose_name = "Sinónimo"
        verbose_name_plural = "Sinónimos"
        ordering = ['palabra']

    def __str__(self):
        return f"{self.palabra} -> {self.pictograma.nombre_identificador}"

    def save(self, *args, **kwargs):
        # Guardamos siempre en minúsculas y sin espacios extra para facilitar coincidencias
        self.palabra = self.palabra.strip().lower()
        super().save(*args, **kwargs)


class Cuento(models.Model):
    CATEGORIAS = [
        ('3-5', '3 a 5 años'),
        ('6-8', '6 a 8 años'),
        ('9-12', '9 a 12 años'),
    ]

    titulo = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True, null=True)
    descripcion = models.TextField(blank=True)
    cuerpo_cuento = models.TextField(help_text="Escribe aquí la historia completa")
    categoria_edad = models.CharField(max_length=10, choices=CATEGORIAS)
    imagen_portada = models.ImageField(upload_to='cuentos_portadas/', blank=True, null=True)
    imagen_final = models.ImageField(upload_to='finales/', blank=True, null=True, help_text="Imagen opcional que se muestra al terminar")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cuento"
        verbose_name_plural = "Cuentos"
        ordering = ['-creado_en']

    def __str__(self):
        return self.titulo


class Nino(models.Model):
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    dni = models.CharField(max_length=15, unique=True, null=True, blank=True, help_text="Documento del niño/a")
    domicilio = models.CharField(max_length=150, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    edad = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(18)],
        help_text="Edad entre 1 y 18 años"
    )
    institucion_o_sala = models.CharField(max_length=100, blank=True, help_text="Sala, curso o jardín al que asiste")
    jardin = models.ForeignKey(
        Jardin, on_delete=models.SET_NULL, null=True, blank=True, related_name='ninos',
        help_text="Institución a la que pertenece; determina quién puede verlo."
    )
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='ninos_a_cargo')
    autorizacion_parental = models.BooleanField(
        default=False,
        verbose_name="Autorización de padres/tutores registrada",
        help_text="Quien da de alta al niño/a confirma contar con la autorización de sus padres o tutores (precondición del CU Alta de Usuario)."
    )
    autorizacion_registrada_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Niño"
        verbose_name_plural = "Niños"
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    def save(self, *args, **kwargs):
        if self.autorizacion_parental and not self.autorizacion_registrada_en:
            from django.utils import timezone
            self.autorizacion_registrada_en = timezone.now()
        super().save(*args, **kwargs)


class ResultadoNarracion(models.Model):
    nino = models.ForeignKey(Nino, on_delete=models.SET_NULL, null=True, blank=True, related_name='resultados')
    cuento = models.ForeignKey(
        Cuento, on_delete=models.CASCADE, related_name='resultados', null=True, blank=True,
        help_text="Vacío cuando la sesión fue una narración libre (RF-09: 'narrar mi propia historia')."
    )
    fecha = models.DateTimeField(auto_now_add=True)
    le_gusto = models.BooleanField(help_text="Indica si al niño le gustó la narración")
    duracion_segundos = models.PositiveIntegerField(null=True, blank=True, help_text="Tiempo total de lectura/actividad")

    class Meta:
        verbose_name = "Resultado de Narración"
        verbose_name_plural = "Resultados de Narraciones"
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['cuento', 'fecha']),
        ]

    def __str__(self):
        receptor = f"{self.nino}" if self.nino else "Anónimo"
        titulo = self.cuento.titulo if self.cuento else "Historia libre"
        simbolo = "👍" if self.le_gusto else "👎"
        return f"{receptor} - {titulo} ({simbolo})"


class RegistroAuditoria(models.Model):
    """
    Trazabilidad de acciones sensibles sobre datos de menores: quién exportó
    un informe, quién dio de baja a un niño/a, etc. Solo de lectura desde la
    aplicación; se genera automáticamente.
    """
    ACCIONES = [
        ('crear_nino', 'Registró un niño/a'),
        ('editar_nino', 'Modificó datos de un niño/a'),
        ('eliminar_nino', 'Eliminó a un niño/a'),
        ('exportar_pdf', 'Exportó un informe en PDF'),
        ('importar_ninos_csv', 'Importó niños/as por CSV'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='acciones_auditadas'
    )
    accion = models.CharField(max_length=30, choices=ACCIONES)
    detalle = models.CharField(max_length=255, blank=True, help_text="Ej: nombre y DNI del niño/a afectado")
    jardin = models.ForeignKey(Jardin, on_delete=models.SET_NULL, null=True, blank=True, related_name='auditoria')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ['-fecha']

    def __str__(self):
        quien = self.usuario.username if self.usuario else "Usuario eliminado"
        return f"{self.fecha:%d/%m/%Y %H:%M} - {quien} - {self.get_accion_display()}"

    @classmethod
    def registrar(cls, usuario, accion, detalle=''):
        perfil = getattr(usuario, 'perfil', None)
        cls.objects.create(usuario=usuario, accion=accion, detalle=detalle, jardin=perfil.jardin if perfil else None)