from dataclasses import dataclass

from packaging.version import Version

from src.constants import GH_PACKAGE_TAG_PREFIXES


class GithubPullRequestStrategy:
    SEPARATE = "separate"
    JOINT = "joint"
    GROUPED = "grouped"


@dataclass
class RHDHPluginPackageVersion:
    name: "str"
    version: "Version"
    created_at: "str"
    second_version: "Version | None" = None


@dataclass
class RHDHPluginPackage:
    """
    Represents the RHDH plugin github package with its versions.
    """

    name: "str"
    versions: "list[RHDHPluginPackageVersion]"


@dataclass
class RHDHPlugin:
    """
    Represents an RHDH plugin from the dynamic plugins configuration.
    """

    package_name: "str"
    current_version: "Version"
    plugin_name: "str"
    disabled: "bool"
    current_second_version: "Version | None" = None
    current_tag_prefix: "str | None" = None


@dataclass
class RHDHPluginUpdate:
    """
    Represents an update for an RHDH plugin.
    """

    rhdh_plugin: "RHDHPlugin"
    new_version: "Version"
    new_second_version: "Version | None" = None


class RHDHPluginUpdaterConfig:
    GH_ORG_NAME = "redhat-developer"
    GH_REPO_NAME = "rhdh-plugin-export-overlays"
    GH_PACKAGE_TAG_PREFIX = GH_PACKAGE_TAG_PREFIXES
    GH_PACKAGES_BASE_URL = "https://api.github.com/orgs/{org}/packages"
    GH_PACKAGES_VERSION_BASE_URL = "https://api.github.com/orgs/{org}/packages/{package_type}/{package_name}/versions"
    GH_RUNNER_PREFIX = "/github/workspace/"
    GH_CR_REGISTRY_PREFIX = (
        "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/"
    )
    GH_PR_BRANCH_NAME_BASE = "update-{plugin_name}-{latest_version}"
    GH_PR_TITLE_BASE = (
        "chore(`rhdh-plugin-gitops-updater`) Update `{plugin_name}` "
        "to version `{latest_version}`"
    )
    GH_GROUPED_PR_BRANCH_NAME_BASE = "update-grouped-{plugin_name}-{update_hash}"
    GH_GROUPED_PR_TITLE_BASE = (
        "chore(`rhdh-plugin-gitops-updater`) Update `{plugin_name}` "
        "({plugin_updates_count} packages)"
    )
    GH_PR_BODY_BASE = """## Plugin Update

**Plugin**: `{plugin_name}`
**Current Version**: `{current_version}`
**New Version**: `{latest_version}`

This PR updates the RHDH plugin to the latest version.

🤖 Generated with [RHDH Plugin GitOps Updater](https://github.com/thepetk/rhdh-plugin-gitops-updater)
"""
    GH_BULK_PR_BRANCH_NAME_BASE = "update-rhdh-plugins-batch"
    GH_BULK_PR_TITLE_BASE = (
        "chore(`rhdh-plugin-gitops-updater`) Update {plugin_updates_count} RHDH plugins"
    )
    GH_BULK_PR_BODY_BASE = """## Batch Plugin Update

This PR updates {plugin_updates_count} RHDH plugins to their latest versions:

"""
