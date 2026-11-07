"""Резервирование SQLite, подготовка контейнера и расписание без реальной сети."""
import json
import sqlite3
import tarfile
from contextlib import closing
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command, CommandError

from tests.factories import make_lead

pytestmark = pytest.mark.django_db(transaction=True)


def test_backup_preserves_database_and_media(settings, tmp_path, monkeypatch, clock):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_ROOT.mkdir()
    (settings.MEDIA_ROOT / "photo.webp").write_bytes(b"original-photo")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    lead = make_lead()
    output = StringIO()
    call_command("backup_site", stdout=output)
    folders = list((tmp_path / "backups").glob("site-*"))
    assert len(folders) == 1
    with closing(sqlite3.connect(folders[0] / "db.sqlite3")) as restored:
        assert restored.execute("SELECT name FROM leads_lead WHERE id=?", [lead.pk]).fetchone() == ("Иван",)
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with tarfile.open(folders[0] / "media.tar.gz") as archive:
        assert archive.extractfile("media/photo.webp").read() == b"original-photo"
    assert json.loads((folders[0] / "metadata.json").read_text())["created_at"] == clock.current.isoformat()
    assert "Иван" not in output.getvalue()


def test_backup_names_are_unique_and_no_source_data_is_deleted(settings, tmp_path, monkeypatch, clock):
    settings.MEDIA_ROOT = tmp_path / "media"
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    make_lead()
    for _ in range(2):
        call_command("backup_site", stdout=StringIO())
    assert len(list((tmp_path / "backups").glob("site-*"))) == 2
    from apps.leads.models import Lead
    assert Lead.objects.count() == 1


def test_failed_backup_does_not_publish_incomplete_archive(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    from apps.pages.management.commands import backup_site
    monkeypatch.setattr(backup_site.tarfile, "open", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(CommandError, match="Резервная копия"):
        call_command("backup_site")
    assert not list((tmp_path / "backups").glob("site-*"))


def test_prepare_runs_backup_before_migrations_and_never_seeds(settings, tmp_path, monkeypatch):
    from apps.pages.management.commands import prepare_container
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.MEDIA_ROOT = tmp_path / "media"
    (settings.DATA_DIR / "db.sqlite3").write_bytes(b"existing database")
    calls = []
    monkeypatch.setattr(prepare_container, "call_command", lambda name, **kw: calls.append(name))
    call_command("prepare_container")
    assert calls == ["backup_site", "check", "migrate", "collectstatic"]
    assert settings.MEDIA_ROOT.is_dir()


def test_prepare_aborts_when_backup_fails(settings, tmp_path, monkeypatch):
    from apps.pages.management.commands import prepare_container
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.MEDIA_ROOT = tmp_path / "media"
    (settings.DATA_DIR / "db.sqlite3").write_bytes(b"existing database")
    calls = []
    def fail(name, **kw):
        calls.append(name)
        raise CommandError("backup failed")
    monkeypatch.setattr(prepare_container, "call_command", fail)
    with pytest.raises(CommandError):
        call_command("prepare_container")
    assert calls == ["backup_site"]


def test_first_prepare_creates_directories_without_backup(settings, tmp_path, monkeypatch):
    from apps.pages.management.commands import prepare_container
    settings.DATA_DIR = tmp_path / "new-data"
    settings.MEDIA_ROOT = tmp_path / "new-media"
    calls = []
    monkeypatch.setattr(prepare_container, "call_command", lambda name, **kw: calls.append(name))
    call_command("prepare_container")
    assert calls == ["check", "migrate", "collectstatic"]
    assert settings.DATA_DIR.is_dir() and settings.MEDIA_ROOT.is_dir()


def test_maintenance_runs_due_jobs_and_handles_failure(monkeypatch, clock):
    from apps.pages.management.commands import run_maintenance as module
    calls, handlers = [], {}
    def command(name, **kwargs):
        calls.append(name)
        if name == "update_rate":
            raise CommandError("network unavailable")
    class Stop:
        stopped = False
        def is_set(self):
            return self.stopped
        def set(self):
            self.stopped = True
        def wait(self, seconds):
            if len(calls) == 1:
                clock.set(clock.current + timedelta(days=1))
            else:
                self.set()
    monkeypatch.setattr(module, "call_command", command)
    monkeypatch.setattr(module, "Event", Stop)
    monkeypatch.setattr(module.signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))
    call_command("run_maintenance")
    assert calls.count("update_rate") == 2
    assert "purge_leads" in calls and "backup_site" in calls
    assert module.signal.SIGTERM in handlers


def test_maintenance_once_does_not_sleep(monkeypatch, clock):
    from apps.pages.management.commands import run_maintenance as module
    calls = []
    monkeypatch.setattr(module, "call_command", lambda name, **kw: calls.append(name))
    call_command("run_maintenance", once=True)
    assert calls == ["update_rate"]
