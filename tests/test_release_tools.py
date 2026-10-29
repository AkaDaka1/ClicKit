"""Тесты инструментов релиза: версия, артефакты, заметки CHANGELOG."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import pytest

from app.version import APP_VERSION
from scripts import release_notes, verify_release

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"


def test_pyproject_version_matches_app_version() -> None:
    """Версия в pyproject.toml совпадает с APP_VERSION — единый источник."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["version"] == APP_VERSION


def test_check_version_accepts_matching_tag() -> None:
    """Тег v<APP_VERSION> проходит проверку версии."""
    assert verify_release.check_version(f"v{APP_VERSION}") == []


def test_check_version_rejects_other_tag() -> None:
    """Чужой тег не проходит проверку: версия обязана совпадать."""
    problems = verify_release.check_version("v999.0.0")

    assert problems
    assert "тег v999.0.0" in problems[0]


def test_check_artifacts_reports_missing_files(tmp_path: Path) -> None:
    """В пустом каталоге скрипт сообщает об отсутствии всех артефактов."""
    problems = verify_release.check_artifacts(tmp_path)

    missing = [item for item in problems if item.startswith("нет файла:")]
    assert len(missing) == 3


def test_find_notice_inside_onedir(tmp_path: Path) -> None:
    """`build_exe.py` кладёт NOTICE рядом с `.exe` — это тоже валидно."""
    onedir = tmp_path / "ClicKit"
    onedir.mkdir()
    notice = onedir / "NOTICE.txt"
    notice.write_text("MIT", encoding="utf-8")

    assert verify_release.find_notice(tmp_path) == notice


def test_find_notice_prefers_dist_root(tmp_path: Path) -> None:
    """Копия в корне `dist/` (артефакт релиза) имеет приоритет."""
    (tmp_path / "ClicKit").mkdir()
    (tmp_path / "ClicKit" / "NOTICE.txt").write_text("MIT", encoding="utf-8")
    root_notice = tmp_path / "NOTICE.txt"
    root_notice.write_text("MIT", encoding="utf-8")

    assert verify_release.find_notice(tmp_path) == root_notice


def test_check_checksums_accepts_valid_file(tmp_path: Path) -> None:
    """Совпадающая контрольная сумма не даёт замечаний."""
    artifact = tmp_path / "ClicKit-win64.zip"
    artifact.write_bytes(b"clickit")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{digest}  {artifact.name}\n", encoding="utf-8"
    )

    assert verify_release.check_checksums(tmp_path) == []


def test_check_checksums_detects_mismatch(tmp_path: Path) -> None:
    """Изменённый файл ловится сравнением SHA-256."""
    artifact = tmp_path / "ClicKit-win64.zip"
    artifact.write_bytes(b"clickit")
    digest = hashlib.sha256(b"other").hexdigest()
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{digest}  {artifact.name}\n", encoding="utf-8"
    )

    problems = verify_release.check_checksums(tmp_path)

    assert problems == [f"{artifact.name}: SHA-256 не совпадает"]


def test_check_checksums_reports_missing_artifact(tmp_path: Path) -> None:
    """Строка суммы для отсутствующего файла — ошибка, а не молчание."""
    digest = hashlib.sha256(b"clickit").hexdigest()
    (tmp_path / "SHA256SUMS.txt").write_text(
        f"{digest}  ClicKit.exe\n", encoding="utf-8"
    )

    problems = verify_release.check_checksums(tmp_path)

    assert problems == ["SHA256SUMS.txt: нет артефакта ClicKit.exe"]


def test_smoke_run_requires_built_exe(tmp_path: Path) -> None:
    """Без собранной onedir-папки смоук-запуск не выполняется."""
    problems = verify_release.smoke_run(tmp_path, timeout=1.0)

    assert len(problems) == 1
    assert "смоук-запуск" in problems[0]


def test_main_reports_success_for_matching_version(
    capsys: pytest.CaptureFixture,
) -> None:
    """CLI с корректным тегом возвращает 0 и печатает итог."""
    code = verify_release.main(["--tag", f"v{APP_VERSION}", "--no-artifacts"])

    assert code == 0
    assert "Проверка релиза пройдена" in capsys.readouterr().out


def test_main_reports_failure_for_unknown_tag(capsys: pytest.CaptureFixture) -> None:
    """CLI с неверным тегом возвращает 1 и перечисляет проблемы."""
    code = verify_release.main(["--tag", "v0.0.1", "--no-artifacts"])

    assert code == 1
    assert "v0.0.1" in capsys.readouterr().out


def test_extract_notes_returns_release_section() -> None:
    """Раздел текущей версии вытаскивается без ссылочных строк."""
    notes = release_notes.extract_notes(CHANGELOG.read_text(encoding="utf-8"), "1.0.0")

    assert "Первый публичный релиз" in notes
    assert "### Добавлено" in notes
    assert "[1.0.0]:" not in notes
    assert notes.endswith("\n")


def test_extract_notes_unknown_version_raises() -> None:
    """Для версии без раздела — понятная ошибка."""
    with pytest.raises(LookupError, match="1.2.3"):
        release_notes.extract_notes(CHANGELOG.read_text(encoding="utf-8"), "1.2.3")


def test_extract_notes_skips_next_release() -> None:
    """Тело раздела заканчивается на заголовке следующей версии."""
    changelog = (
        "# CHANGELOG\n\n## [2.0.0] — 2027-01-01\n\n- новая версия\n\n"
        "## [1.0.0] — 2026-01-01\n\n- старая версия\n\n[1.0.0]: https://example\n"
    )

    notes = release_notes.extract_notes(changelog, "1.0.0")

    assert notes.strip() == "- старая версия"


def test_is_prerelease_detects_suffix() -> None:
    """Суффикс версии означает предварительный релиз."""
    assert release_notes.is_prerelease("1.1.0-rc.1") is True
    assert release_notes.is_prerelease("1.0.0") is False


def test_release_notes_cli_writes_notes_and_flag(tmp_path: Path) -> None:
    """CLI сохраняет заметки и флаг pre-release в указанные файлы."""
    notes_file = tmp_path / "notes.md"
    flag_file = tmp_path / "prerelease.txt"

    code = release_notes.main(
        [
            "--version",
            "1.0.0",
            "--output",
            str(notes_file),
            "--prerelease-flag",
            str(flag_file),
        ]
    )

    assert code == 0
    assert "Первый публичный релиз" in notes_file.read_text(encoding="utf-8")
    assert flag_file.read_text(encoding="utf-8") == "false"


def test_release_notes_cli_fails_without_section(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Отсутствующий раздел CHANGELOG даёт код 1 и сообщение в stderr."""
    code = release_notes.main(["--version", "9.9.9"])

    assert code == 1
    assert "9.9.9" in capsys.readouterr().err
