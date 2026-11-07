"""Отзывы: валидация, приём на модерацию, антиспам, лимит, демо-режим; показ только одобренных."""
import pytest
from django.test import override_settings

from apps.pages.content import SAMPLE_REVIEWS
from apps.pages.viewmodels import reviews_for
from apps.reviews.forms import ReviewForm
from apps.reviews.models import Review
from tests.factories import make_motorcycle, make_review
from tests.fixtures.http import post_form

pytestmark = pytest.mark.django_db

URL = "/reviews/submit/"
JSON = {"HTTP_ACCEPT": "application/json"}
TEXT = "Отличный электромотоцикл, тихий и быстрый."


def review_data(**overrides) -> dict:
    return {"display_name": "Гөлназ", "city": "Набережные Челны", "rating": "5", "text": TEXT, "consent": "on",
            "publication_consent": "on", **overrides}


class TestReviewForm:
    def test_valid(self):
        form = ReviewForm(review_data())
        assert form.is_valid(), form.errors
        assert form.cleaned_data["motorcycle"] is None

    @pytest.mark.parametrize("missing", ["consent", "publication_consent"])
    def test_both_consents_required(self, missing):
        data = review_data()
        del data[missing]
        form = ReviewForm(data)
        assert not form.is_valid()
        assert missing in form.errors

    def test_text_min_20_chars(self):
        assert "text" in ReviewForm(review_data(text="Коротко")).errors
        assert ReviewForm(review_data(text="а" * 20)).is_valid()

    def test_text_stripped(self):
        form = ReviewForm(review_data(text=f"   {TEXT}   "))
        assert form.is_valid()
        assert form.cleaned_data["text"] == TEXT

    @pytest.mark.parametrize("rating", ["0", "6", "x"])
    def test_rating_bounds(self, rating):
        assert "rating" in ReviewForm(review_data(rating=rating)).errors

    @pytest.mark.parametrize("name", ["Я", "123", "<b>Аня</b>", "a" * 41])
    def test_bad_display_name(self, name):
        assert "display_name" in ReviewForm(review_data(display_name=name)).errors

    def test_bad_city(self):
        assert "city" in ReviewForm(review_data(city="г. 123")).errors

    def test_city_optional(self):
        form = ReviewForm(review_data(city=""))
        assert form.is_valid() and form.cleaned_data["city"] == ""

    def test_honeypot_is_spam_error(self):
        form = ReviewForm(review_data(website="x"))
        assert not form.is_valid()
        assert form.non_field_errors().as_data()[0].code == "spam"

    def test_only_published_model_linked(self):
        visible = make_motorcycle()
        hidden = make_motorcycle(is_published=False)
        assert ReviewForm(review_data(model=visible.slug)).is_valid()
        form = ReviewForm(review_data(model=visible.slug))
        form.is_valid()
        assert form.cleaned_data["motorcycle"] == visible
        form = ReviewForm(review_data(model=hidden.slug))
        form.is_valid()
        assert form.cleaned_data["motorcycle"] is None


class TestSubmitView:
    def test_creates_pending_review(self, client, clock):
        moto = make_motorcycle()

        response = post_form(client, URL, review_data(model=moto.slug))

        assert response.status_code == 201
        assert response.json() == {"success": True}
        review = Review.objects.get()
        assert review.status == Review.Status.PENDING
        assert review.motorcycle == moto
        assert review.consent_at == clock.current == review.publication_consent_at
        assert len(review.ip_hash) == 64

    def test_validation_error_400(self, client):
        response = post_form(client, URL, review_data(text="short", consent=""))

        assert response.status_code == 400
        assert set(response.json()["fields"]) == {"text", "consent"}
        assert Review.objects.count() == 0

    def test_honeypot_returns_success_without_saving(self, client):
        response = post_form(client, URL, review_data(website="http://spam"))

        assert response.status_code == 200
        assert response.json() == {"success": True}
        assert Review.objects.count() == 0

    def test_rate_limit(self, client, settings, clock):
        settings.REVIEW_RATE_LIMIT = (2, 86400)

        codes = [post_form(client, URL, review_data()).status_code for _ in range(3)]

        assert codes == [201, 201, 429]
        assert Review.objects.count() == 2

    def test_invalid_submissions_do_not_consume_limit(self, client, settings):
        settings.REVIEW_RATE_LIMIT = (1, 86400)
        for _ in range(3):
            post_form(client, URL, review_data(text="x"))

        assert post_form(client, URL, review_data()).status_code == 201

    def test_rate_limit_counts_only_unmoderated_reviews(self, client, settings, clock):
        settings.REVIEW_RATE_LIMIT = (1, 86400)
        assert post_form(client, URL, review_data()).status_code == 201
        assert post_form(client, URL, review_data()).status_code == 429

        Review.objects.update(status=Review.Status.REJECTED, ip_hash="")  # как после модерации

        assert post_form(client, URL, review_data()).status_code == 201

    def test_rate_limit_window(self, client, settings, clock):
        from datetime import timedelta

        settings.REVIEW_RATE_LIMIT = (1, 3600)
        post_form(client, URL, review_data())
        clock.set(clock.current + timedelta(seconds=3601))
        assert post_form(client, URL, review_data()).status_code == 201

    def test_multipart_rejected_by_guard(self, client):
        assert client.post(URL, review_data()).status_code == 415

    @override_settings(SITE_MODE="demo")
    def test_demo_mode_403(self, client):
        response = post_form(client, URL, review_data())
        assert response.status_code == 403
        assert Review.objects.count() == 0

    def test_non_json_redirects(self, client):
        ok = post_form(client, URL, review_data(), json=False)
        bad = post_form(client, URL, review_data(text="x"), json=False)
        assert ok.status_code == 302 and ok["Location"] == "/reviews/?sent=1"
        assert bad.status_code == 302 and bad["Location"] == "/reviews/?error=1"

    def test_get_not_allowed(self, client):
        assert client.get(URL).status_code == 405


class TestReviewsFor:
    def test_only_approved(self):
        approved = make_review(status=Review.Status.APPROVED)
        make_review(status=Review.Status.PENDING)
        make_review(status=Review.Status.REJECTED)

        reviews, samples = reviews_for()

        assert reviews == [approved] and samples is False

    def test_filtered_by_motorcycle_and_limited(self):
        moto = make_motorcycle()
        for _ in range(3):
            make_review(motorcycle=moto)
        make_review()

        reviews, _ = reviews_for(moto, limit=2)

        assert len(reviews) == 2 and all(r.motorcycle == moto for r in reviews)

    def test_no_samples_by_default(self, settings):
        settings.SHOW_SAMPLE_REVIEWS = False
        make_review(status=Review.Status.PENDING)
        assert reviews_for() == ([], False)

    def test_samples_when_enabled_and_none_approved(self, settings):
        settings.SHOW_SAMPLE_REVIEWS = True
        make_review(status=Review.Status.PENDING)

        reviews, samples = reviews_for()

        assert samples is True
        assert reviews == list(SAMPLE_REVIEWS)

    def test_real_reviews_win_over_samples(self, settings):
        settings.SHOW_SAMPLE_REVIEWS = True
        real = make_review()
        assert reviews_for() == ([real], False)

    def test_str(self):
        assert str(make_review(display_name="Аня", rating=4)) == "Аня: 4★"
