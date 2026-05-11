"""Admin panel human roles — stable ids for RBAC and Users UI."""

from web.backend.core.admin_roles import AdminRole, ROLE_DESCRIPTIONS, ROLE_RANK


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
