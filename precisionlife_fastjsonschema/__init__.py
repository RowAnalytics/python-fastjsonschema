#    ___
#    \./     DANGER: This project implements some code generation
# .--.O.--.          techniques involving string concatenation.
#  \/   \/           If you look at it, you might die.
#

r"""
Installation
************

.. code-block:: bash

    pip install fastjsonschema

Support only for Python 3.3 and higher.

About
*****

``fastjsonschema`` implements validation of JSON documents by JSON schema.
The library implements JSON schema drafts 04, 06 and 07. The main purpose is
to have a really fast implementation. See some numbers:

 * Probably most popular ``jsonschema`` can take up to 5 seconds for valid inputs
   and 1.2 seconds for invalid inputs.
 * Second most popular ``json-spec`` is even worse with up to 7.2 and 1.7 seconds.
 * Last ``validictory``, now deprecated, is much better with 370 or 23 milliseconds,
   but it does not follow all standards and it can be still slow for some purposes.

With this library you can gain big improvements as ``fastjsonschema`` takes
only about 25 milliseconds for valid inputs and 2 milliseconds for invalid ones.
Pretty amazing, right? :-)

Technically it works by generating the most stupid code on the fly which is fast but
is hard to write by hand. The best efficiency is achieved when compiled once and used
many times, of course. It works similarly like regular expressions. But you can also
generate the code to the file which is even slightly faster.

You can do the performance on your computer or server with an included script:

.. code-block:: bash

    $ make performance
    fast_compiled        valid      ==>  0.0464646
    fast_compiled        invalid    ==>  0.0030227
    fast_file            valid      ==>  0.0461219
    fast_file            invalid    ==>  0.0030608
    fast_not_compiled    valid      ==> 11.4627202
    fast_not_compiled    invalid    ==>  2.5726230
    jsonschema           valid      ==>  7.5844927
    jsonschema           invalid    ==>  1.9204665
    jsonschema_compiled  valid      ==>  0.6938364
    jsonschema_compiled  invalid    ==>  0.0359244
    jsonspec             valid      ==>  9.0715843
    jsonspec             invalid    ==>  2.1650488
    validictory          valid      ==>  0.4874793
    validictory          invalid    ==>  0.0232244

This library follows and implements `JSON schema draft-04, draft-06, and draft-07
<http://json-schema.org>`_. Sometimes it's not perfectly clear so I recommend also
check out this `understanding JSON schema <https://spacetelescope.github.io/understanding-json-schema>`_.

Note that there are some differences compared to JSON schema standard:

 * Regular expressions are full Python ones, not only what JSON schema allows. It's easier
   to allow everything and also it's faster to compile without limits. So keep in mind that when
   you will use a more advanced regular expression, it may not work with other library or in
   other languages.
 * Because Python matches new line for a dollar in regular expressions (``a$`` matches ``a`` and ``a\\n``),
   instead of ``$`` is used ``\Z`` and all dollars in your regular expression are changed to ``\\Z``
   as well. When you want to use dollar as regular character, you have to escape it (``\$``).
 * JSON schema says you can use keyword ``default`` for providing default values. This implementation
   uses that and always returns transformed input data.

API
***
"""

from .draft04 import CodeGeneratorDraft04
from .draft06 import CodeGeneratorDraft06
from .draft07 import CodeGeneratorDraft07
from .exceptions import JsonSchemaException, JsonSchemaValidationException, JsonSchemaDefinitionException
from .ref_resolver import RefResolver
from .version import VERSION

__all__ = ('VERSION', 'JsonSchemaException', 'JsonSchemaValidationException', 'JsonSchemaDefinitionException', 'validate', 'compile', 'compile_to_code')


def validate(definition, data, handlers={}, formats={}):
    """
    Validation function for lazy programmers or for use cases, when you need
    to call validation only once, so you do not have to compile it first.
    Use it only when you do not care about performance (even thought it will
    be still faster than alternative implementations).

    .. code-block:: python

        import precisionlife_fastjsonschema as fastjsonschema

        fastjsonschema.validate({'type': 'string'}, 'hello')
        # same as: compile({'type': 'string'})('hello')

    Preferred is to use :any:`compile` function.
    """
    return compile(definition, handlers, formats)(data)


# pylint: disable=redefined-builtin,dangerous-default-value,exec-used
def compile(definition, handlers={}, formats={}, **resolver_kwargs):
    """
    Generates validation function for validating JSON schema passed in ``definition``.
    Example:

    .. code-block:: python

        import precisionlife_fastjsonschema as fastjsonschema

        validate = fastjsonschema.compile({'type': 'string'})
        validate('hello')

    This implementation support keyword ``default``:

    .. code-block:: python

        validate = fastjsonschema.compile({
            'type': 'object',
            'properties': {
                'a': {'type': 'number', 'default': 42},
            },
        })

        data = validate({})
        assert data == {'a': 42}

    Supported implementations are draft-04, draft-06 and draft-07. Which version
    should be used is determined by `$draft` in your ``definition``. When not
    specified, the latest implementation is used (draft-07).

    .. code-block:: python

        validate = fastjsonschema.compile({
            '$schema': 'http://json-schema.org/draft-04/schema',
            'type': 'number',
        })

    You can pass mapping from URI to function that should be used to retrieve
    remote schemes used in your ``definition`` in parameter ``handlers``.

    Also, you can pass mapping for custom formats. Key is the name of your
    formatter and value can be regular expression which will be compiled or
    callback returning `bool` (or you can raise your own exception).

    .. code-block:: python

        validate = fastjsonschema.compile(definition, formats={
            'foo': r'foo|bar',
            'bar': lambda value: value in ('foo', 'bar'),
        })

    Exception :any:`JsonSchemaDefinitionException` is raised when generating the
    code fails (bad definition).

    Exception :any:`JsonSchemaValidationException` is raised from generated function when
    validation fails (data do not follow the definition).
    """
    resolver, code_generator = _factory(definition, handlers, formats, **resolver_kwargs)
    global_state = code_generator.global_state
    # Do not pass local state so it can recursively call itself.
    exec(code_generator.func_code, global_state)
    return global_state[resolver.get_scope_name()]


# pylint: disable=dangerous-default-value
def compile_to_code(definition, handlers={}, formats={}, **resolver_kwargs):
    """
    Generates validation code for validating JSON schema passed in ``definition``.
    Example:

    .. code-block:: python

        import precisionlife_fastjsonschema as fastjsonschema

        code = fastjsonschema.compile_to_code({'type': 'string'})
        with open('your_file.py', 'w') as f:
            f.write(code)

        # You can execute the validation like this:
        spec = importlib.util.spec_from_file_location("temp_module_name", 'your_file.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate(obj_dict, ...) # Typically this will be validate() (for validating against the whole thing).

        # Validating maybe should be something like this to be robust in weird cases? Not sure... (would replicate what compile() does).
        resolver = RefResolver.from_schema(definition, handlers=handlers, **resolver_kwargs)
        getattr(module, resolver.get_scope_name())(obj_dict, ...)

    Exception :any:`JsonSchemaDefinitionException` is raised when generating the
    code fails (bad definition).
    """
    resolver, code_generator = _factory(definition, handlers, formats, **resolver_kwargs)
    return (
        'VERSION = "' + VERSION + '"\n' +
        code_generator.global_state_code + '\n' +
        code_generator.func_code + '\n\n\n' +
        'if __name__ == "__main__":' + '\n' +
        '    # Example code:' + '\n' +
        '    ' + resolver.get_scope_name() + '(obj_dict, special_fields_extractor=...)' + '\n'
    )


def _factory(definition, handlers, formats={}, **resolver_kwargs):
    resolver = RefResolver.from_schema(definition, handlers=handlers, **resolver_kwargs)
    code_generator = _get_code_generator_class(definition)(definition, resolver=resolver, formats=formats)
    return resolver, code_generator


def _get_code_generator_class(schema):
    # Schema in from draft-06 can be just the boolean value.
    if isinstance(schema, dict):
        schema_version = schema.get('$schema', '')
        if 'draft-04' in schema_version:
            return CodeGeneratorDraft04
        if 'draft-06' in schema_version:
            return CodeGeneratorDraft06
    return CodeGeneratorDraft07
