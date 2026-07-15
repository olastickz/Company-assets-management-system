from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from vehicles import views

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='https://telnetng.com/_next/image?url=%%2Fimages%%2Ftelnet-logo-new.png&w=384&q=75', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/', include('vehicles.api_urls')),

    # LOGIN / LOGOUT
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.custom_logout, name='logout'),

    # Password reset flow
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),

    # Dashboard / Vehicles main page
    path('', include('vehicles.urls')),  # includes the updated vehicles/urls.py
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
