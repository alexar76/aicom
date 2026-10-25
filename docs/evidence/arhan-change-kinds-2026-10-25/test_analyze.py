"""Independent counterexamples for the Arhan tool-set change analysis.

Run with the standard library on the Linux measurement host:
    python3 -m unittest discover -s . -p test_analyze.py -v

These cases exercise distinctions relevant to the published counts. They do not
execute MCP servers, install packages, or make network requests.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("arhan_analysis", SCRIPT)
ANALYSIS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ANALYSIS
SPEC.loader.exec_module(ANALYSIS)
compare = ANALYSIS.compare_toolsets


def tool(name="search", description="Find records", schema=None, **extra):
    value = {
        "name": name,
        "description": description,
        "inputSchema": copy.deepcopy(schema if schema is not None else {"type": "object"}),
    }
    value.update(copy.deepcopy(extra))
    return value


class CompareToolsetsTest(unittest.TestCase):
    def result(self, old, new):
        return compare([old], [new])

    def assert_flag(self, result, name, expected=True):
        self.assertIs(result["flags"][name], expected, name)

    def test_tool_order_and_object_key_order_are_not_recorded_changes(self):
        first = tool(schema={"type": "object", "properties": {"q": {"type": "string"}}})
        reordered = {
            "inputSchema": {"properties": {"q": {"type": "string"}}, "type": "object"},
            "description": "Find records",
            "name": "search",
        }
        result = compare([first, tool("status")], [tool("status"), reordered])
        self.assertEqual(result["primary"], "unchanged")
        self.assertEqual(result["description_kind"], "unchanged")
        self.assert_flag(result, "composition", False)

    def test_description_whitespace_has_its_own_category(self):
        result = self.result(tool(description="Find records"), tool(description=" Find\nrecords "))
        self.assertEqual(result["primary"], "description_whitespace")
        self.assertEqual(result["tool_description_kind"], "whitespace")
        self.assert_flag(result, "descriptions_only")
        self.assert_flag(result, "tool_descriptions_only")

    def test_numeric_only_is_consistent_for_tool_and_parameter_descriptions(self):
        direct = self.result(tool(description="Limit 100 records"), tool(description="Limit 200 records"))
        parameter = self.result(
            tool(schema={"properties": {"q": {"type": "string", "description": "Limit 100 records"}}}),
            tool(schema={"properties": {"q": {"type": "string", "description": "Limit 200 records"}}}),
        )
        for result in (direct, parameter):
            self.assertEqual(result["primary"], "description_numeric")
            self.assertEqual(result["description_kind"], "numeric")
            self.assert_flag(result, "descriptions_only")
            self.assert_flag(result, "schema_contract", False)
        self.assertEqual(parameter["tool_description_kind"], "unchanged")
        self.assert_flag(parameter, "tool_descriptions_only", False)

    def test_long_description_tail_is_not_lost_to_summary_truncation(self):
        prefix = "Public documentation. " * 1_500
        result = self.result(
            tool(description=prefix + "Read local files."),
            tool(description=prefix + "Upload local files."),
        )
        self.assertEqual(result["primary"], "description_text")
        self.assertEqual(result["description_kind"], "text")
        self.assert_flag(result, "descriptions_only")

    def test_composition_retains_other_flags_and_rename_is_add_remove(self):
        result = compare(
            [tool("search", "Find files"), tool("old_name")],
            [tool("search", "Delete files"), tool("new_name")],
        )
        self.assertEqual(result["primary"], "composition")
        self.assert_flag(result, "composition")
        self.assert_flag(result, "tool_description")
        self.assert_flag(result, "descriptions_only", False)

    def test_schema_contract_priority_does_not_hide_description_changes(self):
        result = self.result(
            tool(description="Find files", schema={"properties": {"q": {"type": "string"}}}),
            tool(description="Delete files", schema={"properties": {"q": {"type": "integer"}}}),
        )
        self.assertEqual(result["primary"], "schema_contract")
        self.assertEqual(result["description_kind"], "text")
        self.assert_flag(result, "tool_description")
        self.assert_flag(result, "schema_contract")
        self.assert_flag(result, "descriptions_only", False)

    def test_description_visitor_recognizes_actual_nested_schema_nodes(self):
        old_child = {"type": "string", "description": "A query"}
        new_child = {"type": "string", "description": "A destructive command"}
        wrappers = {
            "property": lambda child: {"properties": {"q": child}},
            "array_items": lambda child: {"type": "array", "items": child},
            "definition": lambda child: {"$defs": {"Query": child}},
            "legacy_definition": lambda child: {"definitions": {"Query": child}},
            "alternative": lambda child: {"anyOf": [child]},
            "additional_properties": lambda child: {"additionalProperties": child},
        }
        for label, wrapper in wrappers.items():
            with self.subTest(label=label):
                result = self.result(tool(schema=wrapper(old_child)), tool(schema=wrapper(new_child)))
                self.assertEqual(result["primary"], "description_text")
                self.assert_flag(result, "parameter_description")
                self.assert_flag(result, "descriptions_only")
                self.assert_flag(result, "schema_contract", False)

    def test_property_named_description_is_not_a_description_annotation(self):
        result = self.result(
            tool(schema={"type": "object", "properties": {}}),
            tool(schema={"type": "object", "properties": {"description": {"type": "string"}}}),
        )
        self.assertEqual(result["primary"], "schema_contract")
        self.assert_flag(result, "parameter_description", False)
        self.assert_flag(result, "descriptions_only", False)

    def test_description_inside_default_is_literal_data(self):
        result = self.result(
            tool(schema={"default": {"description": "Find files"}}),
            tool(schema={"default": {"description": "Delete files"}}),
        )
        self.assertEqual(result["primary"], "schema_contract")
        self.assert_flag(result, "parameter_description", False)

    def test_description_inside_enum_is_literal_data(self):
        result = self.result(
            tool(schema={"enum": [{"description": "Find files"}]}),
            tool(schema={"enum": [{"description": "Delete files"}]}),
        )
        self.assertEqual(result["primary"], "schema_contract")
        self.assert_flag(result, "parameter_description", False)

    def test_dialect_and_reference_base_are_contract_changes(self):
        for key, old, new in (
            ("$schema", "http://json-schema.org/draft-04/schema#", "https://json-schema.org/draft/2020-12/schema"),
            ("$id", "https://example.org/v1/root", "https://example.org/v2/root"),
            ("$ref", "#/$defs/Public", "#/$defs/Private"),
        ):
            with self.subTest(key=key):
                result = self.result(tool(schema={key: old}), tool(schema={key: new}))
                self.assertEqual(result["primary"], "schema_contract")
                self.assert_flag(result, "schema_annotation", False)

    def test_unique_required_permutation_has_separate_order_category(self):
        result = self.result(tool(schema={"required": ["q", "limit"]}), tool(schema={"required": ["limit", "q"]}))
        self.assertEqual(result["primary"], "schema_order")
        self.assert_flag(result, "schema_order")
        self.assert_flag(result, "schema_contract", False)

    def test_unique_enum_permutation_preserves_typed_json_values(self):
        result = self.result(
            tool(schema={"enum": [False, 1, "1", {"x": [1, 2]}]}),
            tool(schema={"enum": [{"x": [1, 2]}, "1", 1, False]}),
        )
        self.assertEqual(result["primary"], "schema_order")
        self.assert_flag(result, "schema_contract", False)

    def test_duplicate_array_members_do_not_qualify_for_unique_permutation(self):
        for key in ("required", "enum"):
            with self.subTest(key=key):
                result = self.result(tool(schema={key: ["a", "a", "b"]}), tool(schema={key: ["b", "a", "a"]}))
                self.assertEqual(result["primary"], "schema_contract")

    def test_prefix_items_order_is_part_of_the_contract(self):
        first, second = {"type": "string"}, {"type": "integer"}
        result = self.result(tool(schema={"prefixItems": [first, second]}), tool(schema={"prefixItems": [second, first]}))
        self.assertEqual(result["primary"], "schema_contract")
        self.assert_flag(result, "schema_order", False)

    def test_type_array_order_is_not_folded_into_required_enum_order(self):
        result = self.result(tool(schema={"type": ["string", "null"]}), tool(schema={"type": ["null", "string"]}))
        self.assertEqual(result["primary"], "schema_contract")
        self.assert_flag(result, "schema_order", False)

    def test_boolean_and_integer_are_not_equal_json_values(self):
        for key in ("default", "const"):
            with self.subTest(key=key):
                result = self.result(tool(schema={key: True}), tool(schema={key: 1}))
                self.assertEqual(result["primary"], "schema_contract")
        result = self.result(tool(schema={"enum": [False, 1]}), tool(schema={"enum": [0, True]}))
        self.assertEqual(result["primary"], "schema_contract")

    def test_absent_and_empty_output_schema_are_different_contracts(self):
        result = self.result(tool(), tool(outputSchema={}))
        self.assertEqual(result["primary"], "schema_contract")
        self.assert_flag(result, "output_schema")
        self.assert_flag(result, "input_schema", False)

    def test_actual_schema_annotations_are_reported_without_contract_claim(self):
        result = self.result(
            tool(schema={"type": "string", "title": "Query", "examples": ["a"]}),
            tool(schema={"type": "string", "title": "Search term", "examples": ["b"]}),
        )
        self.assertEqual(result["primary"], "schema_annotation")
        self.assert_flag(result, "schema_annotation")
        self.assert_flag(result, "schema_contract", False)
        self.assert_flag(result, "descriptions_only", False)

    def test_literal_fields_named_title_or_examples_remain_contract_changes(self):
        for key in ("title", "examples", "required", "enum"):
            with self.subTest(key=key):
                result = self.result(
                    tool(schema={"default": {key: ["a", "b"]}}),
                    tool(schema={"default": {key: ["b", "a"]}}),
                )
                self.assertEqual(result["primary"], "schema_contract")
                self.assert_flag(result, "schema_annotation", False)
                self.assert_flag(result, "schema_order", False)


if __name__ == "__main__":
    unittest.main()
