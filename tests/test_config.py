import datetime
import json
import os
import re

import pytest

import config

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------------------
# Static data integrity
# ---------------------------------------------------------------------------

def test_default_settings_json_serializable():
    json.dumps(config.DEFAULT_SETTINGS)


def test_color_themes_json_serializable():
    json.dumps(config.COLOR_THEMES)


def test_default_color_theme_exists():
    assert config.DEFAULT_SETTINGS["color_theme"] in config.COLOR_THEMES


def test_default_font_face_exists():
    assert config.DEFAULT_SETTINGS["font_face"] in config.FONT_PRESETS


def test_default_layout_is_known():
    known = {"ref_10", "balanced_20", "matrix_25", "calendar_53"}
    assert config.DEFAULT_SETTINGS["layout"] in known


def test_default_grid_zoom_in_range():
    z = config.DEFAULT_SETTINGS["grid_zoom"]
    assert isinstance(z, float)
    assert 0.5 <= z <= 2.2


def test_default_colors_match_selected_theme():
    theme = config.COLOR_THEMES[config.DEFAULT_SETTINGS["color_theme"]]
    for key in (
        "color_bg",
        "color_passed",
        "color_current",
        "color_coming",
        "color_text_primary",
        "color_text_secondary",
    ):
        assert config.DEFAULT_SETTINGS[key] == theme[key], key


@pytest.mark.parametrize("theme_key", list(config.COLOR_THEMES.keys()))
def test_theme_colors_are_valid_hex(theme_key):
    theme = config.COLOR_THEMES[theme_key]
    assert "name" in theme
    for prop, val in theme.items():
        if prop == "name":
            continue
        assert isinstance(val, str), f"{theme_key}.{prop}"
        assert HEX_RE.match(val), f"{theme_key}.{prop} = {val!r} is not #RRGGBB"


def test_countdown_defaults_shape():
    targets = config.DEFAULT_SETTINGS["countdown_targets"]
    assert isinstance(targets, list) and targets
    t = targets[0]
    assert {"label", "date", "yearly"} <= set(t)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", t["date"])


def test_countdown_seed_date_is_next_jan1():
    d = config._countdown_seed_date()
    y, m, day = map(int, d.split("-"))
    assert (m, day) == (1, 1)
    assert y == datetime.date.today().year + 1


# ---------------------------------------------------------------------------
# Settings load / save
# ---------------------------------------------------------------------------

def test_load_settings_returns_defaults_when_missing(fake_env):
    s = config.load_settings()
    assert s == config.DEFAULT_SETTINGS


def test_save_and_load_roundtrip(fake_env):
    s = dict(config.DEFAULT_SETTINGS)
    s["layout"] = "matrix_25"
    s["grid_zoom"] = 1.5
    assert config.save_settings(s) is True

    loaded = config.load_settings()
    assert loaded["layout"] == "matrix_25"
    assert loaded["grid_zoom"] == 1.5
    assert loaded["font_face"] == s["font_face"]


def test_load_settings_partial_file_merges_over_defaults(fake_env):
    (fake_env.data / "settings.json").write_text(
        json.dumps({"layout": "calendar_53"}), encoding="utf-8"
    )
    s = config.load_settings()
    assert s["layout"] == "calendar_53"
    assert s["font_face"] == config.DEFAULT_SETTINGS["font_face"]


def test_load_settings_corrupt_json_returns_defaults(fake_env):
    (fake_env.data / "settings.json").write_text("{not valid json", encoding="utf-8")
    s = config.load_settings()
    assert s == config.DEFAULT_SETTINGS


def test_load_settings_non_dict_json_returns_defaults(fake_env):
    (fake_env.data / "settings.json").write_text("[1, 2, 3]", encoding="utf-8")
    s = config.load_settings()
    assert s == config.DEFAULT_SETTINGS


def test_save_settings_invalid_path_returns_false(monkeypatch, tmp_path):
    bad = str(tmp_path / "no_such_dir" / "nested" / "settings.json")
    monkeypatch.setattr(config, "SETTINGS_FILE", bad)
    assert config.save_settings({}) is False


def test_stamp_rendered_date(fake_env):
    assert config.stamp_rendered_date() is True
    s = config.load_settings()
    assert s["last_rendered_date"] == datetime.date.today().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

def test_migrate_copies_legacy_file(fake_env):
    legacy = fake_env.app / "settings.json"
    legacy.write_text(json.dumps({"layout": "ref_10"}), encoding="utf-8")
    target = fake_env.data / "settings.json"
    assert not target.exists()

    config._migrate_legacy_file("settings.json", str(target))
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"layout": "ref_10"}


def test_migrate_noop_when_target_exists(fake_env):
    target = fake_env.data / "settings.json"
    target.write_text(json.dumps({"layout": "keep"}), encoding="utf-8")
    (fake_env.app / "settings.json").write_text(
        json.dumps({"layout": "legacy"}), encoding="utf-8"
    )

    config._migrate_legacy_file("settings.json", str(target))
    assert json.loads(target.read_text(encoding="utf-8")) == {"layout": "keep"}


def test_migrate_noop_when_legacy_missing(fake_env):
    target = fake_env.data / "settings.json"
    config._migrate_legacy_file("settings.json", str(target))
    assert not target.exists()


def test_load_settings_applies_migrated_legacy(fake_env):
    (fake_env.app / "settings.json").write_text(
        json.dumps({"layout": "calendar_53"}), encoding="utf-8"
    )
    s = config.load_settings()
    assert s["layout"] == "calendar_53"
    assert (fake_env.data / "settings.json").exists()


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------

SAMPLE_QUOTES = [
    {"text": "Quote one", "author": "A", "category": "X"},
    {"text": "Quote two", "author": "B", "category": "Y"},
    {"text": "Quote three", "author": "C", "category": "Z"},
]


def test_load_quotes_reads_existing_file(fake_env):
    (fake_env.data / "quotes.json").write_text(
        json.dumps(SAMPLE_QUOTES), encoding="utf-8"
    )
    assert config.load_quotes() == SAMPLE_QUOTES


def test_load_quotes_missing_returns_fallback(fake_env):
    quotes = config.load_quotes()
    assert len(quotes) == 1
    assert quotes[0]["author"] == "Confucius"


def test_load_quotes_empty_returns_fallback(fake_env):
    (fake_env.data / "quotes.json").write_text("[]", encoding="utf-8")
    quotes = config.load_quotes()
    assert len(quotes) == 1
    assert quotes[0]["author"] == "Confucius"


def test_load_quotes_corrupt_returns_fallback(fake_env):
    (fake_env.data / "quotes.json").write_text("not-json", encoding="utf-8")
    quotes = config.load_quotes()
    assert len(quotes) == 1
    assert quotes[0]["author"] == "Confucius"


def test_load_quotes_seeds_from_resource_bundle(fake_env):
    bundle = [{"text": "From bundle", "author": "Bundle Author"}]
    (fake_env.resources / "quotes.json").write_text(
        json.dumps(bundle), encoding="utf-8"
    )
    quotes = config.load_quotes()
    assert quotes == bundle
    assert (fake_env.data / "quotes.json").exists()


def test_load_quotes_does_not_overwrite_existing(fake_env):
    existing = [{"text": "Existing", "author": "E"}]
    (fake_env.data / "quotes.json").write_text(
        json.dumps(existing), encoding="utf-8"
    )
    (fake_env.resources / "quotes.json").write_text(
        json.dumps([{"text": "Bundle"}]), encoding="utf-8"
    )
    assert config.load_quotes() == existing


def test_load_quotes_seeds_from_app_dir_bundle(fake_env):
    bundle = [{"text": "App bundle", "author": "AB"}]
    (fake_env.app / "quotes.json").write_text(json.dumps(bundle), encoding="utf-8")
    quotes = config.load_quotes()
    assert quotes == bundle


def test_load_quotes_seeds_from_second_bundle_when_first_fails(fake_env):
    # The bundled resource copy is unreadable (a directory), so seeding must
    # fall through to the app-dir bundle instead of stopping after one attempt.
    (fake_env.resources / "quotes.json").mkdir()
    bundle = [{"text": "From app dir", "author": "App"}]
    (fake_env.app / "quotes.json").write_text(json.dumps(bundle), encoding="utf-8")

    quotes = config.load_quotes()

    assert quotes == bundle
    assert (fake_env.data / "quotes.json").exists()


def test_load_quotes_rejects_unexpected_shape(fake_env):
    (fake_env.data / "quotes.json").write_text(
        json.dumps({"text": "not a list"}), encoding="utf-8"
    )
    quotes = config.load_quotes()
    assert len(quotes) == 1
    assert quotes[0]["author"] == "Confucius"


# ---------------------------------------------------------------------------
# Regressions: atomic settings write
# ---------------------------------------------------------------------------

def test_save_settings_failure_preserves_existing_file(fake_env, monkeypatch):
    assert config.save_settings(dict(config.DEFAULT_SETTINGS)) is True
    with open(config.SETTINGS_FILE, "r", encoding="utf-8") as f:
        before = f.read()

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(config.json, "dump", _boom)

    changed = dict(config.DEFAULT_SETTINGS)
    changed["grid_zoom"] = 2.0
    assert config.save_settings(changed) is False

    with open(config.SETTINGS_FILE, "r", encoding="utf-8") as f:
        after = f.read()
    assert after == before
    assert not os.path.exists(config.SETTINGS_FILE + ".tmp")


def test_save_settings_leaves_no_temp_file_on_success(fake_env):
    assert config.save_settings(dict(config.DEFAULT_SETTINGS)) is True
    assert os.path.exists(config.SETTINGS_FILE)
    assert not os.path.exists(config.SETTINGS_FILE + ".tmp")
    # and the result is readable back
    assert config.load_settings()["color_theme"] == config.DEFAULT_SETTINGS["color_theme"]
