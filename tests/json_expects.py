import sys
import json as JSON


class JsonHelper:
    """
    Utility class preparing generated JSON result for testing.

    JSON stores the path to some source items. These need to be genericized in
    order for tests to succeed on all machines/user accounts. This is also the
    case for "anon_" tags, which are "reset" for each test to start from
    "anon_1".
    """

    def __init__(self):
        self.anons = list()
    
    @staticmethod
    def sort_anon_fn(anon_tag):
        return int(anon_tag.split("_")[1])
    
    def prepare(self, json):
        """Prepares generated JSON result for testing"""
        self._search_anon_tags(json)
        unique_list = list(set(self.anons))
        unique_sorted_list = sorted(unique_list, key=JsonHelper.sort_anon_fn)

        mapped_tags = dict()
        counter = 1
        for i in unique_sorted_list:
            mapped_tags[i] = "anon_{0}".format(counter)
            counter += 1

        for (old_tag, new_tag) in mapped_tags.items():
            self._replace_anon_tag(json, old_tag, new_tag)

    def _replace_anon_tag(self, json, tag, new_tag):
        """Replaces source paths and resets anon_ tags to increment from 1"""
        if isinstance(json, list):
            for item in json:
                self._replace_anon_tag(item, tag, new_tag)
            return
        if isinstance(json, dict):
            for key, value in json.items():
                if key == "name" and isinstance(value, str):
                    if value == tag:
                        json[key] = new_tag
                elif key == "tag" and isinstance(value, str):
                    if value == tag:
                        json[key] = new_tag
                elif key == "src" and isinstance(value, list) and value:
                    # for whatever reason, on windows ctypesgen's json output contains double slashes in paths, whereas the expectation contains only single slashes, so normalize the output
                    if sys.platform == "win32":
                        value[0] = value[0].replace("\\\\", "\\")
                    # # ignore the line number so changing headers does not cause erroneous test fails
                    value[1] = None
                else:
                    self._replace_anon_tag(value, tag, new_tag)

    def _search_anon_tags(self, json):
        """Search for anon_ tags"""
        if isinstance(json, list):
            for item in json:
                self._search_anon_tags(item)
            return
        if isinstance(json, dict):
            for key, value in json.items():
                if key == "name" and isinstance(value, str):
                    if value.startswith("anon_"):
                        self.anons.append(value)
                else:
                    self._search_anon_tags(value)


def compare_json(test_instance, json, json_ans, verbose=False):
    json_helper = JsonHelper()
    json_helper.prepare(json)

    print_excess = False
    try:
        test_instance.assertEqual(len(json), len(json_ans))
    except Exception:
        if verbose:
            print(
                "JSONs do not have same length: ",
                len(json),
                "generated vs",
                len(json_ans),
                "stored",
            )
            print_excess = True
        else:
            raise

    # first fix paths that exist inside JSON to avoid user-specific paths:
    for i, ith_json_ans in zip(json, json_ans):
        try:
            test_instance.assertEqual(i, ith_json_ans)
        except Exception:
            if verbose:
                print("\nFailed JSON for: ", i["name"])
                print("GENERATED:\n", i, "\nANS:\n", ith_json_ans)
                print("FAILED FOR================", JSON.dumps(i, indent=4))
                print("GENERATED =============", JSON.dumps(ith_json_ans, indent=4))
            raise

    if print_excess:
        if len(json) > len(json_ans):
            j, jlen, jlabel = json, len(json_ans), "generated"
        else:
            j, jlen, jlabel = json_ans, len(json), "stored"
        import pprint

        print("Excess JSON content from", jlabel, "content:")
        pprint.pprint(j[jlen:])


def get_ans_struct(tmp_header_path):
    return [
        {
            "attrib": {},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "foo",
            "type": "struct",
        },
        {
            "attrib": {"packed": True},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "packed_foo",
            "type": "struct",
        },
        {
            "attrib": {},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "anon_1",
            "type": "struct",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": True,
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "attrib": {},
                "src": [tmp_header_path, None],
                "tag": "anon_1",
                "variety": "struct",
            },
            "name": "foo_t",
            "type": "typedef",
        },
        {
            "attrib": {"packed": True},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "anon_2",
            "type": "struct",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": True,
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "attrib": {"packed": True},
                "src": [tmp_header_path, None],
                "tag": "anon_2",
                "variety": "struct",
            },
            "name": "packed_foo_t",
            "type": "typedef",
        },
        {
            "attrib": {"packed": True, "aligned": [4]},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "anon_3",
            "type": "struct",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": True,
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "attrib": {"packed": True, "aligned": [4]},
                "src": [tmp_header_path, None],
                "tag": "anon_3",
                "variety": "struct",
            },
            "name": "pragma_packed_foo_t",
            "type": "typedef",
        },
        {
            "attrib": {"packed": True, "aligned": [2]},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "pragma_packed_foo2",
            "type": "struct",
        },
        {
            "attrib": {},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "c",
                },
                {
                    "bitfield": "15",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 15,
                        },
                        "errors": [],
                    },
                    "name": "d",
                },
                {
                    "bitfield": "17",
                    "ctype": {
                        "Klass": "CtypesBitfield",
                        "base": {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                        "bitfield": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 17,
                        },
                        "errors": [],
                    },
                    "name": None,
                },
            ],
            "name": "foo3",
            "type": "struct",
        },
        {
            "ctype": {
                "Klass": "CtypesSimple",
                "errors": [],
                "longs": 0,
                "name": "int",
                "signed": True,
            },
            "name": "Int",
            "type": "typedef",
        },
        {
            "attrib": {},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "Int",
                }
            ],
            "name": "anon_4",
            "type": "struct",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": True,
                "errors": [],
                "members": [
                    [
                        "Int",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ]
                ],
                "opaque": False,
                "attrib": {},
                "src": [tmp_header_path, None],
                "tag": "anon_4",
                "variety": "struct",
            },
            "name": "id_struct_t",
            "type": "typedef",
        },
        {
            "attrib": {},
            "fields": [
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "int",
                        "signed": True,
                    },
                    "name": "a",
                },
                {
                    "ctype": {
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "char",
                        "signed": True,
                    },
                    "name": "b",
                },
            ],
            "name": "anon_5",
            "type": "struct",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": True,
                "attrib": {},
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                ],
                "opaque": False,
                "src": [tmp_header_path, None],
                "tag": "anon_5",
                "variety": "struct",
            },
            "name": "BAR0",
            "type": "typedef",
        },
        {
            "ctype": {
                "Klass": "CtypesPointer",
                "destination": {
                    "Klass": "CtypesStruct",
                    "anonymous": True,
                    "attrib": {},
                    "errors": [],
                    "members": [
                        [
                            "a",
                            {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                        ],
                        [
                            "b",
                            {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "char",
                                "signed": True,
                            },
                        ],
                    ],
                    "opaque": False,
                    "src": [tmp_header_path, None],
                    "tag": "anon_5",
                    "variety": "struct",
                },
                "errors": [],
                "qualifiers": [],
            },
            "name": "PBAR0",
            "type": "typedef",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": False,
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "attrib": {},
                "src": [tmp_header_path, None],
                "tag": "foo",
                "variety": "struct",
            },
            "name": "foo",
            "type": "typedef",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": False,
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "attrib": {"packed": True},
                "src": [tmp_header_path, None],
                "tag": "packed_foo",
                "variety": "struct",
            },
            "name": "packed_foo",
            "type": "typedef",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": False,
                "attrib": {"aligned": [2], "packed": True},
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "src": [tmp_header_path, None],
                "tag": "pragma_packed_foo2",
                "variety": "struct",
            },
            "name": "pragma_packed_foo2",
            "type": "typedef",
        },
        {
            "ctype": {
                "Klass": "CtypesStruct",
                "anonymous": False,
                "attrib": {},
                "errors": [],
                "members": [
                    [
                        "a",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "b",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "char",
                            "signed": True,
                        },
                    ],
                    [
                        "c",
                        {
                            "Klass": "CtypesSimple",
                            "errors": [],
                            "longs": 0,
                            "name": "int",
                            "signed": True,
                        },
                    ],
                    [
                        "d",
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 15,
                            },
                            "errors": [],
                        },
                    ],
                    [
                        None,
                        {
                            "Klass": "CtypesBitfield",
                            "base": {
                                "Klass": "CtypesSimple",
                                "errors": [],
                                "longs": 0,
                                "name": "int",
                                "signed": True,
                            },
                            "bitfield": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 17,
                            },
                            "errors": [],
                        },
                    ],
                ],
                "opaque": False,
                "src": [tmp_header_path, None],
                "tag": "foo3",
                "variety": "struct",
            },
            "name": "foo3",
            "type": "typedef",
        },
    ]



def get_ans_enum(tmp_header_path):
    return [
        {
            "fields": [
                {
                    "ctype": {
                        "Klass": "ConstantExpressionNode",
                        "errors": [],
                        "is_literal": False,
                        "value": 0,
                    },
                    "name": "TEST_1",
                },
                {
                    "ctype": {
                        "Klass": "BinaryExpressionNode",
                        "can_be_ctype": [False, False],
                        "errors": [],
                        "format": "(%s + %s)",
                        "left": {
                            "Klass": "IdentifierExpressionNode",
                            "errors": [],
                            "name": "TEST_1",
                        },
                        "name": "addition",
                        "right": {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 1,
                        },
                    },
                    "name": "TEST_2",
                },
            ],
            "name": "anon_1",
            "type": "enum",
        },
        {"name": "TEST_1", "type": "constant", "value": "0"},
        {"name": "TEST_2", "type": "constant", "value": "(TEST_1 + 1)"},
        {
            "ctype": {
                "Klass": "CtypesEnum",
                "anonymous": True,
                "enumerators": [
                    [
                        "TEST_1",
                        {
                            "Klass": "ConstantExpressionNode",
                            "errors": [],
                            "is_literal": False,
                            "value": 0,
                        },
                    ],
                    [
                        "TEST_2",
                        {
                            "Klass": "BinaryExpressionNode",
                            "can_be_ctype": [False, False],
                            "errors": [],
                            "format": "(%s + %s)",
                            "left": {
                                "Klass": "IdentifierExpressionNode",
                                "errors": [],
                                "name": "TEST_1",
                            },
                            "name": "addition",
                            "right": {
                                "Klass": "ConstantExpressionNode",
                                "errors": [],
                                "is_literal": False,
                                "value": 1,
                            },
                        },
                    ],
                ],
                "errors": [],
                "opaque": False,
                "src": [tmp_header_path, None],
                "tag": "anon_1",
            },
            "name": "test_status_t",
            "type": "typedef",
        },
    ]



def get_ans_function_prototypes():
    return [
        {
            "args": [
                {
                    "Klass": "CtypesSimple",
                    "errors": [],
                    "identifier": "a",
                    "longs": 0,
                    "name": "int",
                    "signed": True,
                }
            ],
            "attrib": {},
            "name": "bar2",
            "return": {
                "Klass": "CtypesSimple",
                "errors": [],
                "longs": 0,
                "name": "int",
                "signed": True,
            },
            "type": "function",
            "variadic": False,
        },
        {
            "args": [
                {
                    "Klass": "CtypesSimple",
                    "errors": [],
                    "identifier": "",
                    "longs": 0,
                    "name": "int",
                    "signed": True,
                }
            ],
            "attrib": {},
            "name": "bar",
            "return": {
                "Klass": "CtypesSimple",
                "errors": [],
                "longs": 0,
                "name": "int",
                "signed": True,
            },
            "type": "function",
            "variadic": False,
        },
        {
            "args": [],
            "attrib": {},
            "name": "foo",
            "return": {
                "Klass": "CtypesSimple",
                "errors": [],
                "longs": 0,
                "name": "void",
                "signed": True,
            },
            "type": "function",
            "variadic": False,
        },
        {
            "args": [],
            "attrib": {"stdcall": True},
            "name": "foo2",
            "return": {
                "Klass": "CtypesSimple",
                "errors": [],
                "longs": 0,
                "name": "void",
                "signed": True,
            },
            "type": "function",
            "variadic": False,
        },
        {
            "args": [],
            "attrib": {"stdcall": True},
            "name": "foo3",
            "return": {
                "Klass": "CtypesPointer",
                "destination": {
                    "Klass": "CtypesSimple",
                    "errors": [],
                    "longs": 0,
                    "name":
                    "void",
                    "signed": True,
                },
                "errors": [],
                "qualifiers": [],
            },
            "type": "function",
            "variadic": False,
        },
        {
            "args": [],
            "attrib": {"stdcall": True},
            "name": "foo4",
            "return": {
                "Klass": "CtypesPointer",
                "destination": {
                    "Klass": "CtypesPointer",
                    "destination": {
                        # this return type seems like it really ought to be
                        # the same as for foo3
                        "Klass": "CtypesSimple",
                        "errors": [],
                        "longs": 0,
                        "name": "void",
                        "signed": True,
                    },
                    "errors": [],
                    "qualifiers": [],
                },
                "errors": [],
                "qualifiers": [],
            },
            "type": "function",
            "variadic": False,
        },
        {
            "args": [],
            "attrib": {"stdcall": True},
            "name": "foo5",
            "return": {
                "Klass": "CtypesSimple",
                "errors": [],
                "longs": 0,
                "name": "void",
                "signed": True,
            },
            "type": "function",
            "variadic": False,
        },
    ]
