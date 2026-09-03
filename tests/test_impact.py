from app.detection.models import ADDITIVE, BREAKING, Change, ChangeKind
from app.scan.impact import assess_impact, match_path
from app.scan.models import AuthUsage, BodyUsage, HeaderUsage, ResponseUsage, Usage


def usage(method="get", path="/repos/{owner}/{repo}", line=5, file="app.py"):
    return Usage(file=file, line=line, method=method, path=path)


def header(name="Authorization", line=5, file="app.py", context="bearer"):
    return HeaderUsage(file=file, line=line, header_name=name, header_value=None, context=context)


def body(line=5, file="app.py", method="post", path="/repos/{owner}/{repo}", fields=("name",)):
    return BodyUsage(file=file, line=line, method=method, path=path, fields_used=fields, content_type="application/json")


def auth(line=5, file="app.py", auth_type="bearer"):
    return AuthUsage(file=file, line=line, auth_type=auth_type, header_name="Authorization")


def response(line=5, file="app.py", method="get", path="/repos/{owner}/{repo}", status_codes=("200",), fields=("name",)):
    return ResponseUsage(file=file, line=line, method=method, path=path, status_codes_used=status_codes, fields_used=fields)


def breaking(kind="endpoint_removed", method="get", path="/repos/{owner}/{repo}"):
    return Change(kind, BREAKING, path, method, "x")


def test_impact_on_matching_change():
    impacts = assess_impact([usage()], [], [], [], [], [breaking()])
    assert len(impacts) == 1
    assert impacts[0].usage.line == 5


def test_no_impact_when_endpoint_unchanged():
    assert assess_impact([usage()], [], [], [], [], [breaking(path="/orgs/{org}/other")]) == []


def test_no_impact_on_method_mismatch():
    assert assess_impact([usage(method="post")], [], [], [], [], [breaking()]) == []


def test_additive_changes_do_not_affect_impact():
    additive = Change("endpoint_added", ADDITIVE, "/repos/{owner}/{repo}", "get", "x")
    assert assess_impact([usage()], [], [], [], [], [additive]) == []


def test_concrete_path_matches_template():
    assert assess_impact([usage(path="/repos/me/proj")], [], [], [], [], [breaking()])


def test_header_usage_affected_by_security_change():
    impacts = assess_impact([], [header()], [], [], [], [breaking(ChangeKind.OPERATION_SECURITY_CHANGED)])
    assert len(impacts) == 1
    assert impacts[0].usage.header_name == "Authorization"


def test_body_usage_affected_by_body_removal():
    impacts = assess_impact([], [], [body()], [], [], [breaking(ChangeKind.REQUEST_BODY_REMOVED)])
    assert len(impacts) == 1
    assert impacts[0].usage.fields_used == ("name",)


def test_auth_usage_affected_by_security_change():
    impacts = assess_impact([], [], [], [auth()], [], [breaking(ChangeKind.OPERATION_SECURITY_CHANGED)])
    assert len(impacts) == 1
    assert impacts[0].usage.auth_type == "bearer"


def test_response_usage_affected_by_code_removal():
    change = Change(ChangeKind.RESPONSE_CODE_REMOVED, BREAKING, "/repos/{owner}/{repo}", "get", "x", old_value="200")
    impacts = assess_impact([], [], [], [], [response()], [change])
    assert len(impacts) == 1
    assert impacts[0].usage.status_codes_used == ("200",)


def test_match_path_basic():
    assert match_path("/repos/me/proj", "/repos/{owner}/{repo}")
    assert not match_path("/repos/me", "/repos/{owner}/{repo}")
    assert not match_path("/orgs/{org}/x", "/repos/{owner}/{repo}")
