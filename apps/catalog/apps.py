from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.catalog'
    verbose_name = '도구 카탈로그'

    def ready(self):
        from apps.catalog import checks  # noqa: F401 — import 가 곧 체크 등록이다
