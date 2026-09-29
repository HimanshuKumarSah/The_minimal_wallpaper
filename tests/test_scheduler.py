import datetime
import re
import time

import scheduler as sched_mod
from scheduler import DailyScheduler


def test_initial_state_sets_today_and_not_running():
    s = DailyScheduler(lambda **kw: None)
    assert s.running is False
    assert s.thread is None
    assert s.last_updated_date == datetime.date.today().strftime("%Y-%m-%d")


def test_start_sets_running_and_daemon_thread():
    s = DailyScheduler(lambda **kw: None)
    s.start()
    try:
        assert s.running is True
        assert s.thread is not None
        assert s.thread.daemon is True
    finally:
        s.stop()
        s.thread.join(timeout=3)


def test_start_is_idempotent():
    s = DailyScheduler(lambda **kw: None)
    s.start()
    try:
        t = s.thread
        s.start()
        assert s.thread is t
    finally:
        s.stop()
        s.thread.join(timeout=3)


def test_stop_clears_running():
    s = DailyScheduler(lambda **kw: None)
    s.start()
    assert s.running is True
    s.stop()
    assert s.running is False
    s.thread.join(timeout=3)


def test_date_change_triggers_callback(monkeypatch):
    triggers = []
    s = DailyScheduler(lambda **kw: triggers.append(kw))
    s.last_updated_date = "2000-01-01"
    s.running = True

    def fake_sleep(_sec):
        s.running = False

    monkeypatch.setattr(time, "sleep", fake_sleep)
    s._run_loop()

    assert len(triggers) == 1
    assert triggers[0]["reason"] == "midnight_daily_update"
    assert s.last_updated_date == datetime.date.today().strftime("%Y-%m-%d")


def test_same_date_does_not_trigger(monkeypatch):
    triggers = []
    s = DailyScheduler(lambda **kw: triggers.append(kw))
    s.last_updated_date = datetime.date.today().strftime("%Y-%m-%d")
    s.running = True

    def fake_sleep(_sec):
        s.running = False

    monkeypatch.setattr(time, "sleep", fake_sleep)
    s._run_loop()

    assert triggers == []


def test_callback_exception_does_not_crash_loop(monkeypatch):
    calls = {"n": 0}

    def bad_callback(**kw):
        calls["n"] += 1
        raise RuntimeError("boom")

    s = DailyScheduler(bad_callback)
    s.last_updated_date = "2000-01-01"
    s.running = True

    def fake_sleep(_sec):
        s.running = False

    monkeypatch.setattr(time, "sleep", fake_sleep)
    s._run_loop()  # must not raise

    assert calls["n"] == 1
    assert s.last_updated_date == datetime.date.today().strftime("%Y-%m-%d")


def test_date_error_in_loop_does_not_crash(monkeypatch):
    """A failure while formatting the date must be swallowed by the loop."""
    triggers = []
    s = DailyScheduler(lambda **kw: triggers.append(kw))
    s.running = True

    class BoomDate:
        @staticmethod
        def today():
            raise OSError("clock broken")

    class FakeDatetimeModule:
        date = BoomDate

    monkeypatch.setattr(sched_mod, "datetime", FakeDatetimeModule)
    monkeypatch.setattr(time, "sleep", lambda _s: setattr(s, "running", False))
    s._run_loop()  # must not raise
    assert triggers == []


def test_get_time_until_midnight_in_range():
    h, m, sec = DailyScheduler.get_time_until_midnight()
    assert 0 <= h <= 24
    assert 0 <= m <= 59
    assert 0 <= sec <= 59
    total = h * 3600 + m * 60 + sec
    assert 0 <= total <= 86400


def test_get_time_until_midnight_str_format():
    text = DailyScheduler.get_time_until_midnight_str()
    match = re.fullmatch(r"(\d{1,2})h (\d{1,2})m (\d{1,2})s", text)
    assert match, f"unexpected format: {text!r}"
    h, m, sec = (int(g) for g in match.groups())
    assert 0 <= h <= 24
    assert 0 <= m <= 59
    assert 0 <= sec <= 59
    # Same value as the tuple form (allow a one-second tick between calls)
    th, tm, tsec = DailyScheduler.get_time_until_midnight()
    assert abs((h * 3600 + m * 60 + sec) - (th * 3600 + tm * 60 + tsec)) <= 1


def test_get_time_until_midnight_at_exact_midnight(monkeypatch):
    class FakeDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 15, 0, 0, 0)

    monkeypatch.setattr(datetime, "datetime", FakeDateTime)
    h, m, sec = DailyScheduler.get_time_until_midnight()
    assert h == 24
    assert m == 0
    assert sec == 0
