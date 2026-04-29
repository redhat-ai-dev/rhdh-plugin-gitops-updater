import sys
from typing import Any

from packaging.version import Version

from src.constants import logger
from src.types import RHDHPluginUpdaterConfig


def get_plugins_list_from_dict(
    keys: "list[str]", data: "dict[str, Any]", strict: "bool" = True
) -> "list[dict[str, Any]]":
    """
    navigates through a nested dictionary using a list of keys.
    """
    current: "dict[str, Any]" = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            if strict:
                logger.error("invalid config location, cannot find plugins list")
                sys.exit(1)
            return []

        current = current[key]

    return [] if not isinstance(current, list) else current


def parse_dual_version(version_string: "str") -> "tuple[Version, Version | None]":
    """
    parses a version string that may contain dual versions separated by '__'.
    """
    if "__" in version_string:
        parts = version_string.split("__", 1)
        if len(parts) == 2 and parts[1]:
            return (Version(parts[0]), Version(parts[1]))

    # single version or invalid dual version
    return (Version(version_string.split("__")[0]), None)


def compare_versions(
    version1: "Version",
    version2: "Version",
    secondary1: "Version | None" = None,
    secondary2: "Version | None" = None,
) -> "int":
    """
    compares two versions with optional secondary versions
    """
    # compare primary versions
    if version1 < version2:
        return -1
    if version1 > version2:
        return 1

    # primary versions are equal, compare secondary versions
    if secondary1 is None and secondary2 is None:
        return 0

    if secondary1 is None:
        return -1  # version2 has secondary, so it's greater

    if secondary2 is None:
        return 1  # version1 has secondary, so it's greater

    # both have secondary versions
    if secondary1 < secondary2:
        return -1
    if secondary1 > secondary2:
        return 1

    return 0


def rhdh_plugin_needs_update(
    latest_version: "Version",
    current_version: "Version",
    latest_secondary: "Version | None" = None,
    current_secondary: "Version | None" = None,
) -> "bool":
    """
    checks if the latest version is greater than the current version.
    supports dual versions with optional secondary version components.
    """
    return (
        compare_versions(
            latest_version, current_version, latest_secondary, current_secondary
        )
        > 0
    )


def build_version_string(
    version: "Version", second_version: "Version | None" = None
) -> "str":
    """
    builds a version string, including second version if present
    """
    if second_version:
        return f"{version}__{second_version}"
    return str(version)


def match_tag_prefix(tag: "str") -> "str | None":
    """
    checks if a tag starts with any of the configured prefixes
    and returns the matched prefix, or None if no match
    """
    for prefix in RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX:
        if tag.startswith(prefix):
            return prefix
    return None
