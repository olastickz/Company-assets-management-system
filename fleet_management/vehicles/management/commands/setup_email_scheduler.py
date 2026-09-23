"""Backward-compatible entry point for the persistent email scheduler."""

from django.core.management import call_command
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Run the scheduled email alerts for expiring items'

    def handle(self, *args, **options):
        call_command('run_email_scheduler')
