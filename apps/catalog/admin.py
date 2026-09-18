from django.contrib import admin

from .models import Tool


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'provider', 'credential', 'enabled', 'order')
    list_editable = ('enabled', 'order')
    search_fields = ('slug', 'name', 'provider')
