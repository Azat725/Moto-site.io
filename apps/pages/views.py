from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.catalog.models import Color, Motorcycle, SiteSettings
from apps.catalog.services import build_offer, current_context, published_motorcycles

from . import seo
from .content import FAQ, ORDER_STEPS
from .viewmodels import card, catalog_cards, filter_facets, reviews_for

STATIC_PAGES = {
    "delivery": ("pages/delivery.html", "Доставка и оплата"),
    "about": ("pages/about.html", "О нас"),
    "contacts": ("pages/contacts.html", "Контакты"),
    "privacy": ("pages/legal/privacy.html", "Политика конфиденциальности"),
    "consent": ("pages/legal/consent.html", "Согласие на обработку персональных данных"),
    "consent_publication": ("pages/legal/consent_publication.html", "Согласие на публикацию отзыва"),
    "terms": ("pages/legal/terms.html", "Пользовательское соглашение"),
    "cookies": ("pages/legal/cookies.html", "Политика cookie"),
    "thanks": ("pages/thanks.html", "Спасибо за заявку"),
    "preview_logo": ("pages/preview/logo.html", "Варианты логотипа"),
}
NOINDEX_PAGES = {"thanks", "preview_logo"}
LOGO_VARIANTS = (
    ("volt", "Volt — молния-рога", "Щит, разрезанный молнией; верхние концы — дьявольские рога. Электро + дерзость."),
    ("horns", "Horns — рогатый щит", "Угловатый чёрный щит с рогами и красным ядром-молнией."),
    ("fang", "Fang — клык", "Агрессивная курсивная «V» с клыком и искрой на чёрном фоне."),
)


def _catalog_context() -> dict:
    cards, ctx = catalog_cards()
    return {"cards": cards, "price_ctx": ctx, "facets": filter_facets(cards)}


def _home_context() -> dict:
    base = _catalog_context()
    reviews, samples = reviews_for()
    jsonld = [seo.dealer(SiteSettings.load()), seo.item_list(base["cards"]), seo.faq_page()]
    return base | {"faq": FAQ, "steps": ORDER_STEPS, "reviews": reviews, "reviews_are_samples": samples,
                   "jsonld": jsonld}


@require_GET
def home(request):
    return render(request, "pages/home.html", _home_context())


@require_GET
def home_classic(request):
    return render(request, "pages/preview/home_classic.html", _home_context() | {"noindex": True})


@require_GET
def catalog(request):
    context = _catalog_context()
    context["jsonld"] = [seo.item_list(context["cards"]), seo.breadcrumbs([("Каталог", reverse("pages:catalog"))])]
    return render(request, "pages/catalog.html", context)


@require_GET
def model_detail(request, slug: str):
    moto = get_object_or_404(published_motorcycles(), slug=slug)
    ctx = current_context()
    offer = build_offer(moto, ctx)
    moto_card = card(moto, offer)
    colors = list(moto.colors.all()) or list(Color.objects.all())
    related = [card(m, build_offer(m, ctx)) for m in published_motorcycles().exclude(pk=moto.pk).filter(type=moto.type)[:3]]
    reviews, samples = reviews_for(moto, limit=3)
    crumbs = [("Каталог", reverse("pages:catalog")), (moto.name, moto.get_absolute_url())]
    context = {
        "moto": moto, "offer": offer, "cfg": offer.as_json(), "colors": colors, "price_ctx": ctx, "card": moto_card,
        "variant_rows": list(zip(moto.variants.all(), offer.variants)), "related": related,
        "reviews": reviews, "reviews_are_samples": samples,
        "jsonld": [seo.product(moto_card), seo.breadcrumbs(crumbs)],
    }
    return render(request, "pages/model.html", context)


@require_GET
def reviews_page(request):
    reviews, samples = reviews_for(limit=50)
    models = Motorcycle.objects.filter(is_published=True).only("slug", "name")
    crumbs = seo.breadcrumbs([("Отзывы", reverse("pages:reviews"))])
    return render(request, "pages/reviews.html", {"reviews": reviews, "reviews_are_samples": samples,
                                                  "models": models, "jsonld": [crumbs]})


@require_GET
def static_page(request, page: str):
    if page not in STATIC_PAGES:
        raise Http404
    template, title = STATIC_PAGES[page]
    context = {"page_key": page, "page_title": title, "noindex": page in NOINDEX_PAGES,
               "jsonld": [seo.breadcrumbs([(title, request.path_info)])]}
    if page == "contacts":
        context["jsonld"].append(seo.dealer(SiteSettings.load()))
    if page == "preview_logo":
        context["logo_variants"] = LOGO_VARIANTS
    return render(request, template, context)


@require_GET
def robots_txt(request):
    if settings.SITE_NOINDEX:
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = (f"User-agent: *\nAllow: /\nDisallow: /{settings.ADMIN_PATH}\nDisallow: /api/\n"
                f"Disallow: /preview/\nDisallow: /thanks/\n\nSitemap: {settings.SITE_DOMAIN}/sitemap.xml\n")
    return HttpResponse(body, content_type="text/plain; charset=utf-8")
