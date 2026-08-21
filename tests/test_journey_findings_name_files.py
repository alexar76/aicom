"""A runtime finding that names no file sends the round to guess, and the guess was measured.

    находка: demo_login_failed:/login  ->  file='code/prod-bdb1634806de'      (каталог, не файл)
    09:51   Applied 2 edit(s): test_rule_engine.py, test_advisory_api.py      (дефект в auth.py)

The route table (`route_handler_file`) has known `/login -> routers/auth.py` for an hour; this wires it
into the finding the round actually reads. With a file the finding enters the repair scope, the file is
attached to the batch, and the edit protocol has something to anchor on.
"""

from __future__ import annotations

from pathlib import Path

from agents.qa import QAAgent


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


AUTH = (
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
    '@router.post("/login")\n'
    "def login():\n    return {}\n"
)
MAIN = (
    "from fastapi import FastAPI\n"
    "from app.routers import auth\n"
    "app = FastAPI()\n"
    "app.include_router(auth.router)\n"
)


def test_a_login_failure_names_the_auth_router(tmp_path):
    code = _tree(
        tmp_path / "code",
        {"backend/app/routers/auth.py": AUTH, "backend/app/main.py": MAIN},
    )
    got = QAAgent._journey_issue_file(
        code, "demo_login_failed:/login:statuses=[422, 500, 422] (seeded demo user …)"
    )
    assert got == "backend/app/routers/auth.py"


def test_a_traceback_path_beats_endpoint_inference(tmp_path):
    """Boot lines carry the exact file; the endpoint would only approximate it."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/auth.py": AUTH,
            "backend/app/main.py": MAIN,
            "backend/app/services/atlas_client.py": "x = 1\n",
        },
    )
    got = QAAgent._journey_issue_file(
        code,
        "import_error: NameError: name 'invoke_capability' is not defined  (app/services/atlas_client.py:8)",
    )
    assert got == "backend/app/services/atlas_client.py"


def test_a_path_parameter_endpoint_resolves(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/analytics.py": (
                "from fastapi import APIRouter\n"
                "router = APIRouter()\n"
                '@router.get("/api/dashboards/{dashboard_id}/data")\n'
                "def data(dashboard_id: int):\n    return {}\n"
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\n"
                "from app.routers import analytics\n"
                "app = FastAPI()\n"
                "app.include_router(analytics.router)\n"
            ),
        },
    )
    got = QAAgent._journey_issue_file(code, "demo_journey_5xx:/api/dashboards/7/data")
    assert got == "backend/app/routers/analytics.py"


def test_an_unresolvable_line_degrades_to_none(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": MAIN})
    assert QAAgent._journey_issue_file(code, "uvicorn_failed_to_listen: timeout") is None


def test_a11y_missing_h1_names_the_react_page_not_the_vite_shell(tmp_path):
    """PublicWidget.tsx already rendered <h1>Sentinel</h1>. The finding was filed
    against index.html, so the round edited the shell and the heading file never
    entered the six-file scope."""
    code = _tree(
        tmp_path / "code",
        {
            "index.html": "<div id='root'></div>\n",
            "frontend/src/pages/PublicWidget.tsx": "export default function W(){return <h1>Sentinel</h1>}\n",
        },
    )
    got = QAAgent._journey_issue_file(code, "a11y_missing_h1")
    assert got == "frontend/src/pages/PublicWidget.tsx"


def test_spec_alignment_naming_operator_points_at_the_operator_page(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "index.html": "<div id='root'></div>\n",
            "frontend/src/pages/PublicWidget.tsx": "export default function W(){return <h1>Sentinel</h1>}\n",
            "frontend/src/pages/OperatorDashboard.tsx": "export default function O(){return <h1>Ops</h1>}\n",
            "frontend/src/App.tsx": "<Route path='/operator' element={<OperatorDashboard />} />\n",
        },
    )
    got = QAAgent._journey_issue_file(
        code, "spec_alignment_llm_failed: no operator console at /operator"
    )
    assert got == "frontend/src/pages/OperatorDashboard.tsx"


def test_a_pageerror_names_the_react_page_not_the_vite_shell(tmp_path):
    """Playwright's pageerror was filed against index.html, so the throwing widget
    never entered the six-file scope and the round edited the shell."""
    code = _tree(
        tmp_path / "code",
        {
            "index.html": "<div id='root'></div>\n",
            "frontend/src/pages/PublicWidget.tsx": "export default function W(){return <h1>Sentinel</h1>}\n",
        },
    )
    got = QAAgent._journey_issue_file(code, "pageerror: Error")
    assert got == "frontend/src/pages/PublicWidget.tsx"


def test_contrast_names_the_stylesheet_not_the_vite_shell(tmp_path):
    code = _tree(
        tmp_path / "code",
        {
            "index.html": "<div id='root'></div>\n",
            "frontend/src/styles/index.css": "button { color: #ccc; background: #ddd; }\n",
            "frontend/src/pages/PublicWidget.tsx": "export default function W(){return <button>Go</button>}\n",
        },
    )
    got = QAAgent._demo_issue_file(code, {"code": "ux_low_contrast_cta", "detail": "Text/fill contrast"})
    assert got == "frontend/src/styles/index.css"

def test_the_finding_carries_the_file_and_says_so():
    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    region = qa[qa.index('for line in journey.get("issues") or []:') :][:2600]
    assert "_journey_issue_file(" in region
    assert '"file": _jf or f"code/{product_id}"' in region
    assert "The handler for this endpoint lives in" in region, (
        "the description does not tell the round where to act"
    )


def test_a_tokenless_200_is_its_own_finding():
    """Two defects hide behind "no token", and conflating them misdirects the round.

    Measured: login answered 200 with body {"message":"ok"} — no token, no session — and the issue
    still read `statuses=[200, 422, 422]`, pointing at the status, which was fine. The round needed
    the response body named, and told explicitly not to change the status code.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "product_demo_journey.py"
    ).read_text(encoding="utf-8")
    region = src[src.index("if not token:") :][:2600]
    assert "demo_login_no_token:" in region
    assert "carries no token" in region
    assert "do not change the status code" in region, (
        "without this the round 'fixes' the working status and the oscillation starts again"
    )
    # The genuine-failure branch must survive for real 4xx/5xx logins.
    assert "demo_login_failed:" in region


def test_journey_files_enter_the_repair_scope():
    """A scope that excludes the file a runtime defect lives in makes it unfixable by construction.

    Watched twice in one hour: the round FIXED the tokenless login in auth.py, the scope named only
    the static finding's file (FeedbackStates.tsx), and the out-of-scope guard reverted the completed
    fix — measured as free, because a missing token is invisible to the static score.
    """
    from pathlib import Path

    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    region = qa[qa.index("blocking_files: list[str] = []") : qa.index("repair_scope = blocking_files[:6]")]
    assert "_journey_issue_file(" in region, "runtime findings never reach the scope"
    assert 'journey.get("issues")' in region


def test_frontier_findings_do_not_vote_on_the_revert():
    """`auth_rejected` can only exist once login WORKS — voting it punishes the breakthrough.

    Measured: the round that finally made login return a token was reverted 14 -> 32, because the
    journey went deeper for the first time and found six 401s that were unreachable a round
    earlier. Third time the same fix was thrown away, each time by a different guard. The finding
    still reaches the developer and still holds the journey gate red; it just cannot un-accept the
    round that made it observable.
    """
    from pathlib import Path

    from core.round_regression_guard import qa_defect_score

    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    region = qa[qa.index('for line in journey.get("issues") or []:') :][:2600]
    assert '"auth_rejected" in str(line)' in region
    assert '"scored_by_guard": False' in region

    frontier = {
        "severity": "high",
        "title": "Demo journey: demo_journey_auth_rejected:/api/analytics/dashboards:401",
        "scored_by_guard": False,
    }
    real = {"severity": "high", "title": "Demo journey: demo_login_no_token:/api/auth/login: no token"}
    assert qa_defect_score({"bugs_found": [frontier]}) == 0
    assert qa_defect_score({"bugs_found": [frontier, real]}) == 3


def test_the_response_model_file_is_half_the_fix_and_joins_the_scope():
    """FastAPI silently strips every response field the model does not declare.

    Three rounds edited auth.py against the tokenless-login finding and the observable body never
    changed, because the route declares response_model=LoginResponse and LoginResponse declares only
    `message: str` — in another file, which was not in the scope, so an edit there would have been
    reverted as sprawl. A fix that requires two files needs both of them editable, and the finding now
    says the model half out loud.
    """
    from pathlib import Path

    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    block = qa[qa.index("for _line in _runtime_lines:") :][:4200]
    assert 'response_model\\s*=\\s*(\\w+)' in block
    assert "strips every response field the model does not declare" in block

    journey = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "product_demo_journey.py"
    ).read_text(encoding="utf-8")
    assert "FastAPI silently" in journey
    assert "the fix is TWO" in journey
    assert "Editing only the handler changes nothing" in journey


def test_the_route_table_applies_include_prefixes(tmp_path):
    """Served paths carry the include_router prefix; declared paths do not.

    After the product correctly moved /api out of its decorators and into
    include_router(..., prefix=settings.api_prefix), the table held /auth/login while every runtime
    finding said /api/auth/login — route_handler_file answered None, journey findings stopped naming
    files, and the scope silently lost the login handler it had named for hours. The same
    include-prefix blindness as the shadow detector's, one module over.
    """
    from web.backend.services.api_contract_check import route_handler_file

    code = tmp_path / "code"
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "config.py").write_text(
        'class Settings:\n    api_prefix: str = "/api"\n', encoding="utf-8"
    )
    (code / "backend" / "app" / "main.py").write_text(
        "app.include_router(auth.router, prefix=settings.api_prefix)\n", encoding="utf-8"
    )
    (code / "backend" / "app" / "routers" / "auth.py").write_text(
        'router = APIRouter()\n\n\n@router.post("/auth/login")\ndef login():\n    return {}\n',
        encoding="utf-8",
    )
    assert route_handler_file(code, "/api/auth/login") == "backend/app/routers/auth.py"
    # the bare declared path still resolves, in case a router is mounted at the root too
    assert route_handler_file(code, "/auth/login") == "backend/app/routers/auth.py"


def test_auth_rejected_says_how_this_client_authenticates():
    """A 401 with no transport named sends the rounds guessing between cookie and header.

    Measured: six rounds flip-flopped analytics.py and operator.py between cookie-only auth and
    Bearer-header auth, each undoing the previous — my own hand-test hit 200 at 15:55 and QA
    measured 401 on the very next verdict, because the round in between had swapped the dependency
    back. The journey sends 'Authorization: Bearer' and holds no cookies; the finding has to say so,
    and to demand ONE shared dependency rather than another alternation.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "web" / "backend" / "services" / "product_demo_journey.py"
    ).read_text(encoding="utf-8")
    block = src[src.index("demo_journey_auth_rejected:") - 200 :][:1600]
    assert "Authorization: Bearer" in block
    assert "does not keep cookies" in block
    assert "Do not remove cookie support" in block
    assert "ONE shared dependency" in block


def test_auth_rejected_names_the_shared_dependency_not_the_router(tmp_path):
    """The endpoint that answered 401 is not the file to edit.

    Measured: six rounds flip-flopped analytics.py and operator.py between cookie-only and
    Bearer-only because `_journey_issue_file` mapped `/api/analytics/dashboards` to the
    router. get_current_user in deps.py was never in the scope.
    """
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/deps.py": (
                "from fastapi import Request\n"
                "def get_current_user(request: Request):\n"
                "    return request.cookies.get('access_token')\n"
            ),
            "backend/app/routers/analytics.py": (
                "from fastapi import APIRouter, Depends\n"
                "from app.deps import get_current_user\n"
                "router = APIRouter()\n"
                '@router.get("/api/analytics/dashboards")\n'
                "def dashboards(user=Depends(get_current_user)):\n"
                "    return []\n"
            ),
            "backend/app/main.py": (
                "from fastapi import FastAPI\n"
                "from app.routers import analytics\n"
                "app = FastAPI()\n"
                "app.include_router(analytics.router)\n"
            ),
        },
    )
    got = QAAgent._journey_issue_file(
        code,
        "demo_journey_auth_rejected:/api/analytics/dashboards:401: the endpoint refused "
        "the token. This client authenticates ONLY via Authorization: Bearer.",
    )
    assert got == "backend/app/deps.py", got
