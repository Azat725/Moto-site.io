from django.conf import settings

from apps.catalog.models import SiteSettings
from apps.leads.forms import issue_form_token

from .seo import site_origin


def site(request):
    """Общие данные для всех шаблонов сайта."""
    if request.path_info.startswith("/" + settings.ADMIN_PATH):
        return {}
    return {
        "site": SiteSettings.load(),
        "site_mode": settings.SITE_MODE,
        "site_domain": settings.SITE_DOMAIN,
        "site_origin": site_origin(),
        "site_noindex": settings.SITE_NOINDEX,
        "brand": "IV&AX MOTO",
        "city": "Нижнекамск",
        "city_in": "Нижнекамске",
        "region": "Республика Татарстан",
        "consent_version": settings.CONSENT_VERSION,
        "form_token": issue_form_token(),
    }
