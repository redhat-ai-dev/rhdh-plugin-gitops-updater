from dataclasses import replace
from functools import partial
from typing import Any
from unittest.mock import Mock, patch

import pytest
from github import GithubException
from packaging.version import Version

from main import _grouped_update_hash, main
from src.exceptions import GithubPRFailedException
from src.github_api_client import GithubAPIClient
from src.types import (
    GithubPullRequestStrategy,
    RHDHPlugin,
    RHDHPluginPackage,
    RHDHPluginPackageVersion,
    RHDHPluginUpdate,
    RHDHPluginUpdaterConfig,
)
from src.updater import RHDHPluginConfigUpdater


def _configure_grouped_main(
    monkeypatch: "Any",
    items: "list[tuple[RHDHPlugin, RHDHPluginPackage]]",
    pr_creation_limit: "int" = 0,
    config_path: "str" = "dynamic-plugins.yaml",
) -> "tuple[Mock, Mock]":
    monkeypatch.setattr("main.GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr("main.GITHUB_TOKEN", "test_token")
    monkeypatch.setattr("main.GITHUB_REF", "main")
    monkeypatch.setattr("main.DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH", config_path)
    monkeypatch.setattr("main.UPDATE_PR_STRATEGY", "grouped")
    monkeypatch.setattr("main.PR_CREATION_LIMIT", pr_creation_limit)

    loader = Mock()
    loader.load_rhdh_plugins.return_value = [plugin for plugin, _ in items]
    monkeypatch.setattr("main.RHDHPluginsConfigLoader", Mock(return_value=loader))

    api = Mock()
    api._branch_exists.return_value = False
    api.fetch_package.side_effect = [package for _, package in items]
    api.create_pull_request.return_value = "https://github.com/owner/repo/pull/1"
    monkeypatch.setattr("main.GithubAPIClient", Mock(return_value=api))

    updater = Mock()
    updater.bulk_update_rhdh_plugins.return_value = "updated yaml content"
    monkeypatch.setattr("main.RHDHPluginConfigUpdater", Mock(return_value=updater))
    return api, updater


def _plugin_and_package(
    package_name: "str",
    plugin_name: "str",
    current_version: "str",
    new_version: "str",
    tag_prefix: "str | None" = None,
) -> "tuple[RHDHPlugin, RHDHPluginPackage]":
    current, _, current_second = current_version.partition("__")
    target, _, target_second = new_version.partition("__")
    plugin = RHDHPlugin(
        package_name=package_name,
        current_version=Version(current),
        current_second_version=Version(current_second) if current_second else None,
        plugin_name=plugin_name,
        disabled=False,
        current_tag_prefix=tag_prefix,
    )
    package = RHDHPluginPackage(
        name=package_name,
        versions=[
            RHDHPluginPackageVersion(
                name=f"{plugin_name}-latest",
                version=Version(target),
                second_version=Version(target_second) if target_second else None,
                created_at="2024-01-20T10:00:00Z",
            )
        ],
    )
    return plugin, package


@pytest.fixture
def plugin_pair() -> "list[tuple[RHDHPlugin, RHDHPluginPackage]]":
    return [
        _plugin_and_package("scope/pluginabc", "pluginabc", "1.0.0", "1.1.0"),
        _plugin_and_package(
            "scope/pluginabc-backend", "pluginabc-backend", "2.0.0", "2.1.0"
        ),
    ]


class TestMain:
    """
    handles all tests for main.
    """

    @patch("main.GITHUB_REPOSITORY", None)
    @patch("main.GITHUB_TOKEN", "test_token")
    def test_main_no_GITHUB_REPOSITORY(self, capsys: "Any") -> "None":
        # should log error and return without raising exception
        main()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", None)
    def test_main_no_github_token(self, capsys: "Any") -> "None":
        # should log error and return without raising exception
        main()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_no_plugins_found(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = []
        mock_loader_class.return_value = mock_loader

        main()

        mock_loader.load_rhdh_plugins.assert_called_once()

    @pytest.mark.parametrize("strategy", ["separate", "grouped"])
    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_with_plugins_up_to_date(
        self,
        mock_updater_class: "Any",
        mock_loader_class: "Any",
        mock_api_class: "Any",
        strategy: "str",
    ) -> "None":
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        mock_package = RHDHPluginPackage(
            name="test-package",
            versions=[
                RHDHPluginPackageVersion(
                    name="12345",
                    version=Version("1.0.0"),
                    created_at="2024-01-15T10:00:00Z",
                )
            ],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api_class.return_value = mock_api

        with patch("main.UPDATE_PR_STRATEGY", strategy):
            main()

        mock_loader.load_rhdh_plugins.assert_called_once()
        mock_api.fetch_package.assert_called_once_with(
            "test-package", tag_prefix_filter=None
        )
        # no pr should be created
        mock_api.create_pull_request.assert_not_called()

        mock_api._branch_exists.assert_not_called()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.GITHUB_REF", "main")
    @patch(
        "main.DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH",
        "dynamic-plugins.yaml",
    )
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_with_plugin_update_separate_strategy(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        mock_package = RHDHPluginPackage(
            name="test-package",
            versions=[
                RHDHPluginPackageVersion(
                    name="12345",
                    version=Version("1.0.0"),
                    created_at="2024-01-15T10:00:00Z",
                ),
                RHDHPluginPackageVersion(
                    name="12346",
                    version=Version("1.1.0"),
                    created_at="2024-01-20T10:00:00Z",
                ),
            ],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api.create_pull_request.return_value = (
            "https://github.com/owner/repo/pull/1"
        )
        mock_api_class.return_value = mock_api

        mock_updater = Mock()
        mock_updater.update_rhdh_plugin.return_value = "updated yaml content"
        mock_updater_class.return_value = mock_updater

        main()

        mock_loader.load_rhdh_plugins.assert_called_once()
        mock_api.fetch_package.assert_called_once_with(
            "test-package", tag_prefix_filter=None
        )
        mock_updater.update_rhdh_plugin.assert_called_once_with(
            mock_plugin, Version("1.1.0"), None
        )
        mock_api.create_pull_request.assert_called_once()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.GITHUB_REF", "main")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.JOINT)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_with_plugin_update_joint_strategy(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin1 = RHDHPlugin(
            package_name="test-package-1",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin-1",
            disabled=False,
        )
        mock_plugin2 = RHDHPlugin(
            package_name="test-package-2",
            current_version=Version("2.0.0"),
            plugin_name="test-plugin-2",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin1, mock_plugin2]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()

        def fetch_package_side_effect(
            package_name: "str", tag_prefix_filter: "str | None" = None
        ) -> "RHDHPluginPackage":
            if package_name == "test-package-1":
                return RHDHPluginPackage(
                    name="test-package-1",
                    versions=[
                        RHDHPluginPackageVersion(
                            name="12345",
                            version=Version("1.0.0"),
                            created_at="2024-01-15T10:00:00Z",
                        ),
                        RHDHPluginPackageVersion(
                            name="12346",
                            version=Version("1.1.0"),
                            created_at="2024-01-20T10:00:00Z",
                        ),
                    ],
                )
            return RHDHPluginPackage(
                name="test-package-2",
                versions=[
                    RHDHPluginPackageVersion(
                        name="22345",
                        version=Version("2.0.0"),
                        created_at="2024-01-15T10:00:00Z",
                    ),
                    RHDHPluginPackageVersion(
                        name="22346",
                        version=Version("2.1.0"),
                        created_at="2024-01-20T10:00:00Z",
                    ),
                ],
            )

        mock_api.fetch_package.side_effect = fetch_package_side_effect
        mock_api.create_pull_request.return_value = (
            "https://github.com/owner/repo/pull/1"
        )
        mock_api_class.return_value = mock_api

        mock_updater = Mock()
        mock_updater.bulk_update_rhdh_plugins.return_value = "updated yaml content"
        mock_updater_class.return_value = mock_updater

        main()

        mock_loader.load_rhdh_plugins.assert_called_once()
        assert mock_api.fetch_package.call_count == 2
        # Should create a single joint PR
        mock_updater.bulk_update_rhdh_plugins.assert_called_once()
        mock_api.create_pull_request.assert_called_once()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 1)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_respects_pr_creation_limit(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin1 = RHDHPlugin(
            package_name="test-package-1",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin-1",
            disabled=False,
        )
        mock_plugin2 = RHDHPlugin(
            package_name="test-package-2",
            current_version=Version("2.0.0"),
            plugin_name="test-plugin-2",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin1, mock_plugin2]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()

        def fetch_package_side_effect(
            package_name: "str", tag_prefix_filter: "str | None" = None
        ) -> "RHDHPluginPackage":
            if package_name == "test-package-1":
                return RHDHPluginPackage(
                    name="test-package-1",
                    versions=[
                        RHDHPluginPackageVersion(
                            name="12346",
                            version=Version("1.1.0"),
                            created_at="2024-01-20T10:00:00Z",
                        ),
                    ],
                )
            return RHDHPluginPackage(
                name="test-package-2",
                versions=[
                    RHDHPluginPackageVersion(
                        name="22346",
                        version=Version("2.1.0"),
                        created_at="2024-01-20T10:00:00Z",
                    ),
                ],
            )

        mock_api.fetch_package.side_effect = fetch_package_side_effect
        mock_api.create_pull_request.return_value = (
            "https://github.com/owner/repo/pull/1"
        )
        mock_api_class.return_value = mock_api

        mock_updater = Mock()
        mock_updater.update_rhdh_plugin.return_value = "updated yaml content"
        mock_updater_class.return_value = mock_updater

        main()

        # should only create 1 PR due to limit
        assert mock_api.create_pull_request.call_count == 1

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_handles_pr_creation_failure(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        mock_package = RHDHPluginPackage(
            name="test-package",
            versions=[
                RHDHPluginPackageVersion(
                    name="12346",
                    version=Version("1.1.0"),
                    created_at="2024-01-20T10:00:00Z",
                ),
            ],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api.create_pull_request.side_effect = GithubPRFailedException(
            "Branch already exists"
        )
        mock_api_class.return_value = mock_api

        mock_updater = Mock()
        mock_updater.update_rhdh_plugin.return_value = "updated yaml content"
        mock_updater_class.return_value = mock_updater

        # should not raise exception
        main()

        mock_api.create_pull_request.assert_called_once()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.JOINT)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_exits_on_joint_pr_failure(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        mock_package = RHDHPluginPackage(
            name="test-package",
            versions=[
                RHDHPluginPackageVersion(
                    name="12346",
                    version=Version("1.1.0"),
                    created_at="2024-01-20T10:00:00Z",
                ),
            ],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api.create_pull_request.side_effect = GithubPRFailedException(
            "Failed to create PR"
        )
        mock_api_class.return_value = mock_api

        mock_updater = Mock()
        mock_updater.bulk_update_rhdh_plugins.return_value = "updated yaml content"
        mock_updater_class.return_value = mock_updater

        # should exit with code 1
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_skips_packages_without_versions(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        mock_package = RHDHPluginPackage(
            # no versions
            name="test-package",
            versions=[],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api_class.return_value = mock_api

        mock_updater = Mock()
        mock_updater_class.return_value = mock_updater

        main()

        mock_loader.load_rhdh_plugins.assert_called_once()
        mock_api.fetch_package.assert_called_once()

        # no updates should be attempted
        mock_updater.update_rhdh_plugin.assert_not_called()
        mock_api.create_pull_request.assert_not_called()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_filters_by_current_tag_prefix(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        """Test that plugins are fetched with their specific tag prefix filter"""
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
            current_tag_prefix="next__",
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        # Package has both next__ and stable__ versions, but should only return next__
        mock_package = RHDHPluginPackage(
            name="test-package",
            versions=[
                RHDHPluginPackageVersion(
                    name="12345",
                    version=Version("1.0.0"),
                    created_at="2024-01-15T10:00:00Z",
                )
            ],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api_class.return_value = mock_api

        main()

        mock_loader.load_rhdh_plugins.assert_called_once()
        # Verify fetch_package was called with the tag_prefix_filter
        mock_api.fetch_package.assert_called_once_with(
            "test-package", tag_prefix_filter="next__"
        )

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_prevents_cross_prefix_comparison(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin = RHDHPlugin(
            package_name="test-package",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin",
            disabled=False,
            current_tag_prefix="next__",
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()
        mock_package = RHDHPluginPackage(
            name="test-package",
            versions=[
                RHDHPluginPackageVersion(
                    name="12345",
                    version=Version("1.0.0"),  # current version
                    created_at="2024-01-15T10:00:00Z",
                )
            ],
        )
        mock_api.fetch_package.return_value = mock_package
        mock_api_class.return_value = mock_api

        main()

        mock_api.create_pull_request.assert_not_called()

    @patch("main.GITHUB_REPOSITORY", "owner/repo")
    @patch("main.GITHUB_TOKEN", "test_token")
    @patch("main.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.SEPARATE)
    @patch("main.PR_CREATION_LIMIT", 0)
    @patch("main.GithubAPIClient")
    @patch("main.RHDHPluginsConfigLoader")
    @patch("main.RHDHPluginConfigUpdater")
    def test_main_uses_different_prefixes_for_different_plugins(
        self, mock_updater_class: "Any", mock_loader_class: "Any", mock_api_class: "Any"
    ) -> "None":
        mock_plugin1 = RHDHPlugin(
            package_name="test-package-1",
            current_version=Version("1.0.0"),
            plugin_name="test-plugin-1",
            disabled=False,
            current_tag_prefix="next__",
        )
        mock_plugin2 = RHDHPlugin(
            package_name="test-package-2",
            current_version=Version("2.0.0"),
            plugin_name="test-plugin-2",
            disabled=False,
            current_tag_prefix="stable__",
        )

        mock_loader = Mock()
        mock_loader.load_rhdh_plugins.return_value = [mock_plugin1, mock_plugin2]
        mock_loader_class.return_value = mock_loader

        mock_api = Mock()

        def fetch_package_side_effect(
            package_name: "str", tag_prefix_filter: "str | None" = None
        ) -> "RHDHPluginPackage":
            if package_name == "test-package-1":
                return RHDHPluginPackage(
                    name="test-package-1",
                    versions=[
                        RHDHPluginPackageVersion(
                            name="12345",
                            version=Version("1.0.0"),
                            created_at="2024-01-15T10:00:00Z",
                        )
                    ],
                )
            return RHDHPluginPackage(
                name="test-package-2",
                versions=[
                    RHDHPluginPackageVersion(
                        name="22345",
                        version=Version("2.0.0"),
                        created_at="2024-01-15T10:00:00Z",
                    )
                ],
            )

        mock_api.fetch_package.side_effect = fetch_package_side_effect
        mock_api_class.return_value = mock_api

        main()

        assert mock_api.fetch_package.call_count == 2
        mock_api.fetch_package.assert_any_call(
            "test-package-1", tag_prefix_filter="next__"
        )
        mock_api.fetch_package.assert_any_call(
            "test-package-2", tag_prefix_filter="stable__"
        )

    def test_main_grouped_pair_and_unrelated_update_are_isolated(
        self, monkeypatch: "Any", tmp_path: "Any"
    ) -> "None":
        package_root = "rhdh-plugin-export-overlays/"
        versions = [
            ("pluginabc", "1.45.3__1.2.3", "1.45.3__1.2.4", "bs_"),
            ("pluginabc-backend", "1.44.0__0.9.0", "1.46.0__1.2.5", "bs_"),
            ("pluginxyz", "9.0.0", "9.0.1", "next__"),
        ]
        items = [
            _plugin_and_package(package_root + name, name, current, target, prefix)
            for name, current, target, prefix in versions
        ]
        original = "plugins:\n  # preserve this comment\n" + "".join(
            f"  - package: oci://ghcr.io/redhat-developer/{package_root}"
            f"{name}:{prefix}{current}\n"
            for name, current, _, prefix in versions
        )
        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(original)
        api, _ = _configure_grouped_main(
            monkeypatch,
            items,
            config_path=str(config_path),
        )
        monkeypatch.setattr(
            RHDHPluginUpdaterConfig, "GH_PACKAGE_TAG_PREFIX", ["next__", "bs_"]
        )
        monkeypatch.setattr(
            "main.RHDHPluginConfigUpdater",
            lambda: RHDHPluginConfigUpdater(config_path=str(config_path)),
        )

        main()

        calls = [call.kwargs for call in api.create_pull_request.call_args_list]
        assert len(calls) == 2
        pair, singleton = calls
        expected_pair = original
        for name, current, target, prefix in versions[:2]:
            expected_pair = expected_pair.replace(
                f"{name}:{prefix}{current}", f"{name}:{prefix}{target}"
            )
            assert f"**{name}**: `{current}` → `{target}`" in pair["pr_body"]
        assert pair["new_content"] == expected_pair
        assert pair["branch_name"].startswith("update-grouped-pluginabc-")
        assert "pluginabc" in pair["pr_title"]
        assert "2 packages" in pair["pr_title"]
        assert "pluginxyz" not in pair["pr_body"]
        assert singleton["new_content"] == original.replace(
            "pluginxyz:next__9.0.0", "pluginxyz:next__9.0.1"
        )
        assert singleton["branch_name"] == "update-pluginxyz-9.0.1"
        assert singleton["pr_title"] == RHDHPluginUpdaterConfig.GH_PR_TITLE_BASE.format(
            plugin_name="pluginxyz", latest_version="9.0.1"
        )
        assert singleton["pr_body"] == RHDHPluginUpdaterConfig.GH_PR_BODY_BASE.format(
            plugin_name="pluginxyz", current_version="9.0.0", latest_version="9.0.1"
        )
        assert config_path.read_text() == original

    @pytest.mark.parametrize("existing_index", [0, 1])
    def test_main_grouped_does_not_readd_existing_separate_update(
        self,
        monkeypatch: "Any",
        plugin_pair: "Any",
        existing_index: "int",
    ) -> "None":
        api, updater = _configure_grouped_main(monkeypatch, plugin_pair)
        existing_plugin, existing_package = plugin_pair[existing_index]
        remaining_plugin, remaining_package = plugin_pair[1 - existing_index]
        existing_branch = RHDHPluginUpdaterConfig.GH_PR_BRANCH_NAME_BASE.format(
            plugin_name=existing_plugin.plugin_name,
            latest_version=existing_package.versions[0].version,
        )
        api._branch_exists.side_effect = (
            lambda _repo, branch, *, strict: branch == existing_branch
        )

        main()

        updater.bulk_update_rhdh_plugins.assert_called_once()
        remaining = updater.bulk_update_rhdh_plugins.call_args.args[0]
        assert [update.rhdh_plugin for update in remaining] == [remaining_plugin]
        assert api.create_pull_request.call_count == 1
        assert api.create_pull_request.call_args.kwargs["branch_name"] == (
            f"update-{remaining_plugin.plugin_name}-{remaining_package.versions[0].version}"
        )

    def test_main_grouped_branch_lookup_failure_creates_no_prs(
        self, monkeypatch: "Any", plugin_pair: "Any", github_client: "GithubAPIClient"
    ) -> "None":
        api, updater = _configure_grouped_main(monkeypatch, plugin_pair)
        github_client.fetch_package = api.fetch_package
        github_client.create_pull_request = api.create_pull_request
        repo = Mock()
        repo.get_git_ref.side_effect = GithubException(
            500, {"message": "lookup failed"}
        )
        github_client.client.get_repo.return_value = repo
        monkeypatch.setattr("main.GithubAPIClient", Mock(return_value=github_client))

        with pytest.raises(GithubException, match="lookup failed"):
            main()

        api.create_pull_request.assert_not_called()
        updater.bulk_update_rhdh_plugins.assert_not_called()

    @pytest.mark.parametrize("creation_fails", [False, True])
    def test_main_grouped_limit_counts_successful_prs_and_keeps_pairs_together(
        self, monkeypatch: "Any", plugin_pair: "Any", creation_fails: "bool"
    ) -> "None":
        unrelated = _plugin_and_package(
            "scope/pluginxyz", "pluginxyz", "4.0.0", "4.1.0"
        )
        api, updater = _configure_grouped_main(
            monkeypatch, [*plugin_pair, unrelated], pr_creation_limit=1
        )
        if creation_fails:
            api.create_pull_request.side_effect = [
                GithubPRFailedException("temporary failure"),
                "https://github.com/owner/repo/pull/2",
            ]

        main()

        expected_attempts = 2 if creation_fails else 1
        assert api.create_pull_request.call_count == expected_attempts
        assert updater.bulk_update_rhdh_plugins.call_count == expected_attempts
        updates = updater.bulk_update_rhdh_plugins.call_args_list[0].args[0]
        assert [update.rhdh_plugin for update in updates] == [
            plugin for plugin, _ in plugin_pair
        ]
        if creation_fails:
            assert api.create_pull_request.call_args.kwargs["branch_name"] == (
                "update-pluginxyz-4.1.0"
            )

    def test_main_grouped_discovery_failure_creates_no_prs(
        self, monkeypatch: "Any", plugin_pair: "Any"
    ) -> "None":
        api, updater = _configure_grouped_main(monkeypatch, plugin_pair)
        api.fetch_package.side_effect = [
            plugin_pair[0][1],
            RuntimeError("package lookup failed"),
        ]

        with pytest.raises(RuntimeError, match="package lookup failed"):
            main()

        api.create_pull_request.assert_not_called()
        api._branch_exists.assert_not_called()
        updater.bulk_update_rhdh_plugins.assert_not_called()

    def test_main_grouped_skips_packages_without_versions(
        self, monkeypatch: "Any", plugin_pair: "Any"
    ) -> "None":
        plugin_pair[0][1].versions = []
        api, updater = _configure_grouped_main(monkeypatch, plugin_pair)

        main()

        assert api.create_pull_request.call_count == 1
        updates = updater.bulk_update_rhdh_plugins.call_args.args[0]
        assert [update.rhdh_plugin for update in updates] == [plugin_pair[1][0]]

    def test_grouped_hash_tracks_update_identity_and_ignores_input_order(
        self, plugin_pair: "Any"
    ) -> "None":
        updates = [
            RHDHPluginUpdate(plugin, package.versions[0].version)
            for plugin, package in plugin_pair
        ]
        fingerprint = partial(
            _grouped_update_hash, base_branch="main", config_path="dynamic-plugins.yaml"
        )
        original = fingerprint(updates)
        assert fingerprint(updates[::-1]) == original
        assert fingerprint(updates, config_path="overlays/plugins.yaml") != original
        assert fingerprint(updates, base_branch="release-1.0") != original

        frontend, backend = updates
        fingerprints = {original}
        for changed in [
            replace(frontend, new_version=Version("1.2.0")),
            replace(frontend, new_second_version=Version("5.1.0")),
            replace(frontend, new_second_version=Version("5.2.0")),
            replace(
                frontend,
                rhdh_plugin=replace(frontend.rhdh_plugin, current_tag_prefix="bs_"),
            ),
        ]:
            fingerprints.add(fingerprint([changed, backend]))
        assert len(fingerprints) == 5
        repeated_package = replace(
            frontend,
            rhdh_plugin=replace(frontend.rhdh_plugin, plugin_name="another-alias"),
        )
        repeated_updates = [*updates, repeated_package]
        assert fingerprint(repeated_updates) != original
        assert fingerprint(repeated_updates[::-1]) == fingerprint(repeated_updates)
