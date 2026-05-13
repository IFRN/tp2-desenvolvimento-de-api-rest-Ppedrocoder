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
