import datetime
import json
import os
import threading

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont

import config
import wallpaper_generator as wg

# ---------------------------------------------------------------------------
# hex_to_rgb
# ---------------------------------------------------------------------------

def test_hex_to_rgb_six_digit():
    assert wg.hex_to_rgb("#FF8000") == (255, 128, 0)


def test_hex_to_rgb_six_digit_lowercase():
    assert wg.hex_to_rgb("#ff8000") == (255, 128, 0)


def test_hex_to_rgb_six_digit_no_hash():
    assert wg.hex_to_rgb("FF8000") == (255, 128, 0)


def test_hex_to_rgb_three_digit_expands():
    assert wg.hex_to_rgb("#F80") == (255, 136, 0)


def test_hex_to_rgb_strips_whitespace():
    assert wg.hex_to_rgb("  #FFFFFF  ") == (255, 255, 255)


def test_hex_to_rgb_empty_returns_default():
    assert wg.hex_to_rgb("") == (255, 255, 255)


def test_hex_to_rgb_none_returns_default():
    assert wg.hex_to_rgb(None) == (255, 255, 255)


def test_hex_to_rgb_custom_default():
    assert wg.hex_to_rgb("", default=(1, 2, 3)) == (1, 2, 3)
    assert wg.hex_to_rgb("zzzzzz", default=(9, 9, 9)) == (9, 9, 9)


def test_hex_to_rgb_invalid_chars_returns_default():
    assert wg.hex_to_rgb("#GGGGGG") == (255, 255, 255)


def test_hex_to_rgb_wrong_length_returns_default():
    assert wg.hex_to_rgb("#12345") == (255, 255, 255)
    assert wg.hex_to_rgb("#1234567") == (255, 255, 255)


# ---------------------------------------------------------------------------
# wrap_text
# ---------------------------------------------------------------------------

@pytest.fixture
def draw_ctx():
    img = Image.new("RGB", (400, 100), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    return draw, font


def test_wrap_text_empty(draw_ctx):
    draw, font = draw_ctx
    assert wg.wrap_text("", font, 100, draw) == []


def test_wrap_text_whitespace_only(draw_ctx):
    draw, font = draw_ctx
    assert wg.wrap_text("   ", font, 100, draw) == []


def test_wrap_text_single_word(draw_ctx):
    draw, font = draw_ctx
    assert wg.wrap_text("hello", font, 5, draw) == ["hello"]


def test_wrap_text_preserves_all_words(draw_ctx):
    draw, font = draw_ctx
    text = "the quick brown fox jumps over the lazy dog"
    lines = wg.wrap_text(text, font, 30, draw)
    assert " ".join(lines).split() == text.split()


def test_wrap_text_produces_multiple_lines_when_narrow(draw_ctx):
    draw, font = draw_ctx
    text = "the quick brown fox jumps over the lazy dog"
    lines = wg.wrap_text(text, font, 30, draw)
    assert len(lines) > 1


def test_wrap_text_fits_single_line_when_wide(draw_ctx):
    draw, font = draw_ctx
    lines = wg.wrap_text("short quote", font, 10_000, draw)
    assert lines == ["short quote"]


# ---------------------------------------------------------------------------
# get_active_quote
# ---------------------------------------------------------------------------

SAMPLE_QUOTES = [
    {"text": "Quote one", "author": "A"},
    {"text": "Quote two", "author": "B"},
    {"text": "Quote three", "author": "C"},
]


@pytest.fixture
def quotes_env(fake_env):
    (fake_env.data / "quotes.json").write_text(
        json.dumps(SAMPLE_QUOTES), encoding="utf-8"
    )
    return fake_env


def test_quote_custom_mode(quotes_env):
    settings = {
        "quote_mode": "custom",
        "custom_quote": "  Be yourself  ",
        "custom_author": "  Someone  ",
    }
    text, author = wg.get_active_quote(settings)
    assert text == "Be yourself"
    assert author == "Someone"


def test_quote_custom_mode_defaults_when_blank(quotes_env):
    settings = {"quote_mode": "custom"}
    text, author = wg.get_active_quote(settings)
    assert text  # falls back to default string
    assert author


def test_quote_preset_index(quotes_env):
    settings = {"quote_mode": "preset", "preset_index": 1}
    text, author = wg.get_active_quote(settings)
    assert text == "Quote two"
    assert author == "B"


def test_quote_preset_out_of_range_uses_first(quotes_env):
    settings = {"quote_mode": "preset", "preset_index": 999}
    text, _ = wg.get_active_quote(settings)
    assert text == "Quote one"


def test_quote_preset_negative_index_uses_first(quotes_env):
    settings = {"quote_mode": "preset", "preset_index": -1}
    text, _ = wg.get_active_quote(settings)
    assert text == "Quote one"


def test_quote_daily_random_deterministic_same_seed(quotes_env):
    settings = {"quote_mode": "daily_random", "daily_seed": 7}
    a = wg.get_active_quote(dict(settings))
    b = wg.get_active_quote(dict(settings))
    assert a == b


def test_quote_daily_random_seed_shifts_index(quotes_env):
    a = wg.get_active_quote({"quote_mode": "daily_random", "daily_seed": 0})
    b = wg.get_active_quote({"quote_mode": "daily_random", "daily_seed": 1})
    assert a != b


def test_quote_daily_random_indexes_into_list(quotes_env):
    settings = {"quote_mode": "daily_random", "daily_seed": 0}
    text, author = wg.get_active_quote(settings)
    assert text in {q["text"] for q in SAMPLE_QUOTES}
    assert author in {q["author"] for q in SAMPLE_QUOTES}


def test_quote_empty_list_uses_fallback(monkeypatch):
    monkeypatch.setattr(config, "load_quotes", list)
    text, author = wg.get_active_quote({"quote_mode": "preset", "preset_index": 0})
    assert "masterpiece" in text
    assert author == "John Wooden"


# ---------------------------------------------------------------------------
# get_active_countdown
# ---------------------------------------------------------------------------

def _cd_settings(targets, index=0, show=True):
    return {
        "show_countdown": show,
        "countdown_index": index,
        "countdown_targets": targets,
    }


def test_countdown_disabled_returns_none():
    t = [{"label": "NY", "date": "2030-01-01", "yearly": False}]
    assert wg.get_active_countdown(_cd_settings(t, show=False)) is None


def test_countdown_no_targets_returns_none():
    assert wg.get_active_countdown(_cd_settings([])) is None


def test_countdown_missing_targets_key_returns_none():
    assert wg.get_active_countdown({"show_countdown": True}) is None


def test_countdown_index_out_of_range_returns_none():
    t = [{"label": "NY", "date": "2030-01-01", "yearly": False}]
    assert wg.get_active_countdown(_cd_settings(t, index=5)) is None


def test_countdown_non_numeric_index_defaults_to_zero():
    t = [
        {"label": "First", "date": "2030-01-01", "yearly": False},
        {"label": "Second", "date": "2030-02-01", "yearly": False},
    ]
    settings = _cd_settings(t, index="not-a-number")
    settings["countdown_index"] = "not-a-number"
    result = wg.get_active_countdown(settings)
    assert result["label"] == "First"


def test_countdown_empty_label_returns_none():
    t = [{"label": "  ", "date": "2030-01-01", "yearly": False}]
    assert wg.get_active_countdown(_cd_settings(t)) is None


def test_countdown_bad_date_length_returns_none():
    t = [{"label": "NY", "date": "2030-1-1", "yearly": False}]
    assert wg.get_active_countdown(_cd_settings(t)) is None


def test_countdown_invalid_calendar_date_returns_none():
    t = [{"label": "NY", "date": "2030-13-45", "yearly": False}]
    assert wg.get_active_countdown(_cd_settings(t)) is None


def test_countdown_past_one_off_returns_none():
    today = datetime.date(2026, 6, 15)
    t = [{"label": "NY", "date": "2026-01-01", "yearly": False}]
    assert wg.get_active_countdown(_cd_settings(t), today=today) is None


def test_countdown_future_one_off():
    today = datetime.date(2026, 6, 15)
    t = [{"label": "Launch", "date": "2026-07-01", "yearly": False}]
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert result["days"] == 16
    assert result["date"] == "2026-07-01"
    assert result["text"] == "16 DAYS UNTIL LAUNCH"


def test_countdown_today_zero_days():
    today = datetime.date(2026, 12, 31)
    t = [{"label": "New Year", "date": "2026-12-31", "yearly": False}]
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert result["days"] == 0
    assert result["text"] == "NEW YEAR IS TODAY"


def test_countdown_tomorrow_one_day():
    today = datetime.date(2026, 12, 30)
    t = [{"label": "New Year", "date": "2026-12-31", "yearly": False}]
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert result["days"] == 1
    assert result["text"] == "1 DAY UNTIL NEW YEAR"


def test_countdown_yearly_stays_in_year_when_future():
    today = datetime.date(2026, 6, 15)
    t = [{"label": "NY", "date": "2026-01-01", "yearly": True}]
    # Jan 1 already passed in 2026 -> rolls to 2027
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert result["date"] == "2027-01-01"
    assert result["days"] == (datetime.date(2027, 1, 1) - today).days


def test_countdown_yearly_future_this_year():
    today = datetime.date(2026, 6, 15)
    t = [{"label": "NY", "date": "2026-12-31", "yearly": True}]
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert result["date"] == "2026-12-31"


def test_countdown_yearly_past_rolls_over():
    today = datetime.date(2026, 1, 2)
    t = [{"label": "NY", "date": "2026-01-01", "yearly": True}]
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert result["date"] == "2027-01-01"


def test_countdown_selects_by_index():
    today = datetime.date(2026, 6, 15)
    t = [
        {"label": "First", "date": "2026-07-01", "yearly": False},
        {"label": "Second", "date": "2026-08-01", "yearly": False},
    ]
    result = wg.get_active_countdown(_cd_settings(t, index=1), today=today)
    assert result["label"] == "Second"


def test_countdown_null_target_returns_none():
    assert wg.get_active_countdown(_cd_settings([None])) is None


def test_countdown_uppercases_label_in_text():
    today = datetime.date(2026, 6, 15)
    t = [{"label": "my party", "date": "2026-07-01", "yearly": False}]
    result = wg.get_active_countdown(_cd_settings(t), today=today)
    assert "MY PARTY" in result["text"]


# ---------------------------------------------------------------------------
# requires_daily_update / current_wallpaper_path / cleanup
# ---------------------------------------------------------------------------

def test_requires_update_when_date_is_stale(fake_env):
    assert wg.requires_daily_update({"last_rendered_date": "2000-01-01"}) is True


def test_requires_update_when_today_has_no_file(fake_env):
    today = datetime.date.today().strftime("%Y-%m-%d")
    assert wg.requires_daily_update({"last_rendered_date": today}) is True


def test_requires_update_when_no_date_recorded(fake_env):
    assert wg.requires_daily_update({}) is True


def test_no_requires_update_when_todays_file_exists(fake_env):
    today = datetime.date.today().strftime("%Y-%m-%d")
    (fake_env.data / f"wallpaper_{today}.png").write_bytes(b"x")
    assert wg.requires_daily_update({"last_rendered_date": today}) is False


def test_no_requires_update_when_todays_bmp_exists(fake_env):
    today = datetime.date.today().strftime("%Y-%m-%d")
    (fake_env.data / f"wallpaper_{today}.bmp").write_bytes(b"x")
    assert wg.requires_daily_update({"last_rendered_date": today}) is False


def test_no_requires_update_when_legacy_file_exists(fake_env):
    today = datetime.date.today().strftime("%Y-%m-%d")
    (fake_env.data / "wallpaper_current.png").write_bytes(b"x")
    assert wg.requires_daily_update({"last_rendered_date": today}) is False


def test_current_wallpaper_path_none_when_empty(fake_env):
    assert wg.current_wallpaper_path() is None


def test_current_wallpaper_path_prefers_today(fake_env):
    today = datetime.date.today().strftime("%Y-%m-%d")
    p = fake_env.data / f"wallpaper_{today}.png"
    p.write_bytes(b"x")
    assert wg.current_wallpaper_path() == str(p)


def test_current_wallpaper_path_falls_back_to_newest(fake_env):
    (fake_env.data / "wallpaper_2020-01-01.png").write_bytes(b"x")
    (fake_env.data / "wallpaper_2024-06-01.png").write_bytes(b"x")
    result = wg.current_wallpaper_path()
    assert result is not None
    assert result.endswith("wallpaper_2024-06-01.png")


def test_cleanup_keeps_only_specified_wallpaper(fake_env):
    keep = fake_env.data / "wallpaper_2026-01-01.png"
    keep.write_bytes(b"keep")
    old_png = fake_env.data / "wallpaper_2025-12-31.png"
    old_png.write_bytes(b"old")
    old_bmp = fake_env.data / "wallpaper_2025-12-31.bmp"
    old_bmp.write_bytes(b"old")
    legacy = fake_env.data / "wallpaper_current.png"
    legacy.write_bytes(b"legacy")
    legacy_bmp = fake_env.data / "wallpaper_current.bmp"
    legacy_bmp.write_bytes(b"legacy")

    wg._cleanup_old_wallpapers(str(keep))

    assert keep.exists()
    assert not old_png.exists()
    assert not old_bmp.exists()
    assert not legacy.exists()
    assert not legacy_bmp.exists()


# ---------------------------------------------------------------------------
# Rendering (integration)
# ---------------------------------------------------------------------------

def test_preview_render_creates_valid_image(fake_env, tmp_path):
    settings = dict(config.DEFAULT_SETTINGS)
    out = str(tmp_path / "preview.png")
    wall, prev = wg.generate_wallpaper(
        settings,
        width=320,
        height=200,
        preview_only=True,
        preview_path=out,
    )
    assert wall is None
    assert prev == out
    assert os.path.exists(out)

    img = Image.open(out)
    # preview uses 0.5x scale
    assert img.size == (160, 100)


def test_full_render_creates_bmp_and_png(fake_env, tmp_path):
    settings = dict(config.DEFAULT_SETTINGS)
    out = str(tmp_path / "wallpaper.bmp")
    wall, prev = wg.generate_wallpaper(
        settings,
        width=640,
        height=360,
        output_path=out,
        preview_path=str(tmp_path / "prev.png"),
    )
    assert wall == out
    assert os.path.exists(out)
    assert os.path.exists(str(tmp_path / "wallpaper.png"))
    assert os.path.exists(prev)

    img = Image.open(out)
    assert img.size == (640, 360)
    assert img.format == "BMP"

    thumb = Image.open(prev)
    assert thumb.size[0] == 640  # preview_w = 640 for full renders


@pytest.mark.parametrize(
    "layout",
    ["ref_10", "balanced_20", "matrix_25", "calendar_53", "unknown_layout"],
)
def test_preview_render_all_layouts(fake_env, tmp_path, layout):
    settings = dict(config.DEFAULT_SETTINGS)
    settings["layout"] = layout
    out = str(tmp_path / f"p_{layout}.png")
    _, prev = wg.generate_wallpaper(
        settings,
        width=320,
        height=200,
        preview_only=True,
        preview_path=out,
    )
    assert os.path.exists(prev)
    assert Image.open(prev).size == (160, 100)


def test_render_with_countdown_and_quote(fake_env, tmp_path):
    settings = dict(config.DEFAULT_SETTINGS)
    settings["quote_mode"] = "custom"
    settings["custom_quote"] = "A short test quote for rendering."
    settings["custom_author"] = "Tester"
    settings["show_countdown"] = True
    settings["countdown_targets"] = [
        {"label": "Release", "date": "2030-01-01", "yearly": False}
    ]
    out = str(tmp_path / "with_extras.png")
    _, prev = wg.generate_wallpaper(
        settings, width=320, height=200, preview_only=True, preview_path=out
    )
    assert os.path.exists(prev)


def test_render_lock_is_reacquirable():
    assert wg.RENDER_LOCK.acquire(timeout=1)
    wg.RENDER_LOCK.release()


def test_concurrent_renders_serialize_without_error(fake_env, tmp_path):
    settings = dict(config.DEFAULT_SETTINGS)
    errors = []

    def worker(i):
        try:
            wg.generate_wallpaper(
                settings,
                width=160,
                height=100,
                preview_only=True,
                preview_path=str(tmp_path / f"p{i}.png"),
            )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    for i in range(4):
        assert (tmp_path / f"p{i}.png").exists()


# ---------------------------------------------------------------------------
# Regressions: self-deleted return file, edge clipping, cleanup scope
# ---------------------------------------------------------------------------

def _content_bbox(img, bg):
    diff = ImageChops.difference(img, Image.new("RGB", img.size, bg))
    return diff.getbbox()


def test_full_render_default_output_keeps_returned_file(fake_env, tmp_path):
    """generate_wallpaper() must not delete the file it returns."""
    settings = dict(config.DEFAULT_SETTINGS)
    (fake_env.data / "wallpaper_2025-12-31.png").write_bytes(b"old")
    (fake_env.data / "wallpaper_2025-12-31.bmp").write_bytes(b"old")

    wall, _ = wg.generate_wallpaper(
        settings,
        width=800,
        height=600,
        preview_path=str(tmp_path / "prev.png"),
    )

    assert wall is not None and wall.endswith(".bmp")
    assert os.path.exists(wall)
    png = os.path.splitext(wall)[0] + ".png"
    assert os.path.exists(png)
    # previous day's pair is cleaned up, today's pair survives
    assert not (fake_env.data / "wallpaper_2025-12-31.png").exists()
    assert not (fake_env.data / "wallpaper_2025-12-31.bmp").exists()


@pytest.mark.parametrize(
    "width,height,zoom",
    [
        (1280, 720, 1.0),
        (1024, 600, 1.0),
        (1920, 1080, 1.5),
    ],
)
def test_render_content_is_not_clipped_at_edges(fake_env, tmp_path, width, height, zoom):
    """Small screens / high zoom used to push content off the bottom edge."""
    settings = dict(config.DEFAULT_SETTINGS)
    settings["grid_zoom"] = zoom
    wall, _ = wg.generate_wallpaper(
        settings,
        width=width,
        height=height,
        output_path=str(tmp_path / f"edge_{width}x{height}.png"),
        preview_path=str(tmp_path / "prev.png"),
    )
    img = Image.open(wall).convert("RGB")
    bg = wg.hex_to_rgb(settings["color_bg"])
    bbox = _content_bbox(img, bg)
    label = f"{width}x{height} zoom={zoom}"
    assert bbox is not None, f"no content rendered at {label}"
    assert bbox[1] > 0, f"content touches the top edge at {label}"
    assert img.size[1] - bbox[3] > 0, f"content touches the bottom edge at {label}"


def test_cleanup_keeps_current_png_and_bmp_pair(fake_env):
    keep_png = fake_env.data / "wallpaper_2026-01-01.png"
    keep_bmp = fake_env.data / "wallpaper_2026-01-01.bmp"
    old_png = fake_env.data / "wallpaper_2025-12-31.png"
    old_bmp = fake_env.data / "wallpaper_2025-12-31.bmp"
    for p in (keep_png, keep_bmp, old_png, old_bmp):
        p.write_bytes(b"x")

    wg._cleanup_old_wallpapers(str(keep_png))

    assert keep_png.exists()
    assert keep_bmp.exists()
    assert not old_png.exists()
    assert not old_bmp.exists()


def test_cleanup_never_touches_files_outside_data_dir(fake_env, tmp_path):
    inside = fake_env.data / "wallpaper_2026-01-01.png"
    inside.write_bytes(b"keep me")

    wg._cleanup_old_wallpapers(str(tmp_path / "wallpaper_2026-01-01.png"))

    assert inside.exists()


def test_requires_update_ignores_stale_stamp_when_todays_file_exists(fake_env):
    today = datetime.date.today().strftime("%Y-%m-%d")
    (fake_env.data / f"wallpaper_{today}.png").write_bytes(b"x")
    assert wg.requires_daily_update({"last_rendered_date": "2000-01-01"}) is False


# ---------------------------------------------------------------------------
# Regressions: countdown dates
# ---------------------------------------------------------------------------

def test_countdown_yearly_feb29_non_leap_year_rolls_to_march_1():
    today = datetime.date(2027, 1, 10)
    cd = wg.get_active_countdown(
        {
            "show_countdown": True,
            "countdown_index": 0,
            "countdown_targets": [{"label": "Leap", "date": "2027-02-29", "yearly": True}],
        },
        today,
    )
    assert cd is not None
    assert cd["date"] == "2027-03-01"
    assert cd["days"] == (datetime.date(2027, 3, 1) - today).days


def test_countdown_yearly_feb29_rolls_to_next_leap_year_once_passed():
    today = datetime.date(2027, 4, 1)
    cd = wg.get_active_countdown(
        {
            "show_countdown": True,
            "countdown_index": 0,
            "countdown_targets": [{"label": "Leap", "date": "2027-02-29", "yearly": True}],
        },
        today,
    )
    assert cd is not None
    assert cd["date"] == "2028-02-29"


def test_countdown_yearly_feb29_kept_in_leap_year():
    today = datetime.date(2028, 1, 10)
    cd = wg.get_active_countdown(
        {
            "show_countdown": True,
            "countdown_index": 0,
            "countdown_targets": [{"label": "Leap", "date": "2028-02-29", "yearly": True}],
        },
        today,
    )
    assert cd is not None
    assert cd["date"] == "2028-02-29"
