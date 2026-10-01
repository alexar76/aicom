"""'uvicorn_failed_to_listen' with no cause is feedback nobody can act on."""

from web.backend.services.sandbox_preview_api import summarize_startup_failure

CELERY = """/venv/lib/python3.12/site-packages/pydantic/_internal/_config.py:334: UserWarning: Valid config keys have changed in V2:
* 'orm_mode' has been renamed to 'from_attributes'
  warnings.warn(message, UserWarning)
INFO:     Started server process [1064]
INFO:     Waiting for application startup.
ERROR:    Traceback (most recent call last):
  File "/venv/lib/python3.12/site-packages/kombu/utils/functional.py", line 30, in __call__
    return self.value
kombu.exceptions.OperationalError: [Errno 111] Connection refused
"""

POSTGRES = """INFO:     Waiting for application startup.
Traceback (most recent call last):
  File "/app/db.py", line 9, in connect
    engine.connect()
sqlalchemy.exc.OperationalError: could not connect to server: Connection refused
"""


def test_celery_startup_dependency_is_named_as_a_design_finding():
    out = summarize_startup_failure(CELERY)
    assert "kombu.exceptions.OperationalError" in out
    assert "broker" in out.lower()
    assert "serverless" in out.lower()


def test_database_startup_dependency_suggests_the_sqlite_fallback():
    out = summarize_startup_failure(POSTGRES)
    assert "OperationalError" in out
    assert "sqlite" in out.lower()


def test_traceback_frames_and_warnings_are_dropped():
    out = summarize_startup_failure(CELERY)
    assert "File \"" not in out
    assert "UserWarning" not in out
    assert "orm_mode" not in out


def test_empty_input_is_empty_output():
    assert summarize_startup_failure("") == ""
    assert summarize_startup_failure("\n\n") == ""


def test_output_is_bounded():
    assert len(summarize_startup_failure("SomeError: " + "x" * 5000)) <= 700
