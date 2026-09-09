from django.urls import path

from .api_v1 import (
    AuditReportView,
    DocumentReportView,
    EquipmentReportView,
    MaintenanceReportView,
    NotificationDeliveriesView,
    NotificationRecipientsView,
    NotificationRetryView,
    NotificationScheduleView,
    NotificationSettingsView,
    OrganizationSettingsView,
    OverviewReportView,
    ProfileSettingsView,
    SendNotificationNowView,
    TransferReportView,
    VehicleReportView,
)

urlpatterns = [
    path('reports/overview/', OverviewReportView.as_view(), name='api-v1-report-overview'),
    path('reports/vehicles/', VehicleReportView.as_view(), name='api-v1-report-vehicles'),
    path('reports/equipment/', EquipmentReportView.as_view(), name='api-v1-report-equipment'),
    path('reports/documents/', DocumentReportView.as_view(), name='api-v1-report-documents'),
    path('reports/maintenance/', MaintenanceReportView.as_view(), name='api-v1-report-maintenance'),
    path('reports/transfers/', TransferReportView.as_view(), name='api-v1-report-transfers'),
    path('reports/audit/', AuditReportView.as_view(), name='api-v1-report-audit'),
    path('notifications/schedule/', NotificationScheduleView.as_view(), name='api-v1-notification-schedule'),
    path('notifications/recipients/', NotificationRecipientsView.as_view(), name='api-v1-notification-recipients'),
    path('notifications/deliveries/', NotificationDeliveriesView.as_view(), name='api-v1-notification-deliveries'),
    path('notifications/send-now/', SendNotificationNowView.as_view(), name='api-v1-notification-send-now'),
    path('notifications/deliveries/<int:delivery_id>/retry/', NotificationRetryView.as_view(), name='api-v1-notification-retry'),
    path('settings/organization/', OrganizationSettingsView.as_view(), name='api-v1-settings-organization'),
    path('settings/notifications/', NotificationSettingsView.as_view(), name='api-v1-settings-notifications'),
    path('settings/profile/', ProfileSettingsView.as_view(), name='api-v1-settings-profile'),
]
