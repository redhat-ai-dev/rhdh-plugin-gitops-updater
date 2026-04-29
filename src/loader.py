from urllib.parse import urlparse

import yaml
from packaging.version import Version

from src.constants import (
    DYNAMIC_PLUGINS_CONFIG_YAML_EXTRA_LOCATIONS,
    DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH,
    DYNAMIC_PLUGINS_CONFIG_YAML_LOCATION,
    logger,
)
from src.exceptions import InvalidRHDHPluginPackageDefinitionException
from src.types import RHDHPlugin, RHDHPluginUpdaterConfig
from src.utils import get_plugins_list_from_dict, match_tag_prefix, parse_dual_version


class RHDHPluginsConfigLoader:
    """
    Handles RHDH app-config and dynamic plugins config parsing and updates
    """

    def __init__(
        self,
        config_path=DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH,
        config_location=DYNAMIC_PLUGINS_CONFIG_YAML_LOCATION,
        extra_config_locations=None,
    ) -> "None":
        self.config_path = config_path
        self.config_location = config_location
        self.extra_config_locations = (
            extra_config_locations
            if extra_config_locations is not None
            else DYNAMIC_PLUGINS_CONFIG_YAML_EXTRA_LOCATIONS
        )

    def _fetch_plugins_by_location(
        self,
        data: "dict[str, str | int | bool]",
        location: "str | None" = None,
        strict: "bool" = True,
    ) -> "list[dict[str, str | int | bool]]":
        """
        fetches the plugins from the config file based on the config location
        """
        keys = (location if location is not None else self.config_location).split(".")
        plugins_list = get_plugins_list_from_dict(keys, data, strict=strict)

        return plugins_list if isinstance(plugins_list, list) else []

    def _parse_package_string(
        self, package: "str"
    ) -> "dict[str, str | Version | None]":
        """
        parses the OCI package string to extract plugin info.

        ::raises:: InvalidRHDHPluginPackageDefinitionException
        If the package definition is invalid

        ::raises:: ImageTagNotFoundException if the image tag is not found
        """
        if not package.startswith("oci://"):
            raise InvalidRHDHPluginPackageDefinitionException(
                f"Invalid RHDH plugin package definition: {package}"
            )

        # remove the oci:// prefix
        package = package.replace("oci://", "", 1)

        # split image ref and plugin name (! suffix is optional)
        if "!" in package:
            image_ref, plugin_name = package.split("!", 1)
        else:
            image_ref = package
            plugin_name = None

        # parse the image ref
        parsed_url = urlparse(f"//{image_ref}")
        image_ref_parts = parsed_url.path.lstrip("/").split("/")

        # should have less than 4 parts (registry, org, repo, name:version)
        if not len(image_ref_parts) < 4:
            raise InvalidRHDHPluginPackageDefinitionException(
                f"Too few image ref parts ({len(image_ref_parts)}) "
                f"for package: {package}"
            )

        # get name and version
        name_and_version = image_ref_parts[-1]

        if ":" not in name_and_version:
            raise InvalidRHDHPluginPackageDefinitionException(
                f"Tag not found for package {package}"
            )

        name, raw_version = name_and_version.rsplit(":", 1)

        matched_prefix = match_tag_prefix(raw_version)
        if not matched_prefix:
            raise InvalidRHDHPluginPackageDefinitionException(
                f"Tag {raw_version} not valid for package {package}"
            )

        # remove prefix and parse potential dual version
        version_string = raw_version.replace(matched_prefix, "")
        version, second_version = parse_dual_version(version_string)

        package_name = f"rhdh-plugin-export-overlays/{name}"

        # if plugin_name was not provided via !, derive from image name
        if plugin_name is None:
            plugin_name = name

        return {
            "package_name": package_name,
            "version": version,
            "second_version": second_version,
            "plugin_name": plugin_name,
            "tag_prefix": matched_prefix,
        }

    def _convert_rhdhplugin_list(
        self, plugins_list: "list[dict[str, str | int | bool]]"
    ) -> "list[RHDHPlugin]":
        """
        converts a list of plugin dicts into a list of RHDHPlugin objects
        """
        rhdh_plugins = []
        for plugin_entry in plugins_list:
            package = str(plugin_entry.get("package", ""))
            disabled = bool(plugin_entry.get("disabled", False))

            # continue if is not an RHDH plugin or is disabled
            if not package.startswith(RHDHPluginUpdaterConfig.GH_CR_REGISTRY_PREFIX):
                logger.info(f"skipping plugin {package} as it's not RHDH Plugin")
                continue

            if disabled is True:
                logger.info(f"skipping plugin {package} as it's disabled")
                continue

            try:
                parsed = self._parse_package_string(package)
            except InvalidRHDHPluginPackageDefinitionException as e:
                logger.warning(f"failed to parse package:: {e}")
                continue

            if len(parsed.keys()) == 0:
                continue

            rhdh_plugins.append(
                RHDHPlugin(
                    package_name=str(parsed["package_name"]),
                    current_version=parsed["version"],  # type: ignore
                    plugin_name=str(parsed["plugin_name"]),
                    disabled=disabled,
                    current_second_version=parsed.get("second_version"),  # type: ignore
                    current_tag_prefix=str(parsed.get("tag_prefix", "")),
                )
            )
        return rhdh_plugins

    def load_rhdh_plugins(self) -> "list[RHDHPlugin]":
        """
        parses the config file and extracts RHDH plugins list.
        """
        logger.debug("loading RHDH plugins from config...")
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)

        all_plugins_list = self._fetch_plugins_by_location(data, strict=False)
        for extra_location in self.extra_config_locations:
            all_plugins_list.extend(
                self._fetch_plugins_by_location(data, extra_location, strict=False)
            )

        rhdh_plugins = self._convert_rhdhplugin_list(all_plugins_list)
        return rhdh_plugins
