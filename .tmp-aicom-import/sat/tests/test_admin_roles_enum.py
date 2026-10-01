"""Admin panel human roles — stable ids for RBAC and Users UI."""

from web.backend.core.admin_roles import AdminRole, ROLE_DESCRIPTIONS, ROLE_RANK, normalize_role


def test_admin_role_enum_values():
    assert [r.value for r in AdminRole] == ["viewer", "operator", "admin", "super_admin"]


def test_role_rank_increases_with_privilege():
    assert ROLE_RANK[AdminRole.VIEWER] < ROLE_RANK[AdminRole.OPERATOR]
    assert ROLE_RANK[AdminRole.OPERATOR] < ROLE_RANK[AdminRole.ADMIN]
    assert ROLE_RANK[AdminRole.ADMIN] < ROLE_RANK[AdminRole.SUPER_ADMIN]


def test_each_role_has_description():
    for r in AdminRole:
        assert r in ROLE_DESCRIPTIONS
        assert len(ROLE_DESCRIPTIONS[r].strip()) > 10


def test_normalize_role_missing_is_admin_not_super_admin():
    assert normalize_role(None) == AdminRole.ADMIN
    assert normalize_role("") == AdminRole.ADMIN


def test_normalize_role_invalid_fails_closed_to_viewer():
    assert normalize_role("super_admn") == AdminRole.VIEWER
    assert normalize_role("root") == AdminRole.VIEWER


def test_normalize_role_valid():
    assert normalize_role("super_admin") == AdminRole.SUPER_ADMIN
    assert normalize_role("viewer") == AdminRole.VIEWER
