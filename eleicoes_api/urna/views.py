from rest_framework import viewsets, filters, status
from django.utils import timezone
from rest_framework.exceptions import MethodNotAllowed
from django_filters.rest_framework import DjangoFilterBackend
from .models import *
from .serializers import *
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import secrets
from django.db import IntegrityError
import qrcode
import io
from django.http import HttpResponse
import re

class EleitorViewSet(viewsets.ModelViewSet):
    queryset = Eleitor.objects.all()
    serializer_class = EleitorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['ativo']
    search_fields = ['nome', 'email', 'cpf']


class EleicaoViewSet(viewsets.ModelViewSet):
    queryset = Eleicao.objects.all()
    serializer_class = EleicaoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tipo', 'criada_por']
    search_fields = ['titulo']
    ordering_fields = ['data_inicio']
    ordering = ['data_inicio']

    @action(detail=True, methods=['post'])
    def votar(self, request, pk=None):
        votacao = VotacaoInputSerializer(data=request.data)
        eleicao = self.get_object()
        votacao.is_valid(raise_exception=True)
        eleitor_id = votacao.validated_data['eleitor_id']
        candidato = votacao.validated_data.get('candidato')
        em_branco = votacao.validated_data.get('em_branco', False)
        try:
            registro = RegistroVotacao.objects.create(eleitor_id=eleitor_id, eleicao=eleicao, data_hora=timezone.now())
        except IntegrityError:
            return Response({'mensagem': 'Eleitor já votou nesta eleição'}, status=status.HTTP_409_CONFLICT)
        token = secrets.token_urlsafe(32)
        voto = Voto.objects.create(
            eleicao=eleicao,
            candidato=candidato,
            em_branco=bool(em_branco),
            comprovante_hash=token,
        )
        qr_token_url = f"/eleicoes_api/comprovantes/qr/?token={token}"
        candidato_repr = None
        if candidato is not None:
            candidato_repr = f"{candidato.nome} (#{candidato.numero})"

        datatime_iso = voto.data_hora.isoformat()
        if datatime_iso.endswith('+00:00'):
            datatime_iso = datatime_iso.replace('+00:00', 'Z')

        response_body = {
            'mensagem': 'Voto registrado com sucesso. Guarde o seu comprovante.',
            'comprovante': {
                'token': token,
                'eleicao': eleicao.titulo,
                'candidato': candidato_repr,
                'data_hora': datatime_iso,
                'qr_code_url': qr_token_url
            }
        }

        return Response(response_body, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def abrir(self, request, pk=None):
        eleicao = self.get_object()
        if eleicao.status != 'rascunho':
            return Response({'detail': 'Eleição deve estar em rascunho para ser aberta.'}, status=status.HTTP_400_BAD_REQUEST)
        if eleicao.candidatos.count() < 2:
            return Response({'detail': 'É necessário pelo menos 2 candidatos para abrir a eleição.'}, status=status.HTTP_400_BAD_REQUEST)
        if eleicao.aptos.count() < 1:
            return Response({'detail': 'É necessário pelo menos 1 eleitor apto para abrir a eleição.'}, status=status.HTTP_400_BAD_REQUEST)
        eleicao.status = 'aberta'
        eleicao.save()
        return Response(EleicaoSerializer(eleicao).data)

    @action(detail=True, methods=['post'])
    def encerrar(self, request, pk=None):
        eleicao = self.get_object()
        if eleicao.status != 'aberta':
            return Response({'detail': 'Eleição deve estar aberta para ser encerrada.'}, status=status.HTTP_400_BAD_REQUEST)
        eleicao.status = 'encerrada'
        eleicao.save()
        return Response(EleicaoSerializer(eleicao).data)

    @action(detail=True, methods=['get'])
    def apuracao(self, request, pk=None):
        eleicao = self.get_object()
        if eleicao.status not in ('encerrada', 'apurada'):
            return Response({'detail': 'Apuração disponível apenas para eleições encerradas ou apuradas.'}, status=status.HTTP_403_FORBIDDEN)
        total_aptos = eleicao.aptos.count()
        total_votantes = eleicao.registros_votacao.count()
        total_abstencoes = total_aptos - total_votantes
        votos_brancos = Voto.objects.filter(eleicao=eleicao, em_branco=True).count()
        votos_validos = Voto.objects.filter(eleicao=eleicao, em_branco=False).count()
        candidatos = list(eleicao.candidatos.all())
        resultados = []
        for candidato in candidatos:
            votos = Voto.objects.filter(eleicao=eleicao, candidato=candidato, em_branco=False).count()
            percentual = (votos / votos_validos * 100) if votos_validos > 0 else 0
            resultados.append({'candidato': candidato, 'votos': votos, 'percentual': round(percentual, 2)})
        resultados.sort(key=lambda x: x['votos'], reverse=True)
        resultado_list = []
        for idx, r in enumerate(resultados, start=1):
            candidato = r['candidato']
            resultado_list.append({
                'posicao': idx,
                'candidato': candidato.nome,
                'numero': candidato.numero,
                'votos': r['votos'],
                'percentual': r['percentual'],
            })
        vencedores = []
        houve_empate = False
        if resultado_list:
            max_votos = resultado_list[0]['votos']
            vencedores = [r['candidato'] for r in resultado_list if r['votos'] == max_votos]
            houve_empate = len(vencedores) > 1
        comparecimento_pct = (total_votantes / total_aptos * 100) if total_aptos > 0 else 0
        if eleicao.status == 'encerrada':
            eleicao.status = 'apurada'
            eleicao.save()

        return Response({
            'eleicao': eleicao.titulo,
            'total_aptos': total_aptos,
            'total_votantes': total_votantes,
            'total_abstencoes': total_abstencoes,
            'votos_validos': votos_validos,
            'votos_brancos': votos_brancos,
            'comparecimento_pct': round(comparecimento_pct, 2),
            'resultado': resultado_list,
            'vencedores': vencedores,
            'houve_empate': houve_empate,
        })

    @action(detail=True, methods=['get'])
    def votantes(self, request, pk=None):
        eleicao = self.get_object()
        compareceu = request.query_params.get('compareceu')
        def mask_cpf(cpf):
            digitos = re.sub(r'\D', '', cpf or '')
            if len(digitos) >= 5:
                return f"{digitos[:3]}.***.***-{digitos[-2:]}"
            return cpf
        if compareceu is not None and compareceu.lower() in ('false', '0'):
            aptos = Eleitor.objects.filter(aptidoes__eleicao=eleicao).distinct()
            votantes_qs = aptos.exclude(registros_votacao__eleicao=eleicao)
            results = []
            for eleitor in votantes_qs:
                results.append({
                    'nome': eleitor.nome,
                    'cpf': mask_cpf(eleitor.cpf),
                    'data_hora': None,
                })
            return Response(results)
        registros = RegistroVotacao.objects.filter(eleicao=eleicao).select_related('eleitor').order_by('data_hora')
        results = []
        for reg in registros:
            results.append({
                'nome': reg.eleitor.nome,
                'cpf': mask_cpf(reg.eleitor.cpf),
                'data_hora': reg.data_hora.isoformat(),
            })
        return Response(results)

    @action(detail=True, methods=['post'])
    def cadastrar_aptos(self, request, pk=None):
        eleicao = self.get_object()
        if eleicao.status != 'rascunho':
            return Response({'detail': 'Cadastro em lote permitido apenas enquanto eleição está em rascunho.'}, status=status.HTTP_400_BAD_REQUEST)
        eleitores_ids = request.data.get('eleitores_ids')
        if not isinstance(eleitores_ids, list):
            return Response({'detail': 'O corpo deve conter "eleitores_ids" como lista.'}, status=status.HTTP_400_BAD_REQUEST)
        ids_validos = list(Eleitor.objects.filter(pk__in=eleitores_ids).values_list('id', flat=True))
        criar = []
        for id in ids_validos:
            if not AptidaoEleitor.objects.filter(eleitor_id=id, eleicao=eleicao).exists():
                criar.append(AptidaoEleitor(eleitor_id=id, eleicao=eleicao))
        total_cadastrados = 0
        if criar:
            AptidaoEleitor.objects.bulk_create(criar)
            total_cadastrados = len(criar)
        return Response({'total_cadastrados': total_cadastrados})

class CandidatoViewSet(viewsets.ModelViewSet):
    queryset = Candidato.objects.select_related('eleicao').all()
    serializer_class = CandidatoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['eleicao']
    search_fields = ['nome', 'nome_urna', 'partido_ou_chapa']


class AptidaoEleitorViewSet(viewsets.ModelViewSet):
    queryset = AptidaoEleitor.objects.select_related('eleitor', 'eleicao').all()
    serializer_class = AptidaoEleitorSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['eleitor', 'eleicao']


class RegistroVotacaoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RegistroVotacao.objects.select_related('eleitor', 'eleicao').all()
    serializer_class = RegistroVotacaoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['eleicao']
    ordering_fields = ['data_hora']
    ordering = ['-data_hora']


class VotoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Voto.objects.select_related('candidato', 'eleicao').all()
    serializer_class = VotoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['eleicao']
    http_method_names = ['get', 'head', 'options']

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed('POST')

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed('PUT')

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed('PATCH')

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed('DELETE')


@api_view(['GET'])
@permission_classes([AllowAny])
def verificar_comprovante(request):
    token = request.query_params.get('token')
    if not token:
        return Response({'valido': False, 'mensagem': 'token é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        voto = Voto.objects.select_related('eleicao', 'candidato').get(comprovante_hash=token)
    except Voto.DoesNotExist:
        return Response({'valido': False, 'mensagem': 'Comprovante inválido'}, status=status.HTTP_404_NOT_FOUND)
    candidato_repr = 'BRANCO' if voto.em_branco else f"{voto.candidato.nome} (#{voto.candidato.numero})"
    datatime_iso = voto.data_hora.isoformat()
    if datatime_iso.endswith('+00:00'):
        datatime_iso = datatime_iso.replace('+00:00', 'Z')
    return Response({
        'eleicao': voto.eleicao.titulo,
        'candidato': candidato_repr,
        'data_hora': datatime_iso,
        'valido': True,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def comprovante_qr(request):
    token = request.query_params.get('token')
    if not token:
        return Response({'detail': 'token é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
    qr_url = f"/eleicoes_api/verificar-comprovante/?token={token}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return HttpResponse(buffer.getvalue(), content_type='image/png')
