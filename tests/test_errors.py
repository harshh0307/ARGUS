
from app.fix.errors import (
    FixError,
    FixErrorType,
    classify_error,
    duplicate_patch_error,
    hallucination_error,
    llm_crash_error,
    no_progress_error,
    patch_validation_error,
    rate_limit_error,
    semantic_guard_error,
    syntax_error,
    timeout_error,
    token_budget_error,
)


class TestFixError:
    def test_str(self):
        e = FixError(FixErrorType.RATE_LIMIT, "too many requests")
        assert "rate_limit" in str(e)
        assert "too many requests" in str(e)

    def test_str_retryable(self):
        e = FixError(FixErrorType.RATE_LIMIT, "msg", retryable=True)
        assert "retryable" in str(e)

    def test_str_terminal(self):
        e = FixError(FixErrorType.DUPLICATE_PATCH, "msg", retryable=False)
        assert "terminal" in str(e)

    def test_repr(self):
        e = FixError(FixErrorType.TIMEOUT, "msg", retryable=True, attempt=2)
        assert "FixError" in repr(e)
        assert "timeout" in repr(e)

    def test_eq(self):
        e1 = FixError(FixErrorType.RATE_LIMIT, "msg")
        e2 = FixError(FixErrorType.RATE_LIMIT, "msg")
        assert e1 == e2

    def test_eq_diff_type(self):
        e1 = FixError(FixErrorType.RATE_LIMIT, "msg")
        e2 = FixError(FixErrorType.TIMEOUT, "msg")
        assert e1 != e2

    def test_eq_diff_msg(self):
        e1 = FixError(FixErrorType.RATE_LIMIT, "msg1")
        e2 = FixError(FixErrorType.RATE_LIMIT, "msg2")
        assert e1 != e2

    def test_eq_not_fix_error(self):
        e = FixError(FixErrorType.RATE_LIMIT, "msg")
        assert e != "msg"

    def test_hash(self):
        e1 = FixError(FixErrorType.RATE_LIMIT, "msg")
        e2 = FixError(FixErrorType.RATE_LIMIT, "msg")
        assert hash(e1) == hash(e2)
        assert len({e1, e2}) == 1

    def test_hash_diff(self):
        e1 = FixError(FixErrorType.RATE_LIMIT, "msg")
        e2 = FixError(FixErrorType.TIMEOUT, "msg")
        assert len({e1, e2}) == 2


class TestConstructors:
    def test_rate_limit(self):
        e = rate_limit_error("msg", attempt=1)
        assert e.type == FixErrorType.RATE_LIMIT
        assert e.retryable is True
        assert e.attempt == 1

    def test_timeout(self):
        e = timeout_error("msg")
        assert e.type == FixErrorType.TIMEOUT
        assert e.retryable is True

    def test_hallucination(self):
        e = hallucination_error("msg")
        assert e.type == FixErrorType.HALLUCINATION
        assert e.retryable is True

    def test_syntax(self):
        e = syntax_error("msg")
        assert e.type == FixErrorType.SYNTAX_ERROR
        assert e.retryable is True

    def test_semantic_guard(self):
        e = semantic_guard_error("msg")
        assert e.type == FixErrorType.SEMANTIC_GUARD
        assert e.retryable is True

    def test_duplicate_patch(self):
        e = duplicate_patch_error("msg")
        assert e.type == FixErrorType.DUPLICATE_PATCH
        assert e.retryable is False

    def test_no_progress(self):
        e = no_progress_error("msg")
        assert e.type == FixErrorType.NO_PROGRESS
        assert e.retryable is False

    def test_token_budget(self):
        e = token_budget_error("msg")
        assert e.type == FixErrorType.TOKEN_BUDGET
        assert e.retryable is False

    def test_llm_crash(self):
        e = llm_crash_error("msg")
        assert e.type == FixErrorType.LLM_CRASH
        assert e.retryable is True

    def test_patch_validation(self):
        e = patch_validation_error("msg")
        assert e.type == FixErrorType.PATCH_VALIDATION
        assert e.retryable is True


class TestClassifyError:
    def test_rate_limit_429(self):
        e = classify_error(Exception("status code 429"))
        assert e.type == FixErrorType.RATE_LIMIT

    def test_rate_limit_resource_exhausted(self):
        e = classify_error(Exception("resource_exhausted"))
        assert e.type == FixErrorType.RATE_LIMIT

    def test_rate_limit_message(self):
        e = classify_error(Exception("rate_limit exceeded"))
        assert e.type == FixErrorType.RATE_LIMIT

    def test_timeout(self):
        e = classify_error(Exception("connection timeout"))
        assert e.type == FixErrorType.TIMEOUT

    def test_timed_out(self):
        e = classify_error(Exception("request timed out"))
        assert e.type == FixErrorType.TIMEOUT

    def test_token_limit_context_length(self):
        e = classify_error(Exception("context_length_exceeded"))
        assert e.type == FixErrorType.TOKEN_BUDGET

    def test_token_limit_token_exceed(self):
        e = classify_error(Exception("token limit exceed"))
        assert e.type == FixErrorType.TOKEN_BUDGET

    def test_connection_502(self):
        e = classify_error(Exception("502 bad gateway"))
        assert e.type == FixErrorType.LLM_CRASH

    def test_connection_503(self):
        e = classify_error(Exception("503 service unavailable"))
        assert e.type == FixErrorType.LLM_CRASH

    def test_connection_504(self):
        e = classify_error(Exception("504 gateway timeout"))
        assert e.type == FixErrorType.LLM_CRASH

    def test_connection_error(self):
        e = classify_error(Exception("connection reset"))
        assert e.type == FixErrorType.LLM_CRASH

    def test_unknown(self):
        e = classify_error(Exception("something weird happened"))
        assert e.type == FixErrorType.UNKNOWN

    def test_attempt_preserved(self):
        e = classify_error(Exception("timeout"), attempt=3)
        assert e.attempt == 3

    def test_long_message_truncated(self):
        e = classify_error(Exception("x" * 1000))
        assert len(e.message) <= 500

    def test_empty_message(self):
        e = classify_error(Exception(""))
        assert e.type == FixErrorType.UNKNOWN

    def test_combined_patterns(self):
        e = classify_error(Exception("429 rate limit timeout"))
        assert e.type == FixErrorType.RATE_LIMIT
