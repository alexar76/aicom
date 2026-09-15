"""Minimal FastAPI app for CI: validates uvicorn preview + declarative login scenarios."""

from __future__ import annotations

import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

_HOMEPAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Fixture home</title></head>
<body>
<h1>E2E fixture home</h1>
<p>This synthetic app validates FastAPI preview plus declarative login scenarios in CI.</p>
<p><a href="/login">Go to login</a></p>
</body></html>
"""


def _login_page(error: str | None = None) -> str:
    err = f'<p role="alert">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Login</title></head>
<body>
<h1>Sign in</h1>
{err}
<form method="post" action="/login">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" autocomplete="username" value="" />
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" />
  <button type="submit">Sign in</button>
</form>
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(_HOMEPAGE)


@app.get("/login", response_class=HTMLResponse)
def login_get() -> HTMLResponse:
    return HTMLResponse(_login_page())


@app.post("/login")
def login_post(email: str = Form(), password: str = Form()):
    ok_email = os.environ.get("AIFACTORY_E2E_EMAIL", "e2e-user@example.invalid")
    ok_pass = os.environ.get("AIFACTORY_E2E_PASSWORD", "e2e-password-change-me")
    if email.strip() == ok_email and password == ok_pass:
        r = RedirectResponse(url="/dashboard", status_code=303)
        r.set_cookie(
            key="e2e_auth",
            value="1",
            httponly=True,
            samesite="lax",
            max_age=3600,
            path="/",
        )
        return r
    return HTMLResponse(_login_page("Invalid credentials"), status_code=401)


@app.get("/dashboard", response_model=None)
def dashboard(request: Request):
    if request.cookies.get("e2e_auth") != "1":
        return RedirectResponse(url="/login", status_code=302)
    body = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Dashboard</title></head>
<body>
<h1>Dashboard</h1>
<p>You are signed in. Session cookie is set.</p>
</body></html>"""
    return HTMLResponse(body)
