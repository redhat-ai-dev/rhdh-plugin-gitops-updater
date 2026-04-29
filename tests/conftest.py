import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import requests
from packaging.version import Version

from src.types import RHDHPlugin


@pytest.fixture
def temp_yaml_file() -> "Any":
    """
    creates a temporary YAML file with sample plugin configuration.
    """
    content = """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:next__0.2.0!red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # clean temp files
    Path(temp_path).unlink()


@pytest.fixture
def sample_plugin() -> "RHDHPlugin":
    """
    creates a sample RHDHPlugin for testing.
    """
    return RHDHPlugin(
        package_name="rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend",
        current_version=Version("0.1.2"),
        plugin_name="backstage-plugin-mcp-actions-backend",
        disabled=False,
    )


@pytest.fixture
def sample_plugin_list() -> "list[RHDHPlugin]":
    """
    creates a list of sample RHDHPlugin instances.
    """
    return [
        RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend",
            current_version=Version("0.1.2"),
            plugin_name="backstage-plugin-mcp-actions-backend",
            disabled=False,
        ),
        RHDHPlugin(
            package_name="rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            current_version=Version("0.2.0"),
            plugin_name="red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
            disabled=False,
        ),
    ]


@pytest.fixture
def sample_config_data() -> "dict[str, Any]":
    """
    creates a sample configuration data structure.
    """
    return {
        "global": {
            "dynamic": {
                "plugins": [
                    {
                        "disabled": False,
                        "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend",
                    },
                    {
                        "disabled": False,
                        "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:next__0.2.0!red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
                    },
                    {
                        "disabled": True,
                        "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/disabled-plugin:next__1.0.0!disabled-plugin",
                    },
                    {
                        "disabled": False,
                        "package": "./dynamic-plugins/dist/local-plugin",
                    },
                ]
            }
        }
    }


@pytest.fixture
def sample_yaml_content() -> "str":
    """
    creates a sample YAML content as a string.
    """
    return """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:next__0.2.0!red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool
"""


@pytest.fixture
def sample_package_versions_data() -> "list[dict[str, Any]]":
    """
    creates a sample package versions data from GitHub API.
    """
    return [
        {
            "name": "12345",
            "metadata": {"container": {"tags": ["next__0.1.2"]}},
            "created_at": "2024-01-15T10:00:00Z",
        },
        {
            "name": "12346",
            "metadata": {"container": {"tags": ["next__0.1.3"]}},
            "created_at": "2024-01-20T10:00:00Z",
        },
        {
            "name": "12347",
            "metadata": {"container": {"tags": ["next__0.2.0"]}},
            "created_at": "2024-01-25T10:00:00Z",
        },
    ]


@pytest.fixture
def mock_github_token() -> "str":
    """
    creates a mock GitHub token for testing.
    """
    return "ghp_test_token_12345"


@pytest.fixture
def temp_config_file(sample_config_data) -> "Any":
    """
    creates a temporary config file for testing with YAML data.
    """
    import yaml

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config_data, f)
        temp_path = f.name

    yield temp_path

    # clean temp files
    Path(temp_path).unlink()


@pytest.fixture
def github_client(mock_github_token) -> "Any":
    """
    creates a GithubAPIClient instance for testing.
    """
    from unittest.mock import patch

    from src.github_api_client import GithubAPIClient

    with patch("src.github_api_client.Github"):
        client = GithubAPIClient(token=mock_github_token)
        return client


@pytest.fixture
def mock_response() -> "Mock":
    """
    creates a mock response object.
    """
    response = Mock(spec=requests.Response)
    response.links = {}
    response.json.return_value = []
    return response


@pytest.fixture
def sample_package_versions() -> "list[dict[str, Any]]":
    """
    creates sample package versions data from GitHub API.
    """
    return [
        {
            "name": "12345",
            "metadata": {"container": {"tags": ["next__0.1.2"]}},
            "created_at": "2024-01-15T10:00:00Z",
        },
        {
            "name": "12346",
            "metadata": {"container": {"tags": ["next__0.1.3"]}},
            "created_at": "2024-01-20T10:00:00Z",
        },
        {
            "name": "12347",
            "metadata": {"container": {"tags": ["v1.0.0"]}},  # Wrong prefix
            "created_at": "2024-01-25T10:00:00Z",
        },
    ]


@pytest.fixture
def sample_yaml_content_with_multiple_prefixes() -> "str":
    """
    creates a sample YAML content with plugins using different tag prefixes.
    """
    return """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:stable__0.2.0!red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/another-plugin:previous__1.0.0!another-plugin
"""


@pytest.fixture
def sample_plugin_with_stable_prefix() -> "RHDHPlugin":
    """
    creates a sample RHDHPlugin with stable__ prefix for testing.
    """
    return RHDHPlugin(
        package_name="rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
        current_version=Version("0.2.0"),
        plugin_name="red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool",
        disabled=False,
    )


@pytest.fixture
def sample_plugin_with_previous_prefix() -> "RHDHPlugin":
    """
    creates a sample RHDHPlugin with previous__ prefix for testing.
    """
    return RHDHPlugin(
        package_name="rhdh-plugin-export-overlays/another-plugin",
        current_version=Version("1.0.0"),
        plugin_name="another-plugin",
        disabled=False,
    )


@pytest.fixture
def sample_yaml_content_without_exclamation() -> "str":
    """
    creates a sample YAML content with plugins using the new format (no ! suffix).
    """
    return """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:next__0.2.0
"""


@pytest.fixture
def temp_yaml_file_without_exclamation() -> "Any":
    """
    creates a temporary YAML file with plugins using the new format (no ! suffix).
    """
    content = """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-software-catalog-mcp-tool:next__0.2.0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # clean temp files
    Path(temp_path).unlink()


@pytest.fixture
def sample_yaml_content_with_dual_versions() -> "str":
    """
    creates a sample YAML content with plugins using dual versions.
    """
    return """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/dual-version-plugin:next__1.42.5__0.1.0!dual-version-plugin
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend
"""


@pytest.fixture
def sample_config_data_with_lightspeed_plugins() -> "dict[str, Any]":
    """
    creates a config with plugins in both global.dynamic.plugins
    and global.lightspeed.plugins.
    """
    return {
        "global": {
            "dynamic": {
                "plugins": [
                    {
                        "disabled": False,
                        "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend",
                    },
                ]
            },
            "lightspeed": {
                "plugins": [
                    {
                        "disabled": False,
                        "package": "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/lightspeed-plugin:next__1.0.0!lightspeed-plugin",
                    },
                ]
            },
        }
    }


@pytest.fixture
def temp_yaml_file_with_lightspeed_plugins() -> "Any":
    """
    creates a temporary YAML file with plugins in both global.dynamic.plugins
    and global.lightspeed.plugins.
    """
    content = """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend
  lightspeed:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/lightspeed-plugin:next__1.0.0!lightspeed-plugin
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    Path(temp_path).unlink()


@pytest.fixture
def temp_yaml_file_lightspeed_only() -> "Any":
    """
    creates a temporary YAML file with plugins only in global.lightspeed.plugins.
    """
    content = """global:
  lightspeed:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/lightspeed-plugin:next__1.0.0!lightspeed-plugin
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    Path(temp_path).unlink()


@pytest.fixture
def temp_yaml_file_with_dual_versions() -> "Any":
    """
    creates a temporary YAML file with dual version plugins for testing.
    """
    content = """global:
  dynamic:
    plugins:
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/dual-version-plugin:next__1.42.5__0.1.0!dual-version-plugin
      - disabled: false
        package: oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:next__0.1.2!backstage-plugin-mcp-actions-backend
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # clean temp files
    Path(temp_path).unlink()
