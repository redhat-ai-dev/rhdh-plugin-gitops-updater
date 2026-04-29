import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.version import Version

from src.exceptions import InvalidRHDHPluginPackageDefinitionException
from src.loader import RHDHPluginsConfigLoader


class TestRHDHPluginsConfigLoader:
    """
    handles all tests for RHDHPluginsConfigLoader class.
    """

    def test_init_with_defaults(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        assert loader.config_path == "dynamic-plugins.yaml"
        assert loader.config_location == "global.dynamic.plugins"

    def test_init_with_custom_values(self) -> "None":
        loader = RHDHPluginsConfigLoader(
            config_path="/custom/path.yaml", config_location="custom.location"
        )
        assert loader.config_path == "/custom/path.yaml"
        assert loader.config_location == "custom.location"

    def test_fetch_plugins_by_location(
        self, sample_config_data: "dict[str, Any]"
    ) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins = loader._fetch_plugins_by_location(sample_config_data)

        assert isinstance(plugins, list)
        assert len(plugins) == 4

    def test_fetch_plugins_by_location_empty_when_not_list(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        data = {"global": {"dynamic": {"plugins": "not_a_list"}}}
        plugins = loader._fetch_plugins_by_location(data)

        assert plugins == []

    def test_parse_package_string_valid(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend"

        result = loader._parse_package_string(package)

        assert (
            result["package_name"]
            == "rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend"
        )
        assert result["version"] == Version("0.1.2")
        assert result["plugin_name"] == "backstage-plugin-mcp-actions-backend"

    def test_parse_package_string_invalid_no_oci_prefix(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "ghcr.io/redhat-developer/plugin:next__1.0.0!plugin"

        with pytest.raises(InvalidRHDHPluginPackageDefinitionException) as exc_info:
            loader._parse_package_string(package)

        assert "Invalid RHDH plugin package definition" in str(exc_info.value)

    def test_parse_package_string_without_exclamation(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__1.0.0"

        result = loader._parse_package_string(package)

        assert (
            result["package_name"]
            == "rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend"
        )
        assert result["version"] == Version("1.0.0")
        assert result["plugin_name"] == "backstage-plugin-mcp-actions-backend"

    def test_parse_package_string_invalid_no_colon(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin!plugin-name"

        with pytest.raises(InvalidRHDHPluginPackageDefinitionException) as exc_info:
            loader._parse_package_string(package)

        assert "Tag not found" in str(exc_info.value)

    def test_parse_package_string_invalid_no_colon_without_exclamation(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin"

        with pytest.raises(InvalidRHDHPluginPackageDefinitionException) as exc_info:
            loader._parse_package_string(package)

        assert "Tag not found" in str(exc_info.value)

    def test_parse_package_string_invalid_wrong_tag_prefix(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin:v1.0.0!plugin-name"

        with pytest.raises(InvalidRHDHPluginPackageDefinitionException) as exc_info:
            loader._parse_package_string(package)

        assert "not valid for package" in str(exc_info.value)

    def test_parse_package_string_handles_complex_plugin_names(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:next__0.2.0!red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool"

        result = loader._parse_package_string(package)

        assert (
            result["plugin_name"]
            == "red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool"
        )
        assert result["version"] == Version("0.2.0")

    def test_convert_rhdhplugin_list_filters_non_rhdh_plugins(
        self, sample_config_data: "dict[str, Any]"
    ) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins_list = sample_config_data["global"]["dynamic"]["plugins"]

        result = loader._convert_rhdhplugin_list(plugins_list)

        # should only get RHDH-specific plugins
        assert len(result) == 2
        assert all(
            plugin.package_name.startswith("rhdh-plugin-export-overlays/")
            for plugin in result
        )

    def test_convert_rhdhplugin_list_filters_disabled_plugins(
        self, sample_config_data: "dict[str, Any]"
    ) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins_list = sample_config_data["global"]["dynamic"]["plugins"]

        result = loader._convert_rhdhplugin_list(plugins_list)

        # disabled plugin should be filtered out
        assert all(not plugin.disabled for plugin in result)

    def test_convert_rhdhplugin_list_handles_invalid_packages(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins_list = [
            {
                "disabled": False,
                "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/invalid!missing-version",
            }
        ]

        # should handle exception gracefully and return empty list
        result = loader._convert_rhdhplugin_list(plugins_list)
        assert result == []

    def test_load_rhdh_plugins(self, temp_config_file: "str") -> "None":
        loader = RHDHPluginsConfigLoader(config_path=temp_config_file)

        plugins = loader.load_rhdh_plugins()

        assert isinstance(plugins, list)
        # again only non-disabled RHDH-specific plugins
        assert len(plugins) == 2
        assert all(hasattr(plugin, "plugin_name") for plugin in plugins)
        assert all(hasattr(plugin, "current_version") for plugin in plugins)

    def test_load_rhdh_plugins_file_not_found(self) -> "None":
        loader = RHDHPluginsConfigLoader(config_path="/non/existent/file.yaml")

        with pytest.raises(FileNotFoundError):
            loader.load_rhdh_plugins()

    def test_load_rhdh_plugins_invalid_yaml(self) -> "None":
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        loader = RHDHPluginsConfigLoader(config_path=temp_path)

        with pytest.raises(yaml.YAMLError):
            loader.load_rhdh_plugins()

        # clean everything
        Path(temp_path).unlink()

    def test_match_tag_prefix_with_next_prefix(self) -> "None":
        from src.utils import match_tag_prefix

        tag = "next__0.1.2"

        result = match_tag_prefix(tag)

        assert result == "next__"

    def test_match_tag_prefix_with_other_prefix(self) -> "None":
        from unittest.mock import patch

        from src.utils import match_tag_prefix

        tag = "stable__1.0.0"

        # temporarily override the config to include multiple prefixes
        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            result = match_tag_prefix(tag)

        assert result == "stable__"

    def test_match_tag_prefix_no_match(self) -> "None":
        from src.utils import match_tag_prefix

        tag = "v1.0.0"

        result = match_tag_prefix(tag)

        assert result is None

    def test_match_tag_prefix_partial_match(self) -> "None":
        from unittest.mock import patch

        from src.utils import match_tag_prefix

        # prefix is in the middle of the tag, not at the start
        tag = "some-next__0.1.2"

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__"],
        ):
            result = match_tag_prefix(tag)

        # should not match since prefix must be at the start
        assert result is None

    def test_parse_package_string_with_different_prefix(self) -> "None":
        from unittest.mock import patch

        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:stable__0.1.2!backstage-plugin-mcp-actions-backend"

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            result = loader._parse_package_string(package)

        assert (
            result["package_name"]
            == "rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend"
        )
        assert result["version"] == Version("0.1.2")
        assert result["plugin_name"] == "backstage-plugin-mcp-actions-backend"

    def test_parse_package_string_with_multiple_prefixes_configured(self) -> "None":
        from unittest.mock import patch

        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/test-plugin:previous__2.0.0!test-plugin"

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            result = loader._parse_package_string(package)

        assert result["version"] == Version("2.0.0")
        assert result["plugin_name"] == "test-plugin"

    def test_parse_package_string_with_dual_version(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin:next__1.42.5__0.1.0!backstage-plugin"

        result = loader._parse_package_string(package)

        assert result["package_name"] == "rhdh-plugin-export-overlays/backstage-plugin"
        assert result["version"] == Version("1.42.5")
        assert result["second_version"] == Version("0.1.0")
        assert result["plugin_name"] == "backstage-plugin"

    def test_parse_package_string_with_dual_version_complex(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/test-plugin:next__2.10.15__1.5.3!test-plugin"

        result = loader._parse_package_string(package)

        assert result["version"] == Version("2.10.15")
        assert result["second_version"] == Version("1.5.3")

    def test_parse_package_string_single_version_has_no_second_version(
        self,
    ) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin:next__1.0.0!backstage-plugin"

        result = loader._parse_package_string(package)

        assert result["version"] == Version("1.0.0")
        assert result["second_version"] is None

    def test_convert_rhdhplugin_list_with_dual_version_plugins(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins_list = [
            {
                "disabled": False,
                "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin1:next__1.42.5__0.1.0!plugin1",
            },
            {
                "disabled": False,
                "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin2:next__2.0.0!plugin2",
            },
        ]

        result = loader._convert_rhdhplugin_list(plugins_list)

        assert len(result) == 2
        # first plugin has dual version
        assert result[0].current_version == Version("1.42.5")
        assert result[0].current_second_version == Version("0.1.0")
        # second plugin has single version
        assert result[1].current_version == Version("2.0.0")
        assert result[1].current_second_version is None

    def test_parse_package_string_without_exclamation_dual_version(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin:next__1.42.5__0.1.0"

        result = loader._parse_package_string(package)

        assert result["package_name"] == "rhdh-plugin-export-overlays/backstage-plugin"
        assert result["version"] == Version("1.42.5")
        assert result["second_version"] == Version("0.1.0")
        assert result["plugin_name"] == "backstage-plugin"

    def test_convert_rhdhplugin_list_without_exclamation(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins_list = [
            {
                "disabled": False,
                "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin1:next__1.42.5__0.1.0",
            },
            {
                "disabled": False,
                "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/plugin2:next__2.0.0",
            },
        ]

        result = loader._convert_rhdhplugin_list(plugins_list)

        assert len(result) == 2
        assert result[0].plugin_name == "plugin1"
        assert result[0].current_version == Version("1.42.5")
        assert result[0].current_second_version == Version("0.1.0")
        assert result[1].plugin_name == "plugin2"
        assert result[1].current_version == Version("2.0.0")
        assert result[1].current_second_version is None

    def test_init_with_default_extra_locations(self) -> "None":
        loader = RHDHPluginsConfigLoader()
        assert loader.extra_config_locations == ["global.lightspeed.plugins"]

    def test_init_with_custom_extra_locations(self) -> "None":
        loader = RHDHPluginsConfigLoader(
            extra_config_locations=["custom.extra.plugins"]
        )
        assert loader.extra_config_locations == ["custom.extra.plugins"]

    def test_init_with_empty_extra_locations(self) -> "None":
        loader = RHDHPluginsConfigLoader(extra_config_locations=[])
        assert loader.extra_config_locations == []

    def test_fetch_plugins_by_location_with_explicit_location(
        self, sample_config_data_with_lightspeed_plugins: "dict[str, Any]"
    ) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins = loader._fetch_plugins_by_location(
            sample_config_data_with_lightspeed_plugins, "global.lightspeed.plugins"
        )
        assert isinstance(plugins, list)
        assert len(plugins) == 1

    def test_fetch_plugins_by_location_missing_extra_location(
        self, sample_config_data: "dict[str, Any]"
    ) -> "None":
        loader = RHDHPluginsConfigLoader()
        plugins = loader._fetch_plugins_by_location(
            sample_config_data, "global.lightspeed.plugins", strict=False
        )
        assert plugins == []

    def test_load_rhdh_plugins_from_both_locations(
        self, temp_yaml_file_with_lightspeed_plugins: "str"
    ) -> "None":
        loader = RHDHPluginsConfigLoader(
            config_path=temp_yaml_file_with_lightspeed_plugins
        )
        plugins = loader.load_rhdh_plugins()
        assert len(plugins) == 2
        plugin_names = [p.plugin_name for p in plugins]
        assert "backstage-plugin-mcp-actions-backend" in plugin_names
        assert "lightspeed-plugin" in plugin_names

    def test_load_rhdh_plugins_from_lightspeed_only(
        self, temp_yaml_file_lightspeed_only: "str"
    ) -> "None":
        loader = RHDHPluginsConfigLoader(config_path=temp_yaml_file_lightspeed_only)
        plugins = loader.load_rhdh_plugins()
        assert len(plugins) == 1
        assert plugins[0].plugin_name == "lightspeed-plugin"

    def test_load_rhdh_plugins_no_extra_locations(
        self, temp_yaml_file_with_lightspeed_plugins: "str"
    ) -> "None":
        loader = RHDHPluginsConfigLoader(
            config_path=temp_yaml_file_with_lightspeed_plugins,
            extra_config_locations=[],
        )
        plugins = loader.load_rhdh_plugins()
        assert len(plugins) == 1
        assert plugins[0].plugin_name == "backstage-plugin-mcp-actions-backend"

    def test_load_rhdh_plugins_lightspeed_disabled_filtered(self) -> "None":
        content = """global:
  dynamic:
    plugins: []
  lightspeed:
    plugins:
      - disabled: true
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/lightspeed-plugin:next__1.0.0!lightspeed-plugin
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            loader = RHDHPluginsConfigLoader(config_path=temp_path)
            plugins = loader.load_rhdh_plugins()
            assert plugins == []
        finally:
            Path(temp_path).unlink()

    def test_load_rhdh_plugins_lightspeed_non_rhdh_filtered(self) -> "None":
        content = """global:
  dynamic:
    plugins: []
  lightspeed:
    plugins:
      - disabled: false
        package: ./local-plugin/dist
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            loader = RHDHPluginsConfigLoader(config_path=temp_path)
            plugins = loader.load_rhdh_plugins()
            assert plugins == []
        finally:
            Path(temp_path).unlink()

    def test_load_rhdh_plugins_missing_lightspeed_location_does_not_exit(
        self, temp_yaml_file: "str"
    ) -> "None":
        # primary location exists but global.lightspeed.plugins
        # is absent - should not exit
        loader = RHDHPluginsConfigLoader(config_path=temp_yaml_file)
        plugins = loader.load_rhdh_plugins()
        assert len(plugins) == 2

    def test_parse_package_string_dual_version_with_different_prefix(self) -> "None":
        from unittest.mock import patch

        loader = RHDHPluginsConfigLoader()
        package = "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/test-plugin:stable__1.43.0__0.2.0!test-plugin"

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            result = loader._parse_package_string(package)

        assert result["version"] == Version("1.43.0")
        assert result["second_version"] == Version("0.2.0")
        assert result["plugin_name"] == "test-plugin"
