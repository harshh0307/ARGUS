"""Tests for new scan models: BodyUsage, AuthUsage, ResponseUsage."""

from app.fix.strategies import ChangeKind
from app.scan.models import DriftSignal
from app.scan.models import (
    AuthUsage,
    BodyUsage,
    Impact,
    ResponseUsage,
    Usage,
)


class TestBodyUsage:
    def test_construction(self):
        b = BodyUsage(
            file="app.py",
            line=10,
            method="post",
            path="/users",
            fields_used=("name", "email"),
            content_type="application/json",
        )
        assert b.file == "app.py"
        assert b.fields_used == ("name", "email")
        assert b.content_type == "application/json"

    def test_defaults(self):
        b = BodyUsage(file="app.py", line=10, method="post", path="/users")
        assert b.fields_used == ()
        assert b.content_type is None

    def test_str(self):
        b = BodyUsage(
            file="app.py",
            line=10,
            method="post",
            path="/users",
            fields_used=("name",),
        )
        s = str(b)
        assert "name" in s
        assert "POST" in s

    def test_frozen(self):
        b = BodyUsage(file="app.py", line=10, method="post", path="/users")
        try:
            b.line = 20  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass


class TestAuthUsage:
    def test_construction(self):
        a = AuthUsage(
            file="app.py",
            line=5,
            auth_type="bearer",
            header_name="Authorization",
        )
        assert a.auth_type == "bearer"
        assert a.header_name == "Authorization"

    def test_with_scopes(self):
        a = AuthUsage(
            file="app.py",
            line=5,
            auth_type="oauth2",
            scope_used=("read", "write"),
        )
        assert a.scope_used == ("read", "write")

    def test_str(self):
        a = AuthUsage(file="app.py", line=5, auth_type="api_key")
        assert "api_key" in str(a)


class TestResponseUsage:
    def test_construction(self):
        r = ResponseUsage(
            file="app.py",
            line=20,
            method="get",
            path="/users/{id}",
            status_codes_used=("200", "404"),
            fields_used=("name", "email"),
        )
        assert r.status_codes_used == ("200", "404")
        assert r.fields_used == ("name", "email")

    def test_defaults(self):
        r = ResponseUsage(file="app.py", line=20, method="get", path="/users")
        assert r.status_codes_used == ()
        assert r.fields_used == ()

    def test_str(self):
        r = ResponseUsage(
            file="app.py",
            line=20,
            method="get",
            path="/users",
            status_codes_used=("200",),
        )
        s = str(r)
        assert "200" in s


class TestImpact:
    def test_with_usage(self):
        u = Usage(file="app.py", line=10, method="get", path="/users")
        c = DriftSignal(
            kind=ChangeKind.ENDPOINT_REMOVED,
            severity="breaking",
            path="/users",
            method="get",
        )
        impact = Impact(usage=u, change=c)
        assert impact.usage == u
        assert impact.change == c

    def test_with_body_usage(self):
        b = BodyUsage(file="app.py", line=10, method="post", path="/users")
        c = DriftSignal(
            kind=ChangeKind.REQUEST_BODY_REMOVED,
            severity="breaking",
            path="/users",
            method="post",
        )
        impact = Impact(usage=b, change=c)
        assert impact.usage == b

    def test_with_auth_usage(self):
        a = AuthUsage(file="app.py", line=5, auth_type="bearer")
        c = DriftSignal(
            kind=ChangeKind.SECURITY_SCHEME_TYPE_CHANGED,
            severity="breaking",
            path="/",
            method="info",
        )
        impact = Impact(usage=a, change=c)
        assert impact.usage == a

    def test_str(self):
        u = Usage(file="app.py", line=10, method="get", path="/users")
        c = DriftSignal(
            kind=ChangeKind.ENDPOINT_REMOVED,
            severity="breaking",
            path="/users",
            method="get",
        )
        impact = Impact(usage=u, change=c)
        s = str(impact)
        assert "app.py" in s
        assert "breaking" in s
