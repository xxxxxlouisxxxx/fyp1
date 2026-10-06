"""Regression checks for narrow secret scanner fixture exceptions."""

import importlib.util
from pathlib import Path

from scripts import secret_scan


def scanner():
    path = Path(__file__).resolve().parents[2] / "scripts/secret_scan.py"
    spec = importlib.util.spec_from_file_location("platform_secret_scan", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_assignments_do_not_cross_lines():
    assert not scanner().has_credentials(
        "DATAFORSEO_LOGIN" + "=\n" + "DATAFORSEO_PASSWORD" + "=\n",
        Path("docs/spec.md"),
    )


def test_fixture_exception_does_not_hide_other_values():
    check = scanner().has_credentials
    fixture = Path("tests/unit/test_settings.py")
    assignment = "DATAFORSEO_LOGIN" + "="
    assert not check(assignment + "dotenv-login\\n", fixture)
    assert check(assignment + "real-looking-value", fixture)
    assert check(assignment + "dotenv-login", Path("src/config.py"))


def test_scanner_skips_database_and_monthly_environment(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    database = tmp_path / "locked.duckdb"
    database.touch()
    environment = tmp_path / ".venv-monthly"
    environment.mkdir()
    (environment / "dependency.py").touch()
    original = Path.read_text

    def guarded_read(path: Path, *args, **kwargs):
        if path == database or environment in path.parents:
            raise AssertionError("Non-source file read")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert secret_scan.main() == 0
    assert capsys.readouterr().out == "Secret scan passed\n"


def test_scanner_fails_closed_without_content_on_unreadable_source(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    (tmp_path / "unreadable.py").touch()

    def denied_read(path: Path, *args, **kwargs):
        raise PermissionError("sensitive error detail")

    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    monkeypatch.setattr(Path, "read_text", denied_read)
    assert secret_scan.main() == 1
    assert capsys.readouterr().out == "Secret scan could not read: unreadable.py\n"