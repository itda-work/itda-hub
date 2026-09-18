from django.contrib import admin

from .models import ToolboxEntry, ToolSetting


@admin.register(ToolboxEntry)
class ToolboxEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'tool', 'use_shared_credential', 'added_at')
    list_filter = ('tool',)


@admin.register(ToolSetting)
class ToolSettingAdmin(admin.ModelAdmin):
    """값은 보이지 않는다. 키와 갱신 시각만."""

    list_display = ('entry', 'key', 'updated_at')
    fields = ('entry', 'key', 'updated_at')
    readonly_fields = ('entry', 'key', 'updated_at')
