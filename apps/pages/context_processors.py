from django.conf import settings

from apps.catalog.models import SiteSettings


def site(request):
    """Общие данные для всех шаблонов сайта."""
    if request.path.startswith("/" + settings.ADMIN_PATH):
        return {}
    return {
        "site": SiteSettings.load(),
        "site_mode": settings.SITE_MODE,
        "site_domain": settings.SITE_DOMAIN,
        "site_noindex": settings.SITE_NOINDEX,
        "brand": "IV&AX MOTO",
        "city": "Нижнекамск",
        "city_in": "Нижнекамске",
        "region": "Республика Татарстан",
        "consent_version": settings.CONSENT_VERSION,
    }
