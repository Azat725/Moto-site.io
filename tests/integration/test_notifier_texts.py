"""Тексты уведомлений менеджеру (Telegram — без ПДн по умолчанию, e-mail — полный)."""
import pytest

from apps.leads.models import Lead
from apps.leads.notifiers import email_subject, email_text, telegram_enabled, telegram_text
from tests.factories import make_lead

pytestmark = pytest.mark.django_db


def test_telegram_enabled_requires_token_and_chat(settings):
    assert telegram_enabled() is True
    settings.TELEGRAM = {**settings.TELEGRAM, "CHAT_ID": ""}
    assert telegram_enabled() is False


def test_telegram_text_callback_has_admin_link(settings):
    lead = make_lead(kind=Lead.Kind.CALLBACK)

    text = telegram_text(lead)

    assert f"{settings.SITE_DOMAIN}/{settings.ADMIN_PATH}leads/lead/{lead.pk}/change/" in text
    assert "Обратный звонок" in text
    assert "Итого" not in text and "⚠" not in text


def test_rate_note_and_price_on_request():
    lead = make_lead(model_name="Storm", total_rub=None,
                     config={"variant": "V", "options": ["ABS"], "color": "Red", "rate": "90", "rate_date": "d"})

    text = telegram_text(lead)

    assert "Итого: по запросу (курс 90 на d)" in text
    assert "Опции: ABS" in text and "Цвет: Red" in text and "Комплектация: V" in text


def test_error_line_first_and_escaped():
    lead = make_lead(model_name="Storm", config={"error": "Конфигурацию нужно уточнить: <x>"})

    lines = telegram_text(lead).splitlines()

    assert lines[1] == "⚠ Конфигурацию нужно уточнить: &lt;x&gt;"


def test_total_formatted_with_spaces():
    lead = make_lead(model_name="Storm", total_rub=1_234_000, config={})
    assert "Итого: 1 234 000 ₽" in telegram_text(lead)


def test_email_text_contains_contacts_message_and_error(clock):
    lead = make_lead(message="Позвоните после 18:00", page="", config={"error": "Модель «x» не найдена"})

    text = email_text(lead)

    assert "Имя: Иван" in text and "Телефон: +79123456789" in text
    assert "Комментарий: Позвоните после 18:00" in text
    assert "⚠ Модель «x» не найдена" in text
    assert "Страница: —" in text
    assert "07.11.2026 12:00" in text, "время в часовом поясе Москвы"


def test_email_subject_strips_newlines():
    lead = make_lead(model_name="Bike\r\nBcc: x@evil")
    subject = email_subject(lead)
    assert "\n" not in subject and "\r" not in subject


def test_email_subject_falls_back_to_kind():
    lead = make_lead(kind=Lead.Kind.CONTACT)
    assert email_subject(lead) == f"Заявка №{lead.pk}: Сообщение"
