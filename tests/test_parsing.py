"""Tests for reading JSON out of a model response.

The interesting cases here are not invented. Two of them are verbatim
responses captured from a live extraction run against a real datasheet,
where a caller doing plain ``json.loads`` failed roughly two runs in three.
"""
import json

import pytest

from agentflow import JSONResponseError, parse_json_response


# Captured verbatim from a live run. The model produced a malformed array,
# noticed, said so in prose, and then produced the correct one. The right
# answer is sitting in the response; json.loads cannot reach it.
SELF_CORRECTING_RESPONSE = '''["Figure 13-1 shows a typical application circuit for the device including the recommended decoupling network and reset circuit described in the preceding sections.","page":8]

Wait, must output JSON array only.

[{"quote":"Figure 13-1 shows a typical application circuit for the device including the recommended decoupling network and reset circuit described in the preceding sections.","page":8}]'''

# Also captured verbatim, from the same test on a different run: the
# opening brace of the first object is simply missing. There is no valid
# JSON anywhere in this one, and inventing the brace back is not this
# module's job.
UNRECOVERABLE_RESPONSE = (
    '["quote":"13. Typical Application Circuit","page":8},'
    '{"quote":"Figure 13-1 shows a typical application circuit for the device\\n'
    'including the recommended decoupling network and reset circuit\\n'
    'described in the preceding sections.","page":8}]'
)


class TestTheCommonCase:
    def test_a_plain_array(self):
        assert parse_json_response('[{"a": 1}]') == [{"a": 1}]

    def test_a_plain_object(self):
        assert parse_json_response('{"a": 1}') == {"a": 1}

    def test_surrounding_whitespace(self):
        assert parse_json_response('\n\n  [1, 2]  \n') == [1, 2]

    def test_a_scalar_when_nothing_is_expected_of_it(self):
        assert parse_json_response('42') == 42
        assert parse_json_response('null') is None


class TestTheShapesModelsActuallyProduce:
    def test_a_markdown_fence(self):
        assert parse_json_response('```json\n[{"a": 1}]\n```') == [{"a": 1}]

    def test_a_fence_with_no_language(self):
        assert parse_json_response('```\n[1]\n```') == [1]

    def test_preamble_prose(self):
        response = 'Here is the JSON array you asked for:\n\n[{"page": 3}]'
        assert parse_json_response(response) == [{"page": 3}]

    def test_trailing_prose(self):
        response = '[{"page": 3}]\n\nLet me know if you need anything else.'
        assert parse_json_response(response) == [{"page": 3}]

    def test_a_real_self_correcting_response(self):
        """The captured failure this module was written for."""
        with pytest.raises(json.JSONDecodeError):
            json.loads(SELF_CORRECTING_RESPONSE)

        value = parse_json_response(SELF_CORRECTING_RESPONSE, expect=list)

        assert len(value) == 1
        assert value[0]["page"] == 8
        assert value[0]["quote"].startswith("Figure 13-1 shows")

    def test_the_correction_wins_over_the_attempt_it_corrects(self):
        """Ordering is the whole point: a model writes forwards, so a
        correction always follows the thing it corrects."""
        response = '[{"n": 1}]\n\nSorry, that was wrong.\n\n[{"n": 2}]'
        assert parse_json_response(response) == [{"n": 2}]


class TestBracketCountingUnderstandsStrings:
    def test_a_brace_inside_a_quoted_string(self):
        response = 'Note:\n[{"quote": "set the {BOD} fuse", "page": 4}]'
        assert parse_json_response(response) == [{"quote": "set the {BOD} fuse", "page": 4}]

    def test_a_bracket_inside_a_quoted_string(self):
        assert parse_json_response('[{"q": "pins [1:0]"}]') == [{"q": "pins [1:0]"}]

    def test_an_escaped_quote_inside_a_string(self):
        assert parse_json_response(r'[{"q": "he said \"go\" then }"}]') == [{"q": 'he said "go" then }'}]

    def test_a_backslash_before_the_closing_quote(self):
        assert parse_json_response(r'[{"path": "C:\\"}]') == [{"path": "C:\\"}]


class TestExpect:
    def test_a_stray_object_does_not_stand_in_for_the_array(self):
        response = 'I will use this schema: {"quote": "string", "page": 0}\n\n[{"quote": "x", "page": 1}]'
        assert parse_json_response(response, expect=list) == [{"quote": "x", "page": 1}]

    def test_the_wrong_type_alone_is_an_error_not_a_silent_pass(self):
        with pytest.raises(JSONResponseError):
            parse_json_response('{"a": 1}', expect=list)

    def test_a_tuple_of_types(self):
        assert parse_json_response('{"a": 1}', expect=(list, dict)) == {"a": 1}

    def test_an_empty_array_is_a_real_answer_not_a_failure(self):
        """A category with nothing in it is a valid extraction result."""
        assert parse_json_response('[]', expect=list) == []


class TestFailure:
    def test_a_response_with_no_valid_json_raises(self):
        with pytest.raises(JSONResponseError):
            parse_json_response(UNRECOVERABLE_RESPONSE, expect=list)

    def test_nothing_is_repaired_or_guessed(self):
        """A missing brace stays a failure. Patching it up would produce a
        plausible object with no basis, which for extracted citations means
        a quote silently attached to the wrong page."""
        with pytest.raises(JSONResponseError):
            parse_json_response('[{"a": 1]', expect=list)

    def test_prose_with_no_json_at_all_raises(self):
        with pytest.raises(JSONResponseError):
            parse_json_response("I could not find anything relevant in this document.")

    def test_an_empty_response_raises(self):
        with pytest.raises(JSONResponseError):
            parse_json_response("   ")

    def test_the_error_carries_the_response_so_it_can_be_logged(self):
        """json.JSONDecodeError alone says "Expecting ',' delimiter: line 1
        column 9" and nothing about what came back. These failures are
        intermittent; there is often no second chance to look."""
        with pytest.raises(JSONResponseError) as excinfo:
            parse_json_response(UNRECOVERABLE_RESPONSE, expect=list)

        assert excinfo.value.response_text == UNRECOVERABLE_RESPONSE
        assert "13. Typical Application Circuit" in str(excinfo.value)

    def test_a_very_long_response_is_excerpted_in_the_message(self):
        response = "x" * 5000
        with pytest.raises(JSONResponseError) as excinfo:
            parse_json_response(response)

        assert len(str(excinfo.value)) < 700
        assert excinfo.value.response_text == response

    def test_a_truncated_array_fails_rather_than_returning_what_survived(self):
        """The dangerous one. There is a complete, valid object inside this
        truncated array, and returning it would hand the caller a plausible
        single-item result with no sign that the rest was lost."""
        with pytest.raises(JSONResponseError):
            parse_json_response('[{"a": 1}, {"b": ')

    def test_a_truncated_array_fails_even_when_a_type_is_expected(self):
        with pytest.raises(JSONResponseError):
            parse_json_response('[{"a": 1}, {"b": ', expect=list)
