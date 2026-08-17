# narraciones/utils.py
import speech_recognition as sr
from typing import Optional


def procesar_voz_a_texto(timeout_segundos: int = 5, frase_limite: int = 10) -> Optional[str]:
    """
    Captura audio desde el micrófono, calibra el ruido ambiental
    y realiza reconocimiento offline con CMU Sphinx en español.
    """
    recognizer = sr.Recognizer()
    
    # Ajuste dinámico de sensibilidad
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8  # Tiempo de silencio para detectar fin de frase

    try:
        with sr.Microphone() as source:
            # Calibra el ruido de fondo durante 0.5 segundos
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print("🎤 Escuchando narración...")
            
            audio = recognizer.listen(
                source, 
                timeout=timeout_segundos, 
                phrase_time_limit=frase_limite
            )
            
            # Reconocimiento offline (es-ES)
            texto = recognizer.recognize_sphinx(audio, language="es-ES")
            return texto.strip().lower()

    except sr.WaitTimeoutError:
        print("⚠️ Tiempo de espera agotado sin detectar voz.")
        return None
    except sr.UnknownValueError:
        print("⚠️ No se pudo entender el audio.")
        return None
    except sr.RequestError as e:
        print(f"❌ Error en el motor Sphinx: {e}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return None