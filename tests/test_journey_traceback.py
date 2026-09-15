"""A 500 without its traceback is feedback nobody can act on."""

from web.backend.services.product_demo_journey import tracebacks_from_stderr

STDERR = '''INFO:     Started server process [42]
INFO:     Application startup complete.
Traceback (most recent call last):
  File "/app/api/routes/operator.py", line 88, in spend
    total = settings.daily_budget_usd
            ^^^^^^^^
AttributeError: 'Settings' object has no attribute 'daily_budget_usd'
INFO:     127.0.0.1:1 - "GET /api/operator/spend HTTP/1.1" 500 Internal Server Error
'''


def test_the_exception_is_extracted_without_the_frames():
    out = tracebacks_from_stderr(STDERR)
    assert out == ["AttributeError: 'Settings' object has no attribute 'daily_budget_usd'"]


def test_duplicate_tracebacks_are_reported_once():
    out = tracebacks_from_stderr(STDERR + STDERR + STDERR)
    assert len(out) == 1


def test_distinct_exceptions_are_all_kept_up_to_the_limit():
    other = STDERR.replace("AttributeError: 'Settings' object has no attribute 'daily_budget_usd'",
                           "KeyError: 'missing'")
    out = tracebacks_from_stderr(STDERR + other)
    assert len(out) == 2
    assert any("KeyError" in o for o in out)


def test_limit_is_respected():
    blob = "".join(
        STDERR.replace("daily_budget_usd", f"attr_{i}") for i in range(10)
    )
    assert len(tracebacks_from_stderr(blob, limit=2)) == 2


def test_no_traceback_yields_nothing():
    assert tracebacks_from_stderr("INFO: all fine\n") == []
    assert tracebacks_from_stderr("") == []
