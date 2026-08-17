from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


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
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pictograma"
        verbose_name_plural = "Pictogramas"
        ordering = ['nombre_identificador']

    def __str__(self):
        return self.nombre_identificador

    def save(self, *args, **kwargs):
        self.nombre_identificador = self.nombre_identificador.strip()
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
    edad = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(18)],
        help_text="Edad entre 1 y 18 años"
    )
    institucion_o_sala = models.CharField(max_length=100, blank=True, help_text="Sala, curso o jardín al que asiste")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Niño"
        verbose_name_plural = "Niños"
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class ResultadoNarracion(models.Model):
    nino = models.ForeignKey(Nino, on_delete=models.SET_NULL, null=True, blank=True, related_name='resultados')
    cuento = models.ForeignKey(Cuento, on_delete=models.CASCADE, related_name='resultados')
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
        simbolo = "👍" if self.le_gusto else "👎"
        return f"{receptor} - {self.cuento.titulo} ({simbolo})"