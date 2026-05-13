"""
URL configuration for eleicoes_api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter
from urna import views
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
   openapi.Info(
      title="Eleições API",
      default_version='v1',
      description="API REST para gerenciamento de eleições, candidatos e votos.",
   ),
   public=True,
)

router = DefaultRouter()
router.register(r'eleitores', views.EleitorViewSet)
router.register(r'eleicoes', views.EleicaoViewSet)
router.register(r'candidatos', views.CandidatoViewSet)
router.register(r'aptidoes', views.AptidaoEleitorViewSet)
router.register(r'registros-votacao', views.RegistroVotacaoViewSet)
router.register(r'votos', views.VotoViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('eleicoes_api/', include(router.urls)),
    path('eleicoes_api/verificar-comprovante/', views.verificar_comprovante, name='verificar-comprovante'),
    path('eleicoes_api/comprovantes/qr/', views.comprovante_qr, name='comprovante-qr'),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]