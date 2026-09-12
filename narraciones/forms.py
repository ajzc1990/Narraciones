from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Jardin, Nino, PerfilUsuario


class RegistroUsuarioForm(UserCreationForm):
    """Alta de usuario (RF-02): nombre, apellido, edad, email, usuario, contraseña e institución."""
    first_name = forms.CharField(label="Nombre", max_length=150, required=True)
    last_name = forms.CharField(label="Apellido", max_length=150, required=True)
    edad = forms.IntegerField(label="Edad", min_value=16, max_value=120, required=True)
    email = forms.EmailField(label="E-mail", required=True)
    jardin_nombre = forms.CharField(
        label="Jardín / Institución", max_length=150, required=True,
        help_text=(
            "Si ya existe una cuenta con este nombre, te unís a esa institución. Si no, se crea una nueva "
            "y quedará pendiente de aprobación hasta que la validemos (te contactaremos)."
        )
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'edad', 'email', 'jardin_nombre', 'username', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Ya existe una cuenta registrada con este e-mail.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.first_name = self.cleaned_data['first_name']
        usuario.last_name = self.cleaned_data['last_name']
        usuario.email = self.cleaned_data['email']
        if commit:
            usuario.save()
            jardin, creado = Jardin.objects.get_or_create(
                razon_social__iexact=self.cleaned_data['jardin_nombre'],
                defaults={'razon_social': self.cleaned_data['jardin_nombre'], 'activo': False}
            )
            PerfilUsuario.objects.create(
                usuario=usuario, edad=self.cleaned_data['edad'], jardin=jardin,
                # Quien da de alta una institución nueva queda como su administrador.
                es_admin_jardin=creado,
            )
        return usuario


class NinoForm(forms.ModelForm):
    """Alta/Modificación de niño (RF-07): nombre, apellido, DNI, teléfono, domicilio."""

    autorizacion_parental = forms.BooleanField(
        required=True,
        label="Confirmo que cuento con la autorización de los padres/tutores para registrar a este niño/a",
    )

    class Meta:
        model = Nino
        fields = [
            'nombre', 'apellido', 'dni', 'telefono', 'domicilio', 'fecha_nacimiento', 'edad',
            'institucion_o_sala', 'autorizacion_parental',
        ]
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
        }
