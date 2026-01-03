"""
URL configuration for Investment Platform project.
"""

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from apps.users.views import (
    login_page, dashboard_view, logout_view, dev_login_as, register_page,
    transactions_page, transactions_export, settings_page,
)
from apps.investments.views import investments_page
from apps.deposits.views import deposits_page
from apps.withdrawals.views import withdrawals_page
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.http import JsonResponse
import json
import os

# Root redirects to login/register when anonymous, otherwise to dashboard
def root_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')

# Serve manifest.json for PWA
def manifest_view(request):
    manifest_path = os.path.join(settings.BASE_DIR, 'static', 'manifest.json')
    with open(manifest_path, 'r') as f:
        manifest_data = json.load(f)
    return JsonResponse(manifest_data, content_type='application/manifest+json')

urlpatterns = [
    path('admin/', admin.site.urls),
    # PWA manifest
    path('manifest.json', manifest_view, name='manifest'),
    # Frontend template routes
    path('', root_view, name='home'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('debug/', TemplateView.as_view(template_name='debug.html'), name='debug'),
    path('login/', login_page, name='login'),
    path('logout/', logout_view, name='logout'),
    # Dev helper: quickly create a session for a user (DEBUG only)
    path('dev/login-as/', dev_login_as, name='dev-login-as'),
    path('register/', register_page, name='register'),
    path('forgot-password/', TemplateView.as_view(template_name='forgot_password.html'), name='forgot-password'),
    path('reset-password/<str:uid>/<str:token>/', TemplateView.as_view(template_name='reset_password.html'), name='reset-password'),
    path('profile/', TemplateView.as_view(template_name='profile.html'), name='profile'),
    path('settings/', settings_page, name='settings'),
    path('deposits/', deposits_page, name='deposits'),
    path('investments/', investments_page, name='investments'),
    path('support/', TemplateView.as_view(template_name='support.html'), name='support'),
    path('withdrawals/', withdrawals_page, name='withdrawals'),
    path('referrals/', TemplateView.as_view(template_name='referrals.html'), name='referrals'),
    path('transactions/', transactions_page, name='transactions'),
    path('transactions/export/', transactions_export, name='transactions-export'),
    path('api/users/', include('apps.users.urls')),
    path('api/investments/', include('apps.investments.urls')),
    path('api/deposits/', include('apps.deposits.urls')),
    path('api/withdrawals/', include('apps.withdrawals.urls')),
    path('api/support/', include('apps.support.urls')),
    path('api/', include('apps.referrals.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
