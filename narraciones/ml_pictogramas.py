"""
Reconocimiento de pictogramas por Machine Learning (RNF-05).

El diccionario de Sinónimos sigue siendo la primera vía de coincidencia
(exacta, instantánea y 100% predecible). Cuando una palabra dicha por el
niño/a no está cargada como sinónimo exacto, se consulta una red neuronal
(MLPClassifier de scikit-learn) entrenada de forma supervisada con los pares
palabra -> pictograma ya existentes en la base de datos. Así el sistema
generaliza a variantes, plurales o pequeños errores de dictado del
reconocimiento de voz sin depender de APIs pagas (RF-08).
"""
import unicodedata
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline

MODELO_DIR = Path(__file__).resolve().parent / "ml_models"
MODELO_PATH = MODELO_DIR / "clasificador_pictogramas.joblib"

# Confianza mínima para aceptar una predicción del modelo.
UMBRAL_CONFIANZA = 0.55

_modelo_cache = None


def _normalizar(texto: str) -> str:
    """Quita acentos y pasa a minúsculas para robustecer el entrenamiento."""
    texto = texto.strip().lower()
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_acentos


def _construir_dataset():
    """Arma (X, y) a partir de Sinonimo + el nombre_identificador de cada Pictograma."""
    from .models import Sinonimo, Pictograma

    textos, etiquetas = [], []
    for sinonimo in Sinonimo.objects.select_related('pictograma').all():
        textos.append(_normalizar(sinonimo.palabra))
        etiquetas.append(sinonimo.pictograma.nombre_identificador)

    for pictograma in Pictograma.objects.all():
        textos.append(_normalizar(pictograma.nombre_identificador))
        etiquetas.append(pictograma.nombre_identificador)

    return textos, etiquetas


def entrenar_modelo():
    """Entrena la red neuronal supervisada y la persiste en disco. Devuelve (n_ejemplos, n_clases)."""
    textos, etiquetas = _construir_dataset()
    clases = set(etiquetas)

    if len(textos) < 4 or len(clases) < 2:
        raise ValueError(
            "Se necesitan al menos 2 pictogramas con sinónimos cargados para entrenar el modelo."
        )

    pipeline = Pipeline([
        ("vectorizador", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)),
        ("red_neuronal", MLPClassifier(
            hidden_layer_sizes=(48,),
            activation="relu",
            solver="adam",
            alpha=1e-3,
            max_iter=2000,
            random_state=42,
        )),
    ])
    pipeline.fit(textos, etiquetas)

    MODELO_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODELO_PATH)

    global _modelo_cache
    _modelo_cache = pipeline

    return len(textos), len(clases)


def _cargar_modelo():
    global _modelo_cache
    if _modelo_cache is not None:
        return _modelo_cache
    if MODELO_PATH.exists():
        _modelo_cache = joblib.load(MODELO_PATH)
        return _modelo_cache
    return None


def predecir_pictograma(palabra: str):
    """
    Devuelve (nombre_identificador, confianza) si la red neuronal reconoce la
    palabra con suficiente confianza, o None si no hay modelo entrenado o la
    predicción es poco confiable.
    """
    modelo = _cargar_modelo()
    if modelo is None:
        return None

    texto = _normalizar(palabra)
    probabilidades = modelo.predict_proba([texto])[0]
    clases = modelo.classes_
    indice_max = probabilidades.argmax()
    confianza = float(probabilidades[indice_max])

    if confianza < UMBRAL_CONFIANZA:
        return None

    return clases[indice_max], confianza
