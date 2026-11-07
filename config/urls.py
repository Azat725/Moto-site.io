from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "IV&AX MOTO — управление сайтом"
admin.site.site_title = "IV&AX MOTO"
admin.site.index_title = "Каталог, заявки и отзывы"

urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("api/", include("apps.leads.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("", include("apps.pages.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
