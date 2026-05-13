from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import *

class EleitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Eleitor
        fields = '__all__'

    def validate_cpf(self, value):
        import re

        if not re.match(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$', value):
            raise serializers.ValidationError('CPF deve ter formato 000.000.000-00')
        return value


class EleicaoSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_candidatos = serializers.SerializerMethodField()
    total_aptos = serializers.SerializerMethodField()

    class Meta:
        model = Eleicao
        fields = '__all__'

    def get_total_candidatos(self, obj):
        return obj.candidatos.count()

    def get_total_aptos(self, obj):
        return obj.aptos.count()


class CandidatoSerializer(serializers.ModelSerializer):
    eleicao_titulo = serializers.CharField(source='eleicao.titulo', read_only=True)

    class Meta:
        model = Candidato
        fields = '__all__'

    def validate_numero(self, value):
        if value == 0:
            raise serializers.ValidationError('O número 0 é reservado para voto em branco e não pode ser usado para candidato.')
        return value


class AptidaoEleitorSerializer(serializers.ModelSerializer):
    eleitor_nome = serializers.CharField(source='eleitor.nome', read_only=True)
    eleicao_titulo = serializers.CharField(source='eleicao.titulo', read_only=True)

    class Meta:
        model = AptidaoEleitor
        fields = '__all__'


class RegistroVotacaoSerializer(serializers.ModelSerializer):
    eleitor_nome = serializers.CharField(source='eleitor.nome', read_only=True)
    eleicao_titulo = serializers.CharField(source='eleicao.titulo', read_only=True)

    class Meta:
        model = RegistroVotacao
        fields = ['id', 'eleitor', 'eleicao', 'data_hora', 'eleitor_nome', 'eleicao_titulo']
        read_only_fields = fields


class VotoSerializer(serializers.ModelSerializer):
    candidato_nome_urna = serializers.CharField(source='candidato.nome_urna', read_only=True, allow_null=True)
    em_branco_display = serializers.SerializerMethodField()

    class Meta:
        model = Voto
        fields = ['id', 'eleicao', 'candidato', 'em_branco', 'data_hora', 'candidato_nome_urna', 'em_branco_display']
        read_only_fields = fields

    def get_em_branco_display(self, obj):
        return 'BRANCO' if obj.em_branco else None


class VotacaoInputSerializer(serializers.Serializer):
    eleitor_id = serializers.IntegerField()
    eleicao_id = serializers.IntegerField()
    candidato_id = serializers.IntegerField(required=False, allow_null=True)
    em_branco = serializers.BooleanField(default=False)

    def validate(self, data):
        eleitor_id = data.get('eleitor_id')
        eleicao_id = data.get('eleicao_id')
        candidato_id = data.get('candidato_id', None)
        em_branco = data.get('em_branco', False)

        try:
            eleicao = Eleicao.objects.get(pk=eleicao_id)
        except Eleicao.DoesNotExist:
            raise ValidationError('Eleição informada não existe.')

        if eleicao.status != 'aberta':
            raise ValidationError('Eleição não está aberta para votação.')

        agora = timezone.now()
        if not (eleicao.data_inicio <= agora <= eleicao.data_fim):
            raise ValidationError('Fora do período de votação para esta eleição.')

        try:
            eleitor = Eleitor.objects.get(pk=eleitor_id)
        except Eleitor.DoesNotExist:
            raise ValidationError('Eleitor informado não existe.')

        apto = AptidaoEleitor.objects.filter(eleitor=eleitor, eleicao=eleicao).exists()
        if not apto:
            raise ValidationError('Eleitor não está apto para votar nesta eleição.')

        ja_votou = RegistroVotacao.objects.filter(eleitor=eleitor, eleicao=eleicao).exists()
        if ja_votou:
            raise ValidationError('Eleitor já registrou voto nesta eleição.')

        if (candidato_id is None and not em_branco) or (candidato_id is not None and em_branco):
            raise ValidationError('Informe exatamente um: `candidato_id` ou `em_branco=True`.')

        candidato = None
        if candidato_id is not None:
            try:
                candidato = Candidato.objects.get(pk=candidato_id, eleicao=eleicao)
            except Candidato.DoesNotExist:
                raise ValidationError('Candidato informado não pertence a esta eleição.')

        data['eleicao'] = eleicao
        data['eleitor'] = eleitor
        data['candidato'] = candidato
        return data
