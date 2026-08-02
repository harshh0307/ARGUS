from app.detection.models import ADDITIVE, BREAKING, Change
from app.scan.impact import assess_impact, match_path
from app.scan.models import Usage


def usage(method="get", path="/repos/{owner}/{repo}", line=5, file="app.py"):
    return Usage(file=file, line=line, method=method, path=path)


def breaking(kind="endpoint_removed", method="get", path="/repos/{owner}/{repo}"):
    return Change(kind, BREAKING, path, method, "x")


def test_impact_on_matching_change():
    impacts = assess_impact([usage()], [breaking()])
    assert len(impacts) == 1
    assert impacts[0].usage.line == 5


def test_no_impact_when_endpoint_unchanged():
    assert assess_impact([usage()], [breaking(path="/orgs/{org}/other")]) == []


def test_no_impact_on_method_mismatch():
    assert assess_impact([usage(method="post")], [breaking()]) == []


def test_additive_changes_do_not_affect_impact():
    additive = Change("endpoint_added", ADDITIVE, "/repos/{owner}/{repo}", "get", "x")
    assert assess_impact([usage()], [additive]) == []


def test_concrete_path_matches_template():
    assert assess_impact([usage(path="/repos/me/proj")], [breaking()])


def test_match_path_basic():
    assert match_path("/repos/me/proj", "/repos/{owner}/{repo}")
    assert not match_path("/repos/me", "/repos/{owner}/{repo}")
    assert not match_path("/orgs/{org}/x", "/repos/{owner}/{repo}")
