from typing import Any

import pytest
from packaging.version import Version

from src.utils import (
    build_version_string,
    compare_versions,
    get_plugins_list_from_dict,
    parse_dual_version,
    rhdh_plugin_needs_update,
)


class TestGetPluginsListFromDict:
    """
    handles all tests for get_plugins_list_from_dict function.
    """

    def test_returns_list_at_nested_location(self) -> "None":
        data = {
            "level1": {
                "level2": {"plugins": [{"name": "plugin1"}, {"name": "plugin2"}]}
            }
        }
        keys = ["level1", "level2", "plugins"]
        result = get_plugins_list_from_dict(keys, data)
        assert result == [{"name": "plugin1"}, {"name": "plugin2"}]

    def test_returns_empty_list_when_value_not_list(self) -> "None":
        data = {"level1": {"plugins": "not_a_list"}}
        keys = ["level1", "plugins"]
        result = get_plugins_list_from_dict(keys, data)
        assert result == []

    def test_exits_when_key_not_found(self, capsys: "Any") -> "None":
        data = {"level1": {"other": "value"}}
        keys = ["level1", "missing_key"]

        with pytest.raises(SystemExit) as exc_info:
            get_plugins_list_from_dict(keys, data)

        assert exc_info.value.code == 1

    def test_exits_when_intermediate_value_not_dict(self, capsys: "Any") -> "None":
        data = {"level1": "not_a_dict"}
        keys = ["level1", "nested"]

        with pytest.raises(SystemExit) as exc_info:
            get_plugins_list_from_dict(keys, data)

        assert exc_info.value.code == 1

    def test_handles_single_level_navigation(self) -> "None":
        data = {"plugins": [{"name": "plugin1"}]}
        keys = ["plugins"]
        result = get_plugins_list_from_dict(keys, data)
        assert result == [{"name": "plugin1"}]

    def test_returns_empty_list_when_key_not_found_non_strict(self) -> "None":
        data = {"level1": {"other": "value"}}
        keys = ["level1", "missing_key"]
        result = get_plugins_list_from_dict(keys, data, strict=False)
        assert result == []

    def test_returns_empty_list_when_intermediate_not_dict_non_strict(self) -> "None":
        data = {"level1": "not_a_dict"}
        keys = ["level1", "nested"]
        result = get_plugins_list_from_dict(keys, data, strict=False)
        assert result == []


class TestRHDHPluginNeedsUpdate:
    """
    handles all tests for rhdh_plugin_needs_update function.
    """

    def test_returns_true_when_latest_greater(self) -> "None":
        latest = Version("1.2.0")
        current = Version("1.1.0")
        assert rhdh_plugin_needs_update(latest, current) is True

    def test_returns_false_when_versions_equal(self) -> "None":
        latest = Version("1.1.0")
        current = Version("1.1.0")
        assert rhdh_plugin_needs_update(latest, current) is False

    def test_returns_false_when_current_greater(self) -> "None":
        latest = Version("1.0.0")
        current = Version("1.1.0")
        assert rhdh_plugin_needs_update(latest, current) is False

    def test_handles_semantic_versioning(self) -> "None":
        assert rhdh_plugin_needs_update(Version("2.0.0"), Version("1.9.9")) is True
        assert rhdh_plugin_needs_update(Version("1.0.1"), Version("1.0.0")) is True
        assert rhdh_plugin_needs_update(Version("1.10.0"), Version("1.9.0")) is True

    def test_handles_prerelease_versions(self) -> "None":
        assert rhdh_plugin_needs_update(Version("1.0.0"), Version("1.0.0rc1")) is True
        assert (
            rhdh_plugin_needs_update(Version("1.0.0rc2"), Version("1.0.0rc1")) is True
        )


class TestParseDualVersion:
    """
    handles all tests for parse_dual_version function.
    """

    def test_parses_single_version(self) -> "None":
        version_string = "1.42.5"
        primary, secondary = parse_dual_version(version_string)

        assert primary == Version("1.42.5")
        assert secondary is None

    def test_parses_dual_version(self) -> "None":
        version_string = "1.42.5__0.1.0"
        primary, secondary = parse_dual_version(version_string)

        assert primary == Version("1.42.5")
        assert secondary == Version("0.1.0")

    def test_parses_dual_version_with_complex_versions(self) -> "None":
        version_string = "2.10.15__1.5.3"
        primary, secondary = parse_dual_version(version_string)

        assert primary == Version("2.10.15")
        assert secondary == Version("1.5.3")

    def test_handles_dual_version_with_empty_second_part(self) -> "None":
        version_string = "1.0.0__"
        primary, secondary = parse_dual_version(version_string)

        assert primary == Version("1.0.0")
        assert secondary is None

    def test_handles_multiple_double_underscores(self) -> "None":
        version_string = "1.0.0__2.0.0__extra"

        from packaging.version import InvalidVersion

        with pytest.raises(InvalidVersion):
            parse_dual_version(version_string)


class TestCompareVersions:
    """
    handles all tests for compare_versions function.
    """

    def test_compares_primary_versions_greater(self) -> "None":
        result = compare_versions(Version("2.0.0"), Version("1.0.0"))
        assert result > 0

    def test_compares_primary_versions_less(self) -> "None":
        result = compare_versions(Version("1.0.0"), Version("2.0.0"))
        assert result < 0

    def test_compares_primary_versions_equal(self) -> "None":
        result = compare_versions(Version("1.0.0"), Version("1.0.0"))
        assert result == 0

    def test_compares_secondary_when_primary_equal(self) -> "None":
        result = compare_versions(
            Version("1.0.0"),
            Version("1.0.0"),
            Version("0.2.0"),
            Version("0.1.0"),
        )
        assert result > 0

    def test_compares_secondary_less_when_primary_equal(self) -> "None":
        result = compare_versions(
            Version("1.0.0"),
            Version("1.0.0"),
            Version("0.1.0"),
            Version("0.2.0"),
        )
        assert result < 0

    def test_compares_secondary_equal_when_both_equal(self) -> "None":
        result = compare_versions(
            Version("1.0.0"),
            Version("1.0.0"),
            Version("0.1.0"),
            Version("0.1.0"),
        )
        assert result == 0

    def test_version_with_secondary_greater_than_without(self) -> "None":
        result = compare_versions(
            Version("1.0.0"), Version("1.0.0"), Version("0.1.0"), None
        )
        assert result > 0

    def test_version_without_secondary_less_than_with(self) -> "None":
        result = compare_versions(
            Version("1.0.0"), Version("1.0.0"), None, Version("0.1.0")
        )
        assert result < 0

    def test_primary_version_takes_precedence(self) -> "None":
        result = compare_versions(
            Version("1.0.0"),
            Version("2.0.0"),
            Version("10.0.0"),
            Version("0.1.0"),
        )
        assert result < 0


class TestRHDHPluginNeedsUpdateWithDualVersions:
    """
    handles tests for rhdh_plugin_needs_update with dual version support.
    """

    def test_update_needed_when_primary_version_greater(self) -> "None":
        assert (
            rhdh_plugin_needs_update(
                Version("1.43.0"),
                Version("1.42.5"),
                Version("0.1.0"),
                Version("0.1.0"),
            )
            is True
        )

    def test_update_not_needed_when_versions_equal(self) -> "None":
        assert (
            rhdh_plugin_needs_update(
                Version("1.42.5"),
                Version("1.42.5"),
                Version("0.1.0"),
                Version("0.1.0"),
            )
            is False
        )

    def test_update_needed_when_secondary_version_greater(self) -> "None":
        assert (
            rhdh_plugin_needs_update(
                Version("1.42.5"),
                Version("1.42.5"),
                Version("0.2.0"),
                Version("0.1.0"),
            )
            is True
        )

    def test_update_not_needed_when_secondary_version_less(self) -> "None":
        assert (
            rhdh_plugin_needs_update(
                Version("1.42.5"),
                Version("1.42.5"),
                Version("0.1.0"),
                Version("0.2.0"),
            )
            is False
        )

    def test_update_needed_when_latest_has_secondary_current_does_not(
        self,
    ) -> "None":
        assert (
            rhdh_plugin_needs_update(
                Version("1.42.5"), Version("1.42.5"), Version("0.1.0"), None
            )
            is True
        )

    def test_update_not_needed_when_current_has_secondary_latest_does_not(
        self,
    ) -> "None":
        assert (
            rhdh_plugin_needs_update(
                Version("1.42.5"), Version("1.42.5"), None, Version("0.1.0")
            )
            is False
        )

    def test_primary_version_takes_precedence_over_secondary(self) -> "None":
        # even though current has higher secondary, latest has higher primary
        assert (
            rhdh_plugin_needs_update(
                Version("1.43.0"),
                Version("1.42.5"),
                Version("0.1.0"),
                Version("10.0.0"),
            )
            is True
        )


class TestBuildVersionString:
    """
    handles all tests for build_version_string function.
    """

    def test_single_version(self) -> "None":
        result = build_version_string(Version("1.0.0"))
        assert result == "1.0.0"

    def test_dual_version(self) -> "None":
        result = build_version_string(Version("1.45.3"), Version("0.1.0"))
        assert result == "1.45.3__0.1.0"

    def test_none_second_version(self) -> "None":
        result = build_version_string(Version("1.0.0"), None)
        assert result == "1.0.0"
