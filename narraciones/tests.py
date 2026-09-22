import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from . import ml_pictogramas
from .models import Cuento, Jardin, Nino, PerfilUsuario, Pictograma, RegistroAuditoria, ResultadoNarracion, Sinonimo


def _imagen_valida(color='red', size=(200, 200)):
    """Genera un PNG válido en memoria para usar como imagen de Pictograma en los tests."""
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name='test.png')


def crear_pictograma(nombre, palabras, revisado=True, color='red'):
    """Crea un Pictograma aprobado (o no) con sus sinónimos, listo para búsquedas."""
    pictograma = Pictograma.objects.create(nombre_identificador=nombre, tipo_imagen='sustantivo')
    pictograma.imagen.save(f'{nombre.lower()}.png', _imagen_valida(color=color), save=False)
    pictograma.revisado = revisado
    pictograma.save()
    for palabra in palabras:
        Sinonimo.objects.get_or_create(palabra=palabra, defaults={'pictograma': pictograma})
    return pictograma


class RegistroLoginTests(TestCase):
    """RF-01 / RF-02: autenticación y registro de usuario."""

    def _datos_registro(self, **overrides):
        datos = {
            'first_name': 'Ana', 'last_name': 'Lopez', 'edad': 30,
            'email': 'ana@example.com', 'username': 'anatest',
            'jardin_nombre': 'Jardín Solcito',
            'password1': 'ContraseñaSegura123', 'password2': 'ContraseñaSegura123',
        }
        datos.update(overrides)
        return datos

    def test_password_menor_a_10_caracteres_es_rechazada(self):
        response = self.client.post(reverse('narraciones:registro'), self._datos_registro(
            password1='abc123', password2='abc123'
        ))
        self.assertEqual(response.status_code, 200)  # vuelve a mostrar el form, no redirige
        self.assertFalse(User.objects.filter(username='anatest').exists())

    def test_registro_valido_crea_usuario_y_loguea_automaticamente(self):
        # La institución es nueva: queda pendiente de aprobación (el redirect a /menu/
        # del view termina en la pantalla de "pendiente" por el middleware de gating).
        response = self.client.post(reverse('narraciones:registro'), self._datos_registro(), follow=True)
        self.assertRedirects(response, reverse('narraciones:jardin_pendiente'))
        self.assertTrue(User.objects.filter(username='anatest').exists())
        usuario = User.objects.get(username='anatest')
        self.assertTrue(hasattr(usuario, 'perfil'))
        self.assertEqual(usuario.perfil.edad, 30)
        self.assertEqual(usuario.perfil.jardin.razon_social, 'Jardín Solcito')
        self.assertFalse(usuario.perfil.jardin.activo)
        # Quien da de alta una institución nueva queda como su administrador.
        self.assertTrue(usuario.perfil.es_admin_jardin)

    def test_dos_usuarios_con_mismo_nombre_de_jardin_comparten_institucion(self):
        self.client.post(reverse('narraciones:registro'), self._datos_registro(
            username='anatest', email='ana@example.com', jardin_nombre='Jardín Compartido'
        ))
        self.client.logout()
        self.client.post(reverse('narraciones:registro'), self._datos_registro(
            username='bertest', email='ber@example.com', jardin_nombre='jardín compartido'
        ))
        ana = User.objects.get(username='anatest')
        ber = User.objects.get(username='bertest')
        self.assertEqual(ana.perfil.jardin_id, ber.perfil.jardin_id)

    def test_paginas_protegidas_redirigen_a_login_si_no_hay_sesion(self):
        for nombre_url in ['narraciones:index', 'narraciones:menu', 'narraciones:historial_sesiones', 'narraciones:nino_lista']:
            response = self.client.get(reverse(nombre_url))
            self.assertEqual(response.status_code, 302, f'{nombre_url} debería redirigir sin sesión')
            self.assertIn(reverse('narraciones:login'), response.url)

    def test_cerrar_sesion_es_por_post_no_por_get(self):
        """Django rechaza logout por GET (405): los templates deben usar un form POST, no un <a href>."""
        usuario = User.objects.create_user('paracerrar', password='ContraseñaSegura123')
        self.client.force_login(usuario)

        response = self.client.get(reverse('narraciones:logout'))
        self.assertEqual(response.status_code, 405)

        response = self.client.post(reverse('narraciones:logout'))
        self.assertRedirects(response, reverse('narraciones:landing'))
        self.assertNotIn('_auth_user_id', self.client.session)


class NinoCRUDTests(TestCase):
    """RF-07: alta, modificación y baja de niños."""

    def setUp(self):
        self.usuario = User.objects.create_user('tutor', password='ContraseñaSegura123')
        self.client.force_login(self.usuario)

    def test_alta_nino_con_campos_completos(self):
        response = self.client.post(reverse('narraciones:nino_alta'), {
            'nombre': 'Tomás', 'apellido': 'Díaz', 'dni': '45123456',
            'telefono': '3811234567', 'domicilio': 'Calle Falsa 123',
            'fecha_nacimiento': '2018-05-10', 'edad': 7, 'institucion_o_sala': 'Sala Verde',
            'autorizacion_parental': 'on',
        })
        self.assertRedirects(response, reverse('narraciones:nino_lista'))
        nino = Nino.objects.get(dni='45123456')
        self.assertEqual(nino.tutor, self.usuario)
        self.assertEqual(nino.domicilio, 'Calle Falsa 123')
        self.assertTrue(nino.autorizacion_parental)
        self.assertIsNotNone(nino.autorizacion_registrada_en)

    def test_alta_nino_sin_autorizacion_parental_falla(self):
        response = self.client.post(reverse('narraciones:nino_alta'), {
            'nombre': 'Tomás', 'apellido': 'Díaz', 'dni': '45123457',
            'telefono': '', 'domicilio': '', 'fecha_nacimiento': '', 'edad': 7, 'institucion_o_sala': '',
        })
        self.assertEqual(response.status_code, 200)  # vuelve a mostrar el form, no redirige
        self.assertFalse(Nino.objects.filter(dni='45123457').exists())

    def test_editar_nino(self):
        nino = Nino.objects.create(nombre='Tomás', apellido='Díaz', edad=7, dni='1')
        response = self.client.post(reverse('narraciones:nino_editar', args=[nino.id]), {
            'nombre': 'Tomás', 'apellido': 'Díaz', 'dni': '1',
            'telefono': '', 'domicilio': 'Nueva Dirección', 'fecha_nacimiento': '',
            'edad': 8, 'institucion_o_sala': '', 'autorizacion_parental': 'on',
        })
        self.assertRedirects(response, reverse('narraciones:nino_lista'))
        nino.refresh_from_db()
        self.assertEqual(nino.domicilio, 'Nueva Dirección')
        self.assertEqual(nino.edad, 8)

    def test_eliminar_nino(self):
        nino = Nino.objects.create(nombre='Tomás', apellido='Díaz', edad=7, dni='2')
        response = self.client.post(reverse('narraciones:nino_eliminar', args=[nino.id]))
        self.assertRedirects(response, reverse('narraciones:nino_lista'))
        self.assertFalse(Nino.objects.filter(id=nino.id).exists())

    def test_busqueda_por_dni(self):
        Nino.objects.create(nombre='Tomás', apellido='Díaz', edad=7, dni='99999')
        Nino.objects.create(nombre='Otra', apellido='Persona', edad=5, dni='11111')
        response = self.client.get(reverse('narraciones:nino_lista'), {'q': '99999'})
        self.assertContains(response, 'Díaz')
        self.assertNotContains(response, 'Persona')


class NinoImportarCSVTests(TestCase):
    """Alta masiva de niños por CSV, para instituciones con muchos alumnos."""

    def setUp(self):
        self.jardin = Jardin.objects.create(razon_social='Jardín CSV')
        self.usuario = User.objects.create_user('docente_csv', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=self.usuario, edad=30, jardin=self.jardin)
        self.client.force_login(self.usuario)

    def _csv(self, filas):
        encabezado = 'nombre,apellido,dni,telefono,domicilio,fecha_nacimiento,edad,institucion_o_sala,autorizacion_parental'
        contenido = '\n'.join([encabezado] + filas)
        return ContentFile(contenido.encode('utf-8'), name='ninos.csv')

    def test_importa_filas_validas_con_autorizacion(self):
        archivo = self._csv([
            'Juan,Pérez,111,,,,7,Sala Roja,si',
            'María,García,222,,,,5,Sala Amarilla,1',
        ])
        response = self.client.post(reverse('narraciones:nino_importar'), {'archivo_csv': archivo})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['creados'], 2)
        self.assertEqual(Nino.objects.filter(jardin=self.jardin).count(), 2)
        nino = Nino.objects.get(dni='111')
        self.assertTrue(nino.autorizacion_parental)
        self.assertEqual(nino.jardin, self.jardin)
        self.assertEqual(nino.tutor, self.usuario)

    def test_rechaza_fila_sin_autorizacion_parental(self):
        archivo = self._csv([
            'Juan,Pérez,333,,,,7,Sala Roja,no',
            'María,García,444,,,,5,Sala Amarilla,',
        ])
        response = self.client.post(reverse('narraciones:nino_importar'), {'archivo_csv': archivo})
        self.assertEqual(response.context['creados'], 0)
        self.assertEqual(len(response.context['errores']), 2)
        self.assertFalse(Nino.objects.filter(dni__in=['333', '444']).exists())

    def test_fila_invalida_no_bloquea_las_validas(self):
        archivo = self._csv([
            'Juan,Pérez,555,,,,7,Sala Roja,si',
            ',,,,,, ,,si',  # fila vacia / invalida
        ])
        response = self.client.post(reverse('narraciones:nino_importar'), {'archivo_csv': archivo})
        self.assertEqual(response.context['creados'], 1)
        self.assertEqual(len(response.context['errores']), 1)
        self.assertTrue(Nino.objects.filter(dni='555').exists())

    def test_queda_registrado_en_auditoria(self):
        archivo = self._csv(['Juan,Pérez,666,,,,7,Sala Roja,si'])
        self.client.post(reverse('narraciones:nino_importar'), {'archivo_csv': archivo})
        self.assertTrue(RegistroAuditoria.objects.filter(accion='importar_ninos_csv').exists())

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse('narraciones:nino_importar'))
        self.assertEqual(response.status_code, 302)

    def test_descargar_plantilla(self):
        response = self.client.get(reverse('narraciones:nino_importar_plantilla'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        contenido = response.content.decode('utf-8')
        self.assertIn('autorizacion_parental', contenido)


class BusquedaPictogramaTests(TestCase):
    """RF-03/RF-04: reconocimiento de pictogramas por palabra, y RF-05: moderación."""

    def setUp(self):
        self.usuario = User.objects.create_user('docente', password='ContraseñaSegura123')
        self.client.force_login(self.usuario)

    def test_coincidencia_exacta_por_sinonimo(self):
        crear_pictograma('Lobo', ['lobo', 'lobos'])
        response = self.client.get(reverse('narraciones:buscar_pictograma'), {'palabra': 'lobo'})
        data = response.json()
        self.assertTrue(data['encontrado'])
        self.assertEqual(data['nombre'], 'Lobo')
        self.assertEqual(data['origen'], 'diccionario')

    def test_palabra_sin_pictograma_no_encontrada(self):
        response = self.client.get(reverse('narraciones:buscar_pictograma'), {'palabra': 'xyzabc'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['encontrado'])

    def test_frase_compuesta_matchea_por_sinonimo_de_frase(self):
        """Un nombre propio como 'Caperucita Roja' tiene que reconocerse como frase."""
        crear_pictograma('Caperucita', ['caperucita', 'caperucita roja'])
        response = self.client.get(reverse('narraciones:buscar_pictograma'), {'palabra': 'caperucita roja'})
        data = response.json()
        self.assertTrue(data['encontrado'])
        self.assertEqual(data['nombre'], 'Caperucita')

    def test_frase_sin_coincidencia_exacta_no_usa_la_red_neuronal(self):
        """Una frase de varias palabras sin sinonimo exacto no debe caer en el
        modelo de ML (entrenado con palabras sueltas): podria matchear falso
        por pura similitud de caracteres (ej. 'una' contra 'Luna')."""
        crear_pictograma('Rojo', ['rojo', 'roja'])
        with patch('narraciones.views.predecir_pictograma') as mock_predecir:
            mock_predecir.return_value = ('Rojo', 0.99)  # aunque "encontraria" algo, no debe ni llamarse
            response = self.client.get(reverse('narraciones:buscar_pictograma'), {'palabra': 'caperucita roja'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['encontrado'])
        mock_predecir.assert_not_called()

    def test_pictograma_no_revisado_no_aparece_en_narracion(self):
        """RF-05: una imagen recién subida no debe usarse hasta ser aprobada manualmente."""
        crear_pictograma('Casa', ['casa'], revisado=False)
        response = self.client.get(reverse('narraciones:buscar_pictograma'), {'palabra': 'casa'})
        self.assertEqual(response.status_code, 404)

    def test_imagen_invalida_no_se_aprueba_tecnicamente(self):
        pictograma = Pictograma.objects.create(nombre_identificador='Rota', tipo_imagen='otro')
        pictograma.imagen.save('rota.png', ContentFile(b'esto-no-es-una-imagen'), save=False)
        pictograma.revisado = True
        pictograma.save()
        self.assertFalse(pictograma.validacion_tecnica_ok)
        self.assertFalse(pictograma.apto_para_narracion)


class RedNeuronalTests(TestCase):
    """RNF-05: la red neuronal supervisada reconoce variantes no cargadas como sinónimo."""

    def setUp(self):
        self.usuario = User.objects.create_user('docente2', password='ContraseñaSegura123')
        self.client.force_login(self.usuario)
        crear_pictograma('Cerdito', ['cerdito', 'cerdo', 'cerditos', 'chanchito'], color='pink')
        crear_pictograma('Bosque', ['bosque', 'arbol', 'arboles'], color='green')

        self._tmp_dir = tempfile.TemporaryDirectory()
        self._patcher_path = patch.object(ml_pictogramas, 'MODELO_PATH', Path(self._tmp_dir.name) / 'modelo.joblib')
        self._patcher_path.start()
        ml_pictogramas._modelo_cache = None

    def tearDown(self):
        self._patcher_path.stop()
        ml_pictogramas._modelo_cache = None
        self._tmp_dir.cleanup()

    def test_reconoce_variante_no_cargada_como_sinonimo(self):
        ml_pictogramas.entrenar_modelo()
        resultado = ml_pictogramas.predecir_pictograma('cerdita')
        self.assertIsNotNone(resultado)
        nombre, confianza = resultado
        self.assertEqual(nombre, 'Cerdito')
        self.assertGreaterEqual(confianza, ml_pictogramas.UMBRAL_CONFIANZA)

    def test_buscar_pictograma_usa_la_red_neuronal_como_respaldo(self):
        ml_pictogramas.entrenar_modelo()
        response = self.client.get(reverse('narraciones:buscar_pictograma'), {'palabra': 'cerdita'})
        data = response.json()
        self.assertTrue(data['encontrado'])
        self.assertEqual(data['origen'], 'red_neuronal')

    def test_sin_modelo_entrenado_no_hay_prediccion(self):
        resultado = ml_pictogramas.predecir_pictograma('cerdita')
        self.assertIsNone(resultado)


class NarracionLibreTests(TestCase):
    """RF-09: narrar una historia propia, sin cuento asociado."""

    def setUp(self):
        self.usuario = User.objects.create_user('tutor2', password='ContraseñaSegura123')
        self.client.force_login(self.usuario)
        self.nino = Nino.objects.create(nombre='Sofía', apellido='Test', edad=6, dni='777')

    def test_finalizar_libre_carga_sin_cuento(self):
        response = self.client.get(reverse('narraciones:finalizar_libre'), {'nino_id': self.nino.id})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['cuento'])

    def test_registrar_voto_sin_cuento_id_crea_resultado_sin_cuento(self):
        response = self.client.post(
            reverse('narraciones:registrar_voto'),
            data=json.dumps({'cuento_id': None, 'nino_id': self.nino.id, 'voto': True, 'duracion_segundos': 30}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        resultado = ResultadoNarracion.objects.get(id=response.json()['id'])
        self.assertIsNone(resultado.cuento)
        self.assertEqual(resultado.nino, self.nino)

    def test_registrar_voto_sin_voto_falla(self):
        response = self.client.post(
            reverse('narraciones:registrar_voto'),
            data=json.dumps({'cuento_id': None, 'nino_id': self.nino.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class HistorialTests(TestCase):
    """Dashboard docente: estadísticas y listado de sesiones."""

    def setUp(self):
        self.usuario = User.objects.create_user('tutor3', password='ContraseñaSegura123')
        self.client.force_login(self.usuario)
        self.cuento = Cuento.objects.create(titulo='Cuento Test', cuerpo_cuento='...', categoria_edad='3-5')
        self.nino = Nino.objects.create(nombre='Leo', apellido='Test', edad=5, dni='888')

    def test_historial_cuenta_likes_y_dislikes(self):
        ResultadoNarracion.objects.create(cuento=self.cuento, nino=self.nino, le_gusto=True)
        ResultadoNarracion.objects.create(cuento=self.cuento, nino=self.nino, le_gusto=True)
        ResultadoNarracion.objects.create(cuento=None, nino=self.nino, le_gusto=False)

        response = self.client.get(reverse('narraciones:historial_sesiones'))
        self.assertEqual(response.context['total'], 3)
        self.assertEqual(response.context['likes'], 2)
        self.assertContains(response, 'Historia libre')

    def test_historial_incluye_top_ninos_y_cuentos(self):
        otro_nino = Nino.objects.create(nombre='Ana', apellido='Test', edad=6, dni='889')
        ResultadoNarracion.objects.create(cuento=self.cuento, nino=self.nino, le_gusto=True)
        ResultadoNarracion.objects.create(cuento=self.cuento, nino=self.nino, le_gusto=True)
        ResultadoNarracion.objects.create(cuento=self.cuento, nino=otro_nino, le_gusto=False)

        response = self.client.get(reverse('narraciones:historial_sesiones'))

        top_ninos = list(response.context['top_ninos'])
        self.assertEqual(top_ninos[0]['nino_id'], self.nino.id)
        self.assertEqual(top_ninos[0]['sesiones'], 2)

        top_cuentos = list(response.context['top_cuentos'])
        self.assertEqual(top_cuentos[0]['cuento_id'], self.cuento.id)
        self.assertEqual(top_cuentos[0]['sesiones'], 3)
        self.assertEqual(top_cuentos[0]['likes'], 2)

        self.assertIn('sesiones_por_dia_json', response.context)
        import json
        dias = json.loads(response.context['sesiones_por_dia_json'])
        self.assertEqual(len(dias), 14)
        self.assertEqual(sum(d['sesiones'] for d in dias), 3)


class JardinAislamientoTests(TestCase):
    """Multi-institución: los datos de un jardín no deben ser visibles para otro."""

    def setUp(self):
        self.jardin_a = Jardin.objects.create(razon_social='Jardín A')
        self.jardin_b = Jardin.objects.create(razon_social='Jardín B')

        self.usuario_a = User.objects.create_user('tutora', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=self.usuario_a, edad=30, jardin=self.jardin_a)

        self.usuario_b = User.objects.create_user('tutorb', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=self.usuario_b, edad=30, jardin=self.jardin_b)

        self.nino_a = Nino.objects.create(nombre='NiñoA', apellido='Test', edad=5, dni='111', jardin=self.jardin_a)
        self.nino_b = Nino.objects.create(nombre='NiñoB', apellido='Test', edad=5, dni='222', jardin=self.jardin_b)

    def test_lista_de_ninos_no_muestra_los_de_otro_jardin(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse('narraciones:nino_lista'))
        self.assertContains(response, 'NiñoA')
        self.assertNotContains(response, 'NiñoB')

    def test_no_se_puede_editar_nino_de_otro_jardin_por_url(self):
        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse('narraciones:nino_editar', args=[self.nino_b.id]))
        self.assertEqual(response.status_code, 404)

    def test_no_se_puede_eliminar_nino_de_otro_jardin_por_url(self):
        self.client.force_login(self.usuario_a)
        response = self.client.post(reverse('narraciones:nino_eliminar', args=[self.nino_b.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Nino.objects.filter(id=self.nino_b.id).exists())

    def test_historial_no_mezcla_sesiones_de_otro_jardin(self):
        cuento = Cuento.objects.create(titulo='Cuento Compartido', cuerpo_cuento='...', categoria_edad='3-5')
        ResultadoNarracion.objects.create(cuento=cuento, nino=self.nino_a, le_gusto=True)
        ResultadoNarracion.objects.create(cuento=cuento, nino=self.nino_b, le_gusto=True)

        self.client.force_login(self.usuario_a)
        response = self.client.get(reverse('narraciones:historial_sesiones'))
        self.assertEqual(response.context['total'], 1)

    def test_alta_de_nino_queda_asignada_al_jardin_del_usuario(self):
        self.client.force_login(self.usuario_a)
        self.client.post(reverse('narraciones:nino_alta'), {
            'nombre': 'Nuevo', 'apellido': 'Alumno', 'dni': '333',
            'telefono': '', 'domicilio': '', 'fecha_nacimiento': '', 'edad': 6, 'institucion_o_sala': '',
            'autorizacion_parental': 'on',
        })
        nuevo = Nino.objects.get(dni='333')
        self.assertEqual(nuevo.jardin, self.jardin_a)


class AuditoriaTests(TestCase):
    """Trazabilidad de acciones sensibles sobre datos de menores."""

    def setUp(self):
        self.usuario = User.objects.create_user('auditor', password='ContraseñaSegura123')
        self.client.force_login(self.usuario)

    def test_alta_de_nino_queda_registrada_en_auditoria(self):
        self.client.post(reverse('narraciones:nino_alta'), {
            'nombre': 'Con', 'apellido': 'Auditoria', 'dni': '999',
            'telefono': '', 'domicilio': '', 'fecha_nacimiento': '', 'edad': 6, 'institucion_o_sala': '',
            'autorizacion_parental': 'on',
        })
        registro = RegistroAuditoria.objects.get(accion='crear_nino')
        self.assertEqual(registro.usuario, self.usuario)
        self.assertIn('999', registro.detalle)

    def test_eliminar_nino_queda_registrado_en_auditoria(self):
        nino = Nino.objects.create(nombre='A', apellido='Borrar', edad=5, dni='998')
        self.client.post(reverse('narraciones:nino_eliminar', args=[nino.id]))
        registro = RegistroAuditoria.objects.get(accion='eliminar_nino')
        self.assertIn('998', registro.detalle)

    def test_exportar_pdf_queda_registrado_en_auditoria(self):
        nino = Nino.objects.create(nombre='A', apellido='Exportar', edad=5, dni='997')
        self.client.get(reverse('narraciones:exportar_pdf', args=[nino.id]))
        self.assertTrue(RegistroAuditoria.objects.filter(accion='exportar_pdf', detalle__contains='997').exists())


class JardinPendienteTests(TestCase):
    """Alta de institución por autoservicio: queda inactiva hasta que un admin la aprueba."""

    def setUp(self):
        self.jardin = Jardin.objects.create(razon_social='Jardín Nuevo', activo=False)
        self.usuario = User.objects.create_user('pendiente', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=self.usuario, edad=30, jardin=self.jardin, es_admin_jardin=True)
        self.client.force_login(self.usuario)

    def test_usuario_de_jardin_pendiente_no_puede_usar_la_app(self):
        response = self.client.get(reverse('narraciones:menu'))
        self.assertRedirects(response, reverse('narraciones:jardin_pendiente'))

    def test_usuario_de_jardin_pendiente_puede_ver_la_pantalla_de_espera(self):
        response = self.client.get(reverse('narraciones:jardin_pendiente'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jardín Nuevo')

    def test_tras_aprobar_el_jardin_el_usuario_recupera_el_acceso(self):
        self.jardin.aprobar()
        response = self.client.get(reverse('narraciones:menu'))
        self.assertEqual(response.status_code, 200)


class JardinEquipoTests(TestCase):
    """Panel del administrador de institución: gestión de docentes del propio jardín."""

    def setUp(self):
        self.jardin = Jardin.objects.create(razon_social='Jardín Equipo', activo=True)
        self.admin = User.objects.create_user('directora', password='ContraseñaSegura123')
        self.perfil_admin = PerfilUsuario.objects.create(
            usuario=self.admin, edad=40, jardin=self.jardin, es_admin_jardin=True
        )
        self.docente = User.objects.create_user('docente', password='ContraseñaSegura123')
        self.perfil_docente = PerfilUsuario.objects.create(
            usuario=self.docente, edad=28, jardin=self.jardin, es_admin_jardin=False
        )

    def test_docente_no_puede_acceder_al_panel_de_equipo(self):
        self.client.force_login(self.docente)
        response = self.client.get(reverse('narraciones:jardin_equipo'))
        self.assertRedirects(response, reverse('narraciones:menu'))

    def test_admin_ve_a_los_docentes_de_su_jardin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('narraciones:jardin_equipo'))
        self.assertContains(response, 'docente')

    def test_admin_puede_promover_a_otro_docente(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('narraciones:jardin_equipo_actualizar', args=[self.docente.id]),
            {'accion': 'hacer_admin'},
        )
        self.perfil_docente.refresh_from_db()
        self.assertTrue(self.perfil_docente.es_admin_jardin)

    def test_admin_puede_desactivar_a_un_docente(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('narraciones:jardin_equipo_actualizar', args=[self.docente.id]),
            {'accion': 'desactivar'},
        )
        self.docente.refresh_from_db()
        self.assertFalse(self.docente.is_active)

    def test_admin_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('narraciones:jardin_equipo_actualizar', args=[self.admin.id]),
            {'accion': 'desactivar'},
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_no_puede_quitarse_el_rol_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse('narraciones:jardin_equipo_actualizar', args=[self.admin.id]),
            {'accion': 'quitar_admin'},
        )
        self.perfil_admin.refresh_from_db()
        self.assertTrue(self.perfil_admin.es_admin_jardin)

    def test_no_puede_actuar_sobre_un_usuario_de_otro_jardin(self):
        otro_jardin = Jardin.objects.create(razon_social='Otro Jardín', activo=True)
        ajeno = User.objects.create_user('ajeno', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=ajeno, edad=30, jardin=otro_jardin)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('narraciones:jardin_equipo_actualizar', args=[ajeno.id]),
            {'accion': 'desactivar'},
        )
        self.assertEqual(response.status_code, 404)
        ajeno.refresh_from_db()
        self.assertTrue(ajeno.is_active)


class DemoLimiteLoginTests(TestCase):
    """Cuenta de demostración compartida: se bloquea tras superar los inicios de sesión permitidos."""

    def setUp(self):
        self.usuario = User.objects.create_user('cuenta_demo', password='ContraseñaSegura123')
        self.perfil = PerfilUsuario.objects.create(usuario=self.usuario, edad=30, limite_logins_demo=3)

    def _loguear_y_cerrar(self):
        # force_login evita pasar por AxesBackend (que exige un request real a
        # authenticate()), pero sigue emitiendo la señal user_logged_in que
        # cuenta los usos, igual que un login real por formulario.
        self.client.force_login(self.usuario)
        self.client.logout()

    def test_permite_usar_la_cuenta_hasta_el_limite(self):
        for _ in range(3):
            self.client.force_login(self.usuario)
            response = self.client.get(reverse('narraciones:menu'))
            self.assertEqual(response.status_code, 200)
            self.client.logout()

    def test_bloquea_al_superar_el_limite(self):
        for _ in range(3):
            self._loguear_y_cerrar()

        self.client.force_login(self.usuario)
        response = self.client.get(reverse('narraciones:menu'))
        self.assertRedirects(response, reverse('narraciones:demo_agotada'))

    def test_pantalla_de_demo_agotada_se_puede_ver_y_cerrar_sesion(self):
        for _ in range(3):
            self._loguear_y_cerrar()
        self.client.force_login(self.usuario)

        response = self.client.get(reverse('narraciones:demo_agotada'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('narraciones:logout'))
        self.assertRedirects(response, reverse('narraciones:landing'))

    def test_cuenta_sin_limite_configurado_no_se_bloquea(self):
        otro = User.objects.create_user('sin_limite', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=otro, edad=30)
        for _ in range(10):
            self.client.force_login(otro)
            self.client.logout()
        self.client.force_login(otro)
        response = self.client.get(reverse('narraciones:menu'))
        self.assertEqual(response.status_code, 200)

    def test_admin_puede_reiniciar_el_contador(self):
        for _ in range(3):
            self._loguear_y_cerrar()
        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.logins_demo_usados, 3)

        PerfilUsuario.objects.filter(id=self.perfil.id).update(logins_demo_usados=0)
        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.demo_agotada)


class PanelSuperadminTests(TestCase):
    """Panel global de instituciones, solo para el equipo que opera la plataforma."""

    def setUp(self):
        self.jardin_activo = Jardin.objects.create(razon_social='Jardín Activo', activo=True)
        self.jardin_pendiente = Jardin.objects.create(razon_social='Jardín Pendiente', activo=False)

        docente = User.objects.create_user('docente_panel', password='ContraseñaSegura123')
        PerfilUsuario.objects.create(usuario=docente, edad=30, jardin=self.jardin_activo)
        Nino.objects.create(nombre='Leo', apellido='Test', edad=5, jardin=self.jardin_activo)

        self.superusuario = User.objects.create_superuser('superadmin', 'admin@example.com', 'ContraseñaSegura123')
        self.usuario_normal = docente

    def test_usuario_normal_no_puede_ver_el_panel(self):
        self.client.force_login(self.usuario_normal)
        response = self.client.get(reverse('narraciones:panel_superadmin'))
        self.assertRedirects(response, reverse('narraciones:menu'))

    def test_superusuario_ve_todas_las_instituciones_con_sus_totales(self):
        self.client.force_login(self.superusuario)
        response = self.client.get(reverse('narraciones:panel_superadmin'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_jardines'], 2)
        self.assertEqual(response.context['total_activos'], 1)
        self.assertEqual(response.context['total_pendientes'], 1)

        fila_activa = next(f for f in response.context['filas'] if f['jardin'].id == self.jardin_activo.id)
        self.assertEqual(fila_activa['total_usuarios'], 1)
        self.assertEqual(fila_activa['total_ninos'], 1)

    def test_superusuario_puede_aprobar_una_institucion_pendiente(self):
        self.client.force_login(self.superusuario)
        self.client.post(reverse('narraciones:panel_superadmin_actualizar', args=[self.jardin_pendiente.id]), {'accion': 'aprobar'})
        self.jardin_pendiente.refresh_from_db()
        self.assertTrue(self.jardin_pendiente.activo)

    def test_superusuario_puede_desactivar_una_institucion(self):
        self.client.force_login(self.superusuario)
        self.client.post(reverse('narraciones:panel_superadmin_actualizar', args=[self.jardin_activo.id]), {'accion': 'desactivar'})
        self.jardin_activo.refresh_from_db()
        self.assertFalse(self.jardin_activo.activo)

    def test_usuario_normal_no_puede_actualizar_instituciones(self):
        self.client.force_login(self.usuario_normal)
        response = self.client.post(reverse('narraciones:panel_superadmin_actualizar', args=[self.jardin_pendiente.id]), {'accion': 'aprobar'})
        self.assertRedirects(response, reverse('narraciones:menu'))
        self.jardin_pendiente.refresh_from_db()
        self.assertFalse(self.jardin_pendiente.activo)

    def test_superusuario_no_queda_bloqueado_por_middleware_de_jardin_pendiente(self):
        """Un superusuario nunca debe quedar atrapado por el gating de institucion/demo."""
        perfil_super = PerfilUsuario.objects.create(usuario=self.superusuario, edad=40, jardin=self.jardin_pendiente)
        self.client.force_login(self.superusuario)
        response = self.client.get(reverse('narraciones:menu'))
        self.assertEqual(response.status_code, 200)
