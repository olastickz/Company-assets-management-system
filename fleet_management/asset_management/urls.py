from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.auth import views as auth_views
from django.views.static import serve
from django.views.generic import RedirectView
from vehicles import views

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='https://telnetng.com/_next/image?url=%%2Fimages%%2Ftelnet-logo-new.png&w=384&q=75', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/', include('vehicles.api_urls')),
    path('api/v1/', include('vehicles.api_v1_urls')),

    # LOGIN / LOGOUT
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.custom_logout, name='logout'),

    path('staff/password-setup/<uidb64>/<token>/', views.StaffPasswordSetupView.as_view(), name='staff_password_setup'),
    path('staff/password-setup/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='staff_password_setup_done'),
    path('change-password/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change_form.html'), name='password_change'),
    path('change-password/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),

    # Dashboard / Vehicles main page
    path('', include('vehicles.urls')),  # includes the updated vehicles/urls.py
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
