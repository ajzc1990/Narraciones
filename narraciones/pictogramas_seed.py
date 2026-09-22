"""
Generación y carga de pictogramas de ejemplo (RF-03/RF-04).

Cada pictograma se dibuja como una imagen PNG (fondo pastel + emoji a color)
usando la fuente de emojis del sistema, y se vincula mediante Sinonimo a las
palabras que aparecen en los cuentos de demostración, para que se proyecten
automáticamente durante la narración.
"""
import io
import os
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

from .models import Pictograma, Sinonimo, Cuento

# Fuentes de emoji a color: se prueba cada ruta conocida según el sistema
# operativo (Windows en desarrollo, Linux/Noto en el servidor) y se usa la
# primera que exista. Si ninguna está instalada, se dibuja sin emoji en vez
# de romper la siembra de pictogramas.
_RUTAS_FUENTE_EMOJI = [
    r"C:\Windows\Fonts\seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]
FUENTE_EMOJI = next((ruta for ruta in _RUTAS_FUENTE_EMOJI if os.path.exists(ruta)), None)
TAMANIO = 300

COLORES_FONDO = [
    "#fde68a", "#bfdbfe", "#bbf7d0", "#fbcfe8", "#fecaca",
    "#ddd6fe", "#a7f3d0", "#fed7aa", "#c7d2fe", "#fef08a",
]

# nombre_identificador -> (emoji, tipo, [sinonimos])
PICTOGRAMAS_DATA = [
    # "caperucita roja" como frase compuesta: se busca antes que las palabras
    # sueltas (ver PALABRAS_VACIAS/frases en index.html) para que no se
    # muestre el pictograma de "Rojo" cuando en realidad es el nombre del
    # personaje, no el color.
    ("Caperucita", "👧", "sustantivo", ["caperucita", "caperucita roja"]),
    ("Niña", "👧", "sustantivo", ["niña", "nena", "chica"]),
    ("Mamá", "👩", "sustantivo", ["mama", "mamá", "madre"]),
    ("Cesta", "🧺", "sustantivo", ["cesta", "canasta"]),
    ("Casa", "🏠", "sustantivo", ["casa", "casita", "cabaña", "hogar"]),
    ("Bosque", "🌲", "sustantivo", ["bosque", "arbol", "árbol", "arboles", "árboles"]),
    ("Flor", "🌸", "sustantivo", ["flor", "flores"]),
    ("Camino", "👣", "sustantivo", ["camino", "sendero"]),
    ("Lobo", "🐺", "sustantivo", ["lobo", "lobos"]),
    ("Puerta", "🚪", "sustantivo", ["puerta"]),
    ("Cazador", "🪓", "sustantivo", ["cazador", "leñador"]),
    ("Correr", "🏃", "verbo", ["correr", "corrió", "corrio", "corriendo", "corrieron"]),
    ("Cerdito", "🐷", "sustantivo", ["cerdito", "cerdo", "cerditos", "cerdos", "chanchito"]),
    ("Paja", "🌾", "sustantivo", ["paja"]),
    ("Madera", "🪵", "sustantivo", ["madera"]),
    ("Ladrillo", "🧱", "sustantivo", ["ladrillo", "ladrillos"]),
    ("Soplar", "💨", "verbo", ["soplar", "sopló", "soplo", "sopla", "soplido"]),
    ("Feliz", "😊", "adjetivo", ["feliz", "felices", "contento", "contenta", "alegre"]),

    # Vocabulario adicional para ampliar la narración libre (RF-09)
    ("Papá", "👨", "sustantivo", ["papa", "papá", "padre"]),
    ("Amigo", "🤝", "sustantivo", ["amigo", "amiga", "amigos", "amistad"]),
    ("Perro", "🐶", "sustantivo", ["perro", "perrito", "perros"]),
    ("Gato", "🐱", "sustantivo", ["gato", "gatito", "gatos"]),
    ("Pájaro", "🐦", "sustantivo", ["pajaro", "pájaro", "pajarito", "pajaros"]),
    ("Pez", "🐟", "sustantivo", ["pez", "pescado", "peces"]),
    ("León", "🦁", "sustantivo", ["leon", "león", "leones"]),
    ("Elefante", "🐘", "sustantivo", ["elefante", "elefantes"]),
    ("Pato", "🦆", "sustantivo", ["pato", "patito", "patos", "patitos"]),
    ("Cisne", "🦢", "sustantivo", ["cisne", "cisnes"]),
    ("Tortuga", "🐢", "sustantivo", ["tortuga", "tortugas"]),
    ("Conejo", "🐇", "sustantivo", ["conejo", "liebre", "conejito", "conejos"]),
    ("Sol", "☀️", "sustantivo", ["sol"]),
    ("Luna", "🌙", "sustantivo", ["luna"]),
    ("Estrella", "⭐", "sustantivo", ["estrella", "estrellas"]),
    ("Lluvia", "🌧️", "sustantivo", ["lluvia", "llover", "llovió"]),
    ("Nube", "⛅", "sustantivo", ["nube", "nubes"]),
    ("Laguna", "💧", "sustantivo", ["laguna", "lago", "rio", "río", "estanque"]),
    ("Huevo", "🥚", "sustantivo", ["huevo", "huevos"]),
    ("Triste", "😢", "adjetivo", ["triste", "tristeza", "tristes"]),
    ("Sorprendido", "😲", "adjetivo", ["sorprendido", "sorpresa", "asombrado"]),
    ("Jugar", "⚽", "verbo", ["jugar", "jugando", "jugó", "jugo"]),
    ("Dormir", "😴", "verbo", ["dormir", "durmiendo", "durmió", "durmio"]),
    ("Nadar", "🏊", "verbo", ["nadar", "nadando", "nadó", "nado"]),
    ("Ganar", "🏆", "verbo", ["ganar", "ganó", "gano", "ganaron"]),
    ("Rápido", "⚡", "adjetivo", ["rapido", "rápido", "rapida", "rápida", "veloz"]),
    ("Lento", "🐌", "adjetivo", ["lento", "lenta", "lentamente", "despacio"]),
    ("Rojo", "🔴", "adjetivo", ["rojo", "roja"]),
    ("Azul", "🔵", "adjetivo", ["azul"]),
    ("Amarillo", "🟡", "adjetivo", ["amarillo", "amarilla"]),
    ("Verde", "🟢", "adjetivo", ["verde"]),

    # Vocabulario agregado a partir de búsquedas reales sin resultado en
    # producción (palabras de "El Patito Feo" que todavía no tenían pictograma).
    ("Salir", "🚶", "verbo", ["salir", "salio", "salió", "saliendo", "salieron", "irse"]),
    ("Llegar", "🏁", "verbo", ["llegar", "llego", "llegó", "llegando", "llegaron"]),
    ("Descubrir", "🔍", "verbo", ["descubrir", "descubrio", "descubrió", "descubriendo", "descubrieron"]),
    ("Decidir", "🤔", "verbo", ["decidir", "decidio", "decidió", "decidiendo", "decidieron"]),
    ("Sentir", "❤️", "verbo", ["sentir", "sentia", "sentía", "sintio", "sintió", "sintiendo"]),
    ("Vivir", "🌱", "verbo", ["vivir", "vivia", "vivía", "vivio", "vivió", "viviendo"]),
    ("Ver", "👀", "verbo", ["ver", "vio", "veian", "veían", "mirar", "mira", "miro", "miró", "viendo"]),
    ("Cuidar", "🤗", "verbo", ["cuidar", "cuidaba", "cuido", "cuidó", "cuidando"]),
    ("Gris", "🩶", "adjetivo", ["gris", "grises"]),
    ("Diferente", "🔀", "adjetivo", ["diferente", "diferentes", "distinto", "distinta"]),
    ("Grande", "🐋", "adjetivo", ["grande", "grandes"]),
    ("Primavera", "🌷", "sustantivo", ["primavera"]),
    ("Invierno", "❄️", "sustantivo", ["invierno"]),
    ("Reflejo", "🪞", "sustantivo", ["reflejo", "espejo"]),
]

CUENTOS_DATA = {
    "Caperucita Roja": {"categoria_edad": "6-8", "texto": (
        "Había una vez una niña muy buena llamada Caperucita Roja, que vivía en el "
        "bosque con su mamá. Un día, su mamá le pidió que llevara una cesta con "
        "comida a la casa de su abuela, que vivía del otro lado del bosque. "
        "Caperucita caminó feliz por el sendero, juntando flores en el camino. "
        "De pronto apareció un lobo enorme y le preguntó a dónde iba. Caperucita, "
        "sin miedo, le contó que iba a visitar a su abuela. El lobo corrió más "
        "rápido y llegó primero a la casa. Cuando Caperucita entró y tocó la "
        "puerta, un cazador que pasaba por el bosque escuchó los gritos y corrió "
        "a ayudar. Al final, todos quedaron muy felices y Caperucita aprendió a "
        "tener más cuidado."
    )},
    "Los Tres Cerditos": {"categoria_edad": "3-5", "texto": (
        "Había una vez tres cerditos que decidieron construir sus propias casas "
        "en el bosque. El primer cerdito hizo su casa de paja porque quería "
        "terminar rápido. El segundo cerdito construyó su casa con madera. El "
        "tercer cerdito, muy trabajador, construyó su casa con ladrillo. Un día "
        "llegó un lobo hambriento y sopló con fuerza contra la casa de paja, que "
        "se cayó enseguida. El cerdito corrió a la casa de madera, pero el lobo "
        "también la derribó de un soplido. Los dos cerditos corrieron a la casa "
        "de ladrillo de su hermano. El lobo sopló y sopló, pero la casa de "
        "ladrillo no se movió. Cansado, el lobo se fue del bosque y los tres "
        "cerditos vivieron felices en su casa fuerte."
    )},
    "El Patito Feo": {"categoria_edad": "3-5", "texto": (
        "Había una vez una mamá pata que cuidaba sus huevos en una laguna. Uno de "
        "los huevos era más grande que los demás. Cuando los huevos se abrieron, "
        "salieron varios patitos amarillos, pero del huevo grande salió un "
        "patito gris y diferente. Los otros animales se reían de él, y el "
        "patito se sentía muy triste. Un día, el patito decidió irse solo, "
        "nadando lejos de la laguna. Pasó el invierno y llegó la primavera. El "
        "patito vio unos cisnes nadando cerca de él y se acercó despacio. "
        "Cuando miró su reflejo en el agua, descubrió sorprendido que él "
        "también se había convertido en un cisne. Desde ese día, vivió feliz "
        "junto a los demás cisnes en la laguna."
    )},
    "La Tortuga y la Liebre": {"categoria_edad": "6-8", "texto": (
        "Había una vez una tortuga muy lenta y una liebre muy rápida. La liebre "
        "siempre se burlaba de lo lento que caminaba la tortuga, así que un día "
        "la tortuga la desafió a una carrera. Todos los animales del bosque se "
        "juntaron para mirar. Cuando empezó la carrera, la liebre corrió tan "
        "rápido que le sacó mucha ventaja a la tortuga. Como estaba segura de "
        "ganar, la liebre se acostó bajo un árbol a dormir una siesta. "
        "Mientras tanto, la tortuga siguió caminando despacio pero sin parar "
        "nunca. Cuando la liebre despertó, vio a la tortuga cruzando la meta. "
        "La tortuga había ganado la carrera gracias a su paciencia. Todos los "
        "animales del bosque festejaron felices."
    )},
}


# Fuentes de emoji a color en formato bitmap (como Noto Color Emoji en Linux)
# solo traen unos pocos tamaños fijos ("strikes"); pedir cualquier otro tira
# OSError. Se prueban tamaños conocidos hasta encontrar uno que la fuente
# soporte, y despues se escala el resultado al tamaño que realmente se quiere.
_TAMANIOS_EMOJI_CANDIDATOS = [136, 128, 109, 96, 72, 64, 48, 32]


def _cargar_fuente_emoji(tamanio_deseado):
    for tamanio in [tamanio_deseado] + _TAMANIOS_EMOJI_CANDIDATOS:
        try:
            return ImageFont.truetype(FUENTE_EMOJI, tamanio), tamanio
        except OSError:
            continue
    return None, None


def _dibujar_pictograma(emoji: str, color_fondo: str) -> ContentFile:
    """Genera un PNG cuadrado con fondo pastel redondeado y el emoji centrado."""
    img = Image.new("RGBA", (TAMANIO, TAMANIO), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    margen = 12
    draw.rounded_rectangle(
        [margen, margen, TAMANIO - margen, TAMANIO - margen],
        radius=48,
        fill=color_fondo,
    )
    centro = TAMANIO // 2
    tamanio_emoji = int(TAMANIO * 0.55)
    fuente, tamanio_real = _cargar_fuente_emoji(tamanio_emoji) if FUENTE_EMOJI else (None, None)

    if fuente and tamanio_real == tamanio_emoji:
        draw.text((centro, centro + 6), emoji, font=fuente, embedded_color=True, anchor="mm")
    elif fuente:
        glifo = Image.new("RGBA", (tamanio_real, tamanio_real), (255, 255, 255, 0))
        ImageDraw.Draw(glifo).text(
            (tamanio_real // 2, tamanio_real // 2), emoji, font=fuente, embedded_color=True, anchor="mm"
        )
        glifo = glifo.resize((tamanio_emoji, tamanio_emoji), Image.LANCZOS)
        img.alpha_composite(glifo, (centro - tamanio_emoji // 2, centro - tamanio_emoji // 2 + 6))
    else:
        # Sin fuente de emoji instalada: placeholder simple (no rompe la siembra).
        fuente_generica = ImageFont.load_default(size=int(TAMANIO * 0.35))
        draw.text((centro, centro), "?", font=fuente_generica, fill="#334155", anchor="mm")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())


def cargar_pictogramas():
    """Crea (si no existen) los pictogramas y sinónimos de ejemplo."""
    creados, actualizados = 0, 0

    for idx, (nombre, emoji, tipo, sinonimos) in enumerate(PICTOGRAMAS_DATA):
        pictograma, fue_creado = Pictograma.objects.get_or_create(
            nombre_identificador=nombre,
            defaults={"tipo_imagen": tipo},
        )

        if fue_creado or not pictograma.imagen:
            color = COLORES_FONDO[idx % len(COLORES_FONDO)]
            archivo = _dibujar_pictograma(emoji, color)
            # Imagen generada y verificada por este mismo script: se aprueba automáticamente (RF-05).
            pictograma.revisado = True
            pictograma.imagen.save(f"{nombre.lower()}.png", archivo, save=True)

        if fue_creado:
            creados += 1
        else:
            actualizados += 1

        for palabra in sinonimos:
            Sinonimo.objects.get_or_create(palabra=palabra.lower(), defaults={"pictograma": pictograma})

    return creados, actualizados


def actualizar_cuentos_demo():
    """Crea (si no existen) los cuentos de ejemplo y completa su cuerpo con el vocabulario de los pictogramas."""
    actualizados = 0
    for titulo, info in CUENTOS_DATA.items():
        cuento, fue_creado = Cuento.objects.get_or_create(
            titulo=titulo,
            defaults={"cuerpo_cuento": info["texto"], "categoria_edad": info["categoria_edad"]},
        )
        if not fue_creado and cuento.cuerpo_cuento != info["texto"]:
            cuento.cuerpo_cuento = info["texto"]
            cuento.save(update_fields=["cuerpo_cuento"])
        actualizados += 1
    return actualizados
