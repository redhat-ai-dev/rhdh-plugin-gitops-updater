from typing import Any
from unittest.mock import patch

import pytest
from packaging.version import Version

from src.loader import RHDHPluginsConfigLoader
from src.types import RHDHPlugin, RHDHPluginUpdate
from src.updater import RHDHPluginConfigUpdater


class TestRHDHPluginConfigUpdater:
    """
    handles all tests for RHDHPluginConfigUpdater class.
    """

    def test_init_with_defaults(self) -> "None":
        updater = RHDHPluginConfigUpdater()
        assert updater.config_path == "dynamic-plugins.yaml"
        assert updater.config_location == "redhat-developer-hub.dynamicPlugins.plugins"

    def test_init_with_custom_values(self) -> "None":
        updater = RHDHPluginConfigUpdater(
            config_path="/custom/path.yaml", config_location="custom.location"
        )
        assert updater.config_path == "/custom/path.yaml"
        assert updater.config_location == "custom.location"

    def test_update_plugin_version_in_content_success(
        self, sample_yaml_content: "str", sample_plugin: "RHDHPlugin"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        new_version = Version("0.1.3")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content, sample_plugin, new_version
        )

        assert "next__0.1.3" in updated_content
        assert "next__0.1.2" not in updated_content
        assert updated_content != sample_yaml_content

    def test_update_plugin_version_in_content_preserves_formatting(
        self, sample_yaml_content: "str", sample_plugin: "RHDHPlugin"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        new_version = Version("0.1.3")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content, sample_plugin, new_version
        )

        # check that structure is preserved
        assert "global:" in updated_content
        assert "dynamic:" in updated_content
        assert "plugins:" in updated_content
        assert "disabled: false" in updated_content

    def test_update_plugin_version_in_content_no_match(
        self, sample_yaml_content: "str"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        non_existent_plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/non-existent",
            current_version=Version("1.0.0"),
            plugin_name="non-existent-plugin",
            disabled=False,
        )
        new_version = Version("1.0.1")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content, non_existent_plugin, new_version
        )

        # content should be unchanged
        assert updated_content == sample_yaml_content

    def test_update_plugin_version_updates_correct_plugin_only(
        self, sample_yaml_content: "str"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            current_version=Version("0.2.0"),
            plugin_name="red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            disabled=False,
        )
        new_version = Version("0.2.1")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content, plugin, new_version
        )

        # check that the correct plugin was updated
        assert "software-catalog-mcp-tool:next__0.2.1" in updated_content
        # check that other plugin was not affected
        assert "mcp-actions-backend:next__0.1.2" in updated_content

    @pytest.mark.parametrize(
        ("old_section", "new_section"),
        [
            ("dynamic", "dynamicPlugins"),
            ("lightspeed", "intelligentAssistant"),
        ],
    )
    def test_update_matching_package_in_new_and_legacy_locations(
        self, tmp_path: "Any", old_section: "str", new_section: "str"
    ) -> "None":
        package = (
            "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/"
            "shared-plugin:next__1.0.0"
        )
        content = f"""global:
  {old_section}:
    plugins:
      - package: {package}
redhat-developer-hub:
  {new_section}:
    plugins:
      - package: {package}
"""
        config_path = tmp_path / "values.yaml"
        config_path.write_text(content)

        plugins = RHDHPluginsConfigLoader(config_path=config_path).load_rhdh_plugins()
        assert len(plugins) == 1

        updated = RHDHPluginConfigUpdater(config_path=config_path).update_rhdh_plugin(
            plugins[0], Version("1.0.1")
        )

        assert updated.count("shared-plugin:next__1.0.1") == 2
        assert "shared-plugin:next__1.0.0" not in updated

    def test_update_rhdh_plugin(
        self, temp_yaml_file: "Any", sample_plugin: "RHDHPlugin"
    ) -> "None":
        updater = RHDHPluginConfigUpdater(config_path=temp_yaml_file)
        new_version = Version("0.1.3")

        updated_content = updater.update_rhdh_plugin(sample_plugin, new_version)

        assert "next__0.1.3" in updated_content
        assert "next__0.1.2" not in updated_content

    def test_bulk_update_rhdh_plugins(self, temp_yaml_file: "Any") -> "None":
        updater = RHDHPluginConfigUpdater(config_path=temp_yaml_file)

        plugin1 = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend",
            current_version=Version("0.1.2"),
            plugin_name="backstage-plugin-mcp-actions-backend",
            disabled=False,
        )
        plugin2 = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            current_version=Version("0.2.0"),
            plugin_name="red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            disabled=False,
        )

        updates = [
            RHDHPluginUpdate(rhdh_plugin=plugin1, new_version=Version("0.1.3")),
            RHDHPluginUpdate(rhdh_plugin=plugin2, new_version=Version("0.2.1")),
        ]

        updated_content = updater.bulk_update_rhdh_plugins(updates)

        assert "next__0.1.3" in updated_content
        assert "next__0.2.1" in updated_content
        assert "next__0.1.2" not in updated_content
        assert "next__0.2.0" not in updated_content

    def test_update_rhdh_plugin_file_not_found(self) -> "None":
        updater = RHDHPluginConfigUpdater(config_path="/non/existent/file.yaml")
        plugin = RHDHPlugin(
            package_name="test",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
        )

        with pytest.raises(FileNotFoundError):
            updater.update_rhdh_plugin(plugin, Version("1.0.1"))

    def test_find_current_tag_prefix_with_next_prefix(
        self, sample_yaml_content: "str", sample_plugin: "RHDHPlugin"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()

        result = updater._find_current_tag_prefix(sample_yaml_content, sample_plugin)

        assert result == "next__"

    def test_find_current_tag_prefix_with_multiple_prefixes(
        self,
        sample_yaml_content_with_multiple_prefixes: "str",
        sample_plugin_with_stable_prefix: "RHDHPlugin",
    ) -> "None":
        from unittest.mock import patch

        updater = RHDHPluginConfigUpdater()

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            result = updater._find_current_tag_prefix(
                sample_yaml_content_with_multiple_prefixes,
                sample_plugin_with_stable_prefix,
            )

        assert result == "stable__"

    def test_find_current_tag_prefix_with_previous_prefix(
        self,
        sample_yaml_content_with_multiple_prefixes: "str",
        sample_plugin_with_previous_prefix: "RHDHPlugin",
    ) -> "None":
        from unittest.mock import patch

        updater = RHDHPluginConfigUpdater()

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            result = updater._find_current_tag_prefix(
                sample_yaml_content_with_multiple_prefixes,
                sample_plugin_with_previous_prefix,
            )

        assert result == "previous__"

    def test_find_current_tag_prefix_defaults_to_first_when_not_found(
        self, sample_yaml_content: "str"
    ) -> "None":
        from unittest.mock import patch

        updater = RHDHPluginConfigUpdater()
        non_existent_plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/non-existent",
            current_version=Version("1.0.0"),
            plugin_name="non-existent-plugin",
            disabled=False,
        )

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__"],
        ):
            result = updater._find_current_tag_prefix(
                sample_yaml_content, non_existent_plugin
            )

        assert result == "next__"

    def test_update_plugin_version_preserves_original_prefix(
        self,
        sample_yaml_content_with_multiple_prefixes: "str",
        sample_plugin_with_stable_prefix: "RHDHPlugin",
    ) -> "None":
        from unittest.mock import patch

        updater = RHDHPluginConfigUpdater()
        new_version = Version("0.2.1")

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            updated_content = updater._update_plugin_version_in_content(
                sample_yaml_content_with_multiple_prefixes,
                sample_plugin_with_stable_prefix,
                new_version,
            )

        assert "stable__0.2.1" in updated_content
        assert "stable__0.2.0" not in updated_content
        assert "next__0.1.2" in updated_content
        assert "previous__1.0.0" in updated_content

    def test_update_plugin_version_with_different_prefixes(
        self,
        sample_yaml_content_with_multiple_prefixes: "str",
        sample_plugin_with_previous_prefix: "RHDHPlugin",
    ) -> "None":
        from unittest.mock import patch

        updater = RHDHPluginConfigUpdater()
        new_version = Version("1.1.0")

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["next__", "stable__", "previous__"],
        ):
            updated_content = updater._update_plugin_version_in_content(
                sample_yaml_content_with_multiple_prefixes,
                sample_plugin_with_previous_prefix,
                new_version,
            )

        assert "previous__1.1.0" in updated_content
        assert "previous__1.0.0" not in updated_content
        assert "next__0.1.2" in updated_content
        assert "stable__0.2.0" in updated_content

    def test_build_version_string_with_single_version(self) -> "None":
        updater = RHDHPluginConfigUpdater()
        version = Version("1.42.5")

        result = updater._build_version_string(version)

        assert result == "1.42.5"

    def test_build_version_string_with_dual_version(self) -> "None":
        updater = RHDHPluginConfigUpdater()
        version = Version("1.42.5")
        second_version = Version("0.1.0")

        result = updater._build_version_string(version, second_version)

        assert result == "1.42.5__0.1.0"

    def test_build_version_string_with_none_second_version(self) -> "None":
        updater = RHDHPluginConfigUpdater()
        version = Version("1.42.5")

        result = updater._build_version_string(version, None)

        assert result == "1.42.5"

    def test_update_plugin_version_with_dual_version(
        self, sample_yaml_content_with_dual_versions: "str"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/dual-version-plugin",
            current_version=Version("1.42.5"),
            plugin_name="dual-version-plugin",
            disabled=False,
            current_second_version=Version("0.1.0"),
        )
        new_version = Version("1.43.0")
        new_second_version = Version("0.2.0")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content_with_dual_versions,
            plugin,
            new_version,
            new_second_version,
        )

        assert "next__1.43.0__0.2.0" in updated_content
        assert "next__1.42.5__0.1.0" not in updated_content

    def test_update_plugin_version_from_dual_to_single(
        self, sample_yaml_content_with_dual_versions: "str"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/dual-version-plugin",
            current_version=Version("1.42.5"),
            plugin_name="dual-version-plugin",
            disabled=False,
            current_second_version=Version("0.1.0"),
        )
        new_version = Version("2.0.0")
        # no second version in new version

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content_with_dual_versions, plugin, new_version
        )

        assert "next__2.0.0" in updated_content
        assert "next__1.42.5__0.1.0" not in updated_content

    def test_update_plugin_version_from_single_to_dual(
        self, sample_yaml_content: "str", sample_plugin: "RHDHPlugin"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        new_version = Version("0.2.0")
        new_second_version = Version("1.0.0")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content, sample_plugin, new_version, new_second_version
        )

        assert "next__0.2.0__1.0.0" in updated_content
        assert "next__0.1.2" not in updated_content

    def test_find_current_tag_prefix_with_dual_version(
        self, sample_yaml_content_with_dual_versions: "str"
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/dual-version-plugin",
            current_version=Version("1.42.5"),
            plugin_name="dual-version-plugin",
            disabled=False,
            current_second_version=Version("0.1.0"),
        )

        result = updater._find_current_tag_prefix(
            sample_yaml_content_with_dual_versions, plugin
        )

        assert result == "next__"

    def test_bulk_update_with_dual_versions(
        self, temp_yaml_file_with_dual_versions: "Any"
    ) -> "None":
        updater = RHDHPluginConfigUpdater(config_path=temp_yaml_file_with_dual_versions)

        plugin1 = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/dual-version-plugin",
            current_version=Version("1.42.5"),
            plugin_name="dual-version-plugin",
            disabled=False,
            current_second_version=Version("0.1.0"),
        )
        plugin2 = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend",
            current_version=Version("0.1.2"),
            plugin_name="backstage-plugin-mcp-actions-backend",
            disabled=False,
        )

        updates = [
            RHDHPluginUpdate(
                rhdh_plugin=plugin1,
                new_version=Version("1.43.0"),
                new_second_version=Version("0.2.0"),
            ),
            RHDHPluginUpdate(
                rhdh_plugin=plugin2,
                new_version=Version("0.2.0"),
                new_second_version=Version("1.0.0"),
            ),
        ]

        updated_content = updater.bulk_update_rhdh_plugins(updates)

        assert "next__1.43.0__0.2.0" in updated_content
        assert "next__0.2.0__1.0.0" in updated_content
        assert "next__1.42.5__0.1.0" not in updated_content
        assert "next__0.1.2" not in updated_content

    def test_update_rhdh_plugin_with_dual_version(
        self, temp_yaml_file_with_dual_versions: "Any"
    ) -> "None":
        updater = RHDHPluginConfigUpdater(config_path=temp_yaml_file_with_dual_versions)
        plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/dual-version-plugin",
            current_version=Version("1.42.5"),
            plugin_name="dual-version-plugin",
            disabled=False,
            current_second_version=Version("0.1.0"),
        )
        new_version = Version("1.43.0")
        new_second_version = Version("0.2.0")

        updated_content = updater.update_rhdh_plugin(
            plugin, new_version, new_second_version
        )

        assert "next__1.43.0__0.2.0" in updated_content
        assert "next__1.42.5__0.1.0" not in updated_content

    def test_update_plugin_version_without_exclamation(
        self,
        sample_yaml_content_without_exclamation: "str",
        sample_plugin: "RHDHPlugin",
    ) -> "None":
        updater = RHDHPluginConfigUpdater()
        new_version = Version("0.1.3")

        updated_content = updater._update_plugin_version_in_content(
            sample_yaml_content_without_exclamation, sample_plugin, new_version
        )

        assert "next__0.1.3" in updated_content
        assert "next__0.1.2" not in updated_content
        assert updated_content != sample_yaml_content_without_exclamation

    def test_find_current_tag_prefix_without_exclamation(
        self,
        sample_yaml_content_without_exclamation: "str",
        sample_plugin: "RHDHPlugin",
    ) -> "None":
        updater = RHDHPluginConfigUpdater()

        result = updater._find_current_tag_prefix(
            sample_yaml_content_without_exclamation, sample_plugin
        )

        assert result == "next__"

    def test_bulk_update_without_exclamation(
        self, temp_yaml_file_without_exclamation: "Any"
    ) -> "None":
        updater = RHDHPluginConfigUpdater(
            config_path=temp_yaml_file_without_exclamation
        )

        plugin1 = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend",
            current_version=Version("0.1.2"),
            plugin_name="backstage-plugin-mcp-actions-backend",
            disabled=False,
        )
        plugin2 = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            current_version=Version("0.2.0"),
            plugin_name="red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            disabled=False,
        )

        updates = [
            RHDHPluginUpdate(rhdh_plugin=plugin1, new_version=Version("0.1.3")),
            RHDHPluginUpdate(rhdh_plugin=plugin2, new_version=Version("0.2.1")),
        ]

        updated_content = updater.bulk_update_rhdh_plugins(updates)

        assert "next__0.1.3" in updated_content
        assert "next__0.2.1" in updated_content
        assert "next__0.1.2" not in updated_content
        assert "next__0.2.0" not in updated_content

    def test_update_plugin_does_not_match_substring_plugin_name(self) -> "None":
        updater = RHDHPluginConfigUpdater()
        # known issue where if one plugin's name is a substring of another, it may
        # incorrectly match and update the wrong plugin.
        content = """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-lightspeed-backend:bs_1.45.3__1.2.3
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-lightspeed:bs_1.45.3__1.2.3
"""
        plugin = RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-lightspeed",
            current_version=Version("1.45.3"),
            plugin_name="red-hat-developer-hub-backstage-plugin-lightspeed",
            disabled=False,
            current_second_version=Version("1.2.3"),
            current_tag_prefix="bs_",
        )
        new_version = Version("1.45.3")
        new_second_version = Version("1.2.4")

        with patch(
            "src.types.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
            ["bs_", "next__"],
        ):
            updated_content = updater._update_plugin_version_in_content(
                content, plugin, new_version, new_second_version
            )

        # lightspeed should be updated
        assert (
            "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-lightspeed:bs_1.45.3__1.2.4"
            in updated_content
        )
        # lightspeed-backend should NOT be updated
        assert (
            "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-lightspeed-backend:bs_1.45.3__1.2.3"
            in updated_content
        )
