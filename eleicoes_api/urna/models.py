from django.db import models
from django.core.exceptions import ValidationError

# Create your models here.

class Eleitor(models.Model):
    nome = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    cpf = models.CharField(max_length=14, unique=True)
    data_nascimento = models.DateField()
    ativo = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

class Eleicao(models.Model):
    CHOICES_TIPO = [
        ('estudantil', 'Estudantil'),
        ('sindical', 'Sindical'),
        ('associacao', 'Associação'),
        ('condominio', 'Condomínio'),
        ('conselho', 'Conselho'),
        ('outra', 'Outra'),
    ]

    CHOICES_STATUS = [
        ('rascunho', 'Rascunho'),
        ('aberta', 'Aberta'),
        ('encerrada', 'Encerrada'),
        ('apurada', 'Apurada'),
    ]

    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    tipo = models.CharField(max_length=50, choices=CHOICES_TIPO)
    data_inicio = models.DateTimeField()
    data_fim = models.DateTimeField()
    status = models.CharField(max_length=50, choices=CHOICES_STATUS, default='rascunho')
    permite_branco = models.BooleanField(default=False)
    criada_por = models.ForeignKey(Eleitor, on_delete=models.PROTECT, related_name='eleicoes_criadas')

    def clean(self):
        errors = {}
        if self.data_fim <= self.data_inicio:
            errors['data_fim'] = 'A data de fim deve ser posterior à data de início.'

        if self.pk:
            try:
                antigo = Eleicao.objects.get(pk=self.pk)
            except Eleicao.DoesNotExist:
                antigo = None

            if antigo and antigo.status != self.status:
                transicoes = {
                    'rascunho': 'aberta',
                    'aberta': 'encerrada',
                    'encerrada': 'apurada',
                }
                permitido = transicoes.get(antigo.status)
                if permitido != self.status:
                    errors['status'] = (
                        f'Transição inválida: {antigo.status} → {self.status}. '
                        'Só é permitido seguir: rascunho → aberta → encerrada → apurada.'
                    )
        else:
            if self.status != 'rascunho':
                errors['status'] = 'Ao criar, o status inicial deve ser "rascunho".'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

class Candidato(models.Model):
    eleicao = models.ForeignKey(Eleicao, on_delete=models.CASCADE, related_name='candidatos')
    numero = models.PositiveIntegerField()
    nome = models.CharField(max_length=150)
    nome_urna = models.CharField(max_length=50)
    partido_ou_chapa = models.CharField(max_length=100, blank=True)
    proposta = models.TextField(blank=True)
    foto_url = models.URLField(blank=True)

    class Meta:
        unique_together = ('eleicao', 'numero')

class AptidaoEleitor(models.Model):
    eleitor = models.ForeignKey(Eleitor, on_delete=models.PROTECT, related_name='aptidoes')
    eleicao = models.ForeignKey(Eleicao, on_delete=models.CASCADE, related_name='aptos')
    data_inclusao = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('eleitor', 'eleicao')

class RegistroVotacao(models.Model):
    eleitor = models.ForeignKey(Eleitor, on_delete=models.PROTECT, related_name='registros_votacao')
    eleicao = models.ForeignKey(Eleicao, on_delete=models.PROTECT, related_name='registros_votacao')
    data_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('eleitor', 'eleicao')

class Voto(models.Model):
    eleicao = models.ForeignKey(Eleicao, on_delete=models.PROTECT, related_name='votos')
    candidato = models.ForeignKey(Candidato, on_delete=models.PROTECT, related_name='votos', null=True, blank=True)
    em_branco = models.BooleanField(default=False)
    data_hora = models.DateTimeField(auto_now_add=True)
    comprovante_hash = models.CharField(max_length=64, unique=True)

    def clean(self):
        errors = {}
        if self.em_branco and self.candidato is not None:
            errors['candidato'] = 'Não pode escolher um candidato se votar em branco.'
        if not self.em_branco and self.candidato is None:
            errors['candidato'] = 'Deve escolher um candidato ou votar em branco.'
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)