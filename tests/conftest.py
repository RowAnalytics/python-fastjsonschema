import os
import sys

current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(current_dir, os.pardir))


from pprint import pprint

import pytest

from fastjsonschema import JsonSchemaException, compile
from fastjsonschema.draft07 import CodeGeneratorDraft07


@pytest.fixture
def asserter():
    def f(definition, value, expected, formats={}, *, special_fields_extractor=None, ignore_exc_fields=None):
        # When test fails, it will show up code.
        code_generator = CodeGeneratorDraft07(definition, formats=formats)
        print(code_generator.func_code)
        pprint(code_generator.global_state)

        # By default old tests are written for draft-04.
        definition.setdefault('$schema', 'http://json-schema.org/draft-04/schema')

        validator = compile(definition, formats=formats)
        if isinstance(expected, JsonSchemaException):
            with pytest.raises(JsonSchemaException) as exc:
                validator(value, special_fields_extractor=special_fields_extractor)
            ignore_exc_fields = ignore_exc_fields or []
            if 'message' not in ignore_exc_fields:
                assert exc.value.message == expected.message
            if 'value' not in ignore_exc_fields:
                assert exc.value.value == (value if expected.value == '{data}' else expected.value)
            if 'name' not in ignore_exc_fields:
                assert exc.value.name == expected.name
            if 'definition' not in ignore_exc_fields:
                assert exc.value.definition == (definition if expected.definition == '{definition}' else expected.definition)
            if 'rule' not in ignore_exc_fields:
                assert exc.value.rule == expected.rule
        else:
            assert validator(value) == expected
    return f
