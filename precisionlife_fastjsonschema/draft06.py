from .draft04 import CodeGeneratorDraft04, JSON_TYPE_TO_PYTHON_TYPE
from .exceptions import JsonSchemaDefinitionException
from .generator import enforce_list


class CodeGeneratorDraft06(CodeGeneratorDraft04):
    FORMAT_REGEXS = dict(CodeGeneratorDraft04.FORMAT_REGEXS, **{
        'json-pointer': r'^(/(([^/~])|(~[01]))*)*\Z',
        'uri-reference': r'^(\w+:(\/?\/?))?[^#\\\s]*(#[^\\\s]*)?\Z',
        'uri-template': (
            r'^(?:(?:[^\x00-\x20\"\'<>%\\^`{|}]|%[0-9a-f]{2})|'
            r'\{[+#./;?&=,!@|]?(?:[a-z0-9_]|%[0-9a-f]{2})+'
            r'(?::[1-9][0-9]{0,3}|\*)?(?:,(?:[a-z0-9_]|%[0-9a-f]{2})+'
            r'(?::[1-9][0-9]{0,3}|\*)?)*\})*\Z'
        ),
    })

    def __init__(self, definition, resolver=None, formats={}):
        super().__init__(definition, resolver, formats)
        self._json_keywords_to_function.update((
            ('exclusiveMinimum', self.generate_exclusive_minimum),
            ('exclusiveMaximum', self.generate_exclusive_maximum),
            ('propertyNames', self.generate_property_names),
            ('contains', self.generate_contains),
            ('const', self.generate_const),
        ))

    def _generate_func_code_block(self, definition):
        if isinstance(definition, bool):
            self.generate_boolean_schema()
        elif '$ref' in definition:
            # needed because ref overrides any sibling keywords
            self.generate_ref()
        else:
            self.run_generate_functions(definition)

    def generate_boolean_schema(self):
        """
        Means that schema can be specified by boolean.
        True means everything is valid, False everything is invalid.
        """
        if self._definition is False:
            self.exc('must not be there')

    def generate_type(self):
        """
        Validation of type. Can be one type or list of types.

        Since draft 06 a float without fractional part is an integer.

        .. code-block:: python

            {'type': 'string'}
            {'type': ['string', 'number']}
        """
        types = enforce_list(self._definition['type'])
        try:
            python_types = ', '.join(JSON_TYPE_TO_PYTHON_TYPE[t] for t in types)
        except KeyError as exc:
            raise JsonSchemaDefinitionException('Unknown type: {}'.format(exc))

        extra = ''

        if 'integer' in types:
            extra += ' and not (isinstance({variable}, float) and {variable}.is_integer())'.format(
                variable=self._variable,
            )

        if ('number' in types or 'integer' in types) and 'boolean' not in types:
            extra += ' or isinstance({variable}, bool)'.format(variable=self._variable)
        if ('array' in types) and ('string' not in types):
            extra = ' or isinstance({variable}, str)'.format(variable=self._variable)

        with self.l('if not isinstance({variable}, ({})){}:', python_types, extra):
            self.exc('must be {}, but is a: " + type({variable}).__name__ + "', ' or '.join(types), rule='type')

    def generate_exclusive_minimum(self):
        with self.l('if isinstance({variable}, (int, float)):'):
            if not isinstance(self._definition['exclusiveMinimum'], (int, float)):
                raise JsonSchemaDefinitionException('exclusiveMinimum must be an integer or a float')
            with self.l('if {variable} <= {exclusiveMinimum}:'):
                self.exc('must be bigger than {exclusiveMinimum}', rule='exclusiveMinimum')

    def generate_exclusive_maximum(self):
        with self.l('if isinstance({variable}, (int, float)):'):
            if not isinstance(self._definition['exclusiveMaximum'], (int, float)):
                raise JsonSchemaDefinitionException('exclusiveMaximum must be an integer or a float')
            with self.l('if {variable} >= {exclusiveMaximum}:'):
                self.exc('must be smaller than {exclusiveMaximum}', rule='exclusiveMaximum')

    def generate_property_names(self):
        """
        Means that keys of object must to follow this definition.

        .. code-block:: python

            {
                'propertyNames': {
                    'maxLength': 3,
                },
            }

        Valid keys of object for this definition are foo, bar, ... but not foobar for example.
        """
        property_names_definition = self._definition.get('propertyNames', {})
        if property_names_definition is True:
            pass
        elif property_names_definition is False:
            self.create_variable_keys()
            with self.l('if {variable}_keys:'):
                self.exc('must not be there', rule='propertyNames')
        else:
            self.create_variable_is_dict()
            with self.l('if {variable}_is_dict:'):
                self.create_variable_with_length()
                with self.l('if {variable}_len != 0:'):
                    self.l('{variable}_property_names = True')
                    with self.l('for {variable}_key in {variable}:'):
                        with self.l('try:'):
                            self.generate_func_code_block(
                                property_names_definition,
                                '{}_key'.format(self._variable),
                                self._variable_path,
                                clear_variables=True,
                            )
                        with self.l('except JsonSchemaValidationException:'):
                            self.l('{variable}_property_names = False')
                    with self.l('if not {variable}_property_names:'):
                        self.exc('must be named by propertyName definition', rule='propertyNames')

    def generate_contains(self):
        """
        Means that array must contain at least one defined item.

        .. code-block:: python

            {
                'contains': {
                    'type': 'number',
                },
            }

        Valid array is any with at least one number.
        """
        self.create_variable_is_list()
        with self.l('if {variable}_is_list:'):
            contains_definition = self._definition['contains']

            if contains_definition is False:
                self.exc('is always invalid', rule='contains')
            elif contains_definition is True:
                with self.l('if not {variable}:'):
                    self.exc('must not be empty', rule='contains')
            else:
                self.l('{variable}_contains = False')
                with self.l('for {variable}_key in {variable}:'):
                    with self.l('try:'):
                        self.generate_func_code_block(
                            contains_definition,
                            '{}_key'.format(self._variable),
                            self._variable_path,
                            clear_variables=True,
                        )
                        self.l('{variable}_contains = True')
                        self.l('break')
                    self.l('except JsonSchemaValidationException: pass')

                with self.l('if not {variable}_contains:'):
                    self.exc('must contain one of contains definition', rule='contains')

    def generate_const(self):
        """
        Means that value is valid when is equeal to const definition.

        .. code-block:: python

            {
                'const': 42,
            }

        Only valid value is 42 in this example.
        """
        const = self._definition['const']
        if isinstance(const, str):
            const = '"{}"'.format(const)
        with self.l('if {variable} != {}:', const):
            self.exc('must be const {} but is: " + str({variable}) + "', self.e(const), rule='const')
