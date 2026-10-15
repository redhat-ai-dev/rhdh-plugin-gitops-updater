#!/usr/bin/env python3
import hashlib
import json
import sys

from src.constants import (
    DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH,
    GITHUB_REF,
    GITHUB_REPOSITORY,
    GITHUB_TOKEN,
    PR_CREATION_LIMIT,
    UPDATE_PR_STRATEGY,
    logger,
)
from src.exceptions import GithubPRFailedException
from src.github_api_client import GithubAPIClient
from src.loader import RHDHPluginsConfigLoader
from src.types import (
    GithubPullRequestStrategy,
    RHDHPluginUpdate,
    RHDHPluginUpdaterConfig,
)
from src.updater import RHDHPluginConfigUpdater
from src.utils import (
    build_version_string,
    group_plugin_updates,
    rhdh_plugin_needs_update,
)


def _single_plugin_pr_info(
    plugin_name: "str", current_version: "str", latest_version: "str"
) -> "tuple[str, str, str]":
    values = {
        "plugin_name": plugin_name,
        "current_version": current_version,
        "latest_version": latest_version,
    }
    return (
        RHDHPluginUpdaterConfig.GH_PR_BRANCH_NAME_BASE.format(**values),
        RHDHPluginUpdaterConfig.GH_PR_TITLE_BASE.format(**values),
        RHDHPluginUpdaterConfig.GH_PR_BODY_BASE.format(**values),
    )


def _plugin_update_details(updates: "list[RHDHPluginUpdate]") -> "str":
    body = ""
    for update in updates:
        plugin = update.rhdh_plugin
        current = build_version_string(
            plugin.current_version, plugin.current_second_version
        )
        latest = build_version_string(update.new_version, update.new_second_version)
        body += f"- **{plugin.plugin_name}**: `{current}` → `{latest}`\n"
    return body + (
        "\n🤖 Generated with [RHDH Plugin GitOps Updater]"
        "(https://github.com/thepetk/rhdh-plugin-gitops-updater)\n"
    )


def _grouped_update_hash(
    updates: "list[RHDHPluginUpdate]", base_branch: "str", config_path: "str"
) -> "str":
    identities: "list[dict[str, str]]" = [
        {
            "package_name": update.rhdh_plugin.package_name,
            "plugin_name": update.rhdh_plugin.plugin_name,
            "tag_prefix": update.rhdh_plugin.current_tag_prefix or "",
            "new_version": str(update.new_version),
            "new_second_version": (
                str(update.new_second_version) if update.new_second_version else ""
            ),
        }
        for update in updates
    ]
    identity = {
        "updates": sorted(identities, key=lambda item: tuple(item.values())),
        "base_branch": base_branch,
        "config_path": config_path,
    }
    encoded_identity = json.dumps(
        identity, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded_identity).hexdigest()[:10]


def _create_grouped_pull_requests(
    gh_api_client: "GithubAPIClient",
    rhdh_config_updater: "RHDHPluginConfigUpdater",
    plugin_updates: "list[RHDHPluginUpdate]",
    trimmed_file_path: "str",
) -> "int":
    repo = gh_api_client.client.get_repo(GITHUB_REPOSITORY)
    eligible_updates: "list[RHDHPluginUpdate]" = []
    for update in plugin_updates:
        plugin = update.rhdh_plugin
        latest_version_string = build_version_string(
            update.new_version, update.new_second_version
        )
        separate_branch_name = RHDHPluginUpdaterConfig.GH_PR_BRANCH_NAME_BASE.format(
            plugin_name=plugin.plugin_name,
            latest_version=latest_version_string,
        )
        # Only a confirmed 404 means absent here: lookup errors must not duplicate
        # an existing individual update in a new group.
        if not gh_api_client._branch_exists(repo, separate_branch_name, strict=True):
            eligible_updates.append(update)

    groups = group_plugin_updates(eligible_updates)
    prs_created = 0
    for group in groups:
        if PR_CREATION_LIMIT > 0 and prs_created >= PR_CREATION_LIMIT:
            logger.warning(
                f"reached the PR creation limit of {PR_CREATION_LIMIT}, stopping..."
            )
            break

        try:
            updated_yaml = rhdh_config_updater.bulk_update_rhdh_plugins(group)

            if len(group) == 1:
                update = group[0]
                plugin = update.rhdh_plugin
                current_version_string = build_version_string(
                    plugin.current_version, plugin.current_second_version
                )
                latest_version_string = build_version_string(
                    update.new_version, update.new_second_version
                )
                branch_name, pr_title, pr_body = _single_plugin_pr_info(
                    plugin.plugin_name, current_version_string, latest_version_string
                )
            else:
                package_name = group[0].rhdh_plugin.package_name
                family_name = package_name.removesuffix("-backend").rsplit("/", 1)[-1]
                update_hash = _grouped_update_hash(group, GITHUB_REF, trimmed_file_path)
                branch_name = (
                    RHDHPluginUpdaterConfig.GH_GROUPED_PR_BRANCH_NAME_BASE.format(
                        plugin_name=family_name,
                        update_hash=update_hash,
                    )
                )
                pr_title = RHDHPluginUpdaterConfig.GH_GROUPED_PR_TITLE_BASE.format(
                    plugin_name=family_name,
                    plugin_updates_count=len(group),
                )
                pr_body = (
                    "## Grouped Plugin Update\n\n"
                    f"This PR updates {len(group)} related RHDH plugin packages "
                    f"for `{family_name}`:\n\n"
                )
                pr_body += _plugin_update_details(group)

            pr_url = gh_api_client.create_pull_request(
                repo_full_name=GITHUB_REPOSITORY,
                file_path=trimmed_file_path,
                new_content=updated_yaml,
                branch_name=branch_name,
                pr_title=pr_title,
                pr_body=pr_body,
                base_branch=GITHUB_REF,
            )
            prs_created += 1
            logger.info(f"✓ Created grouped PR: {pr_url}")

        except GithubPRFailedException as e:
            logger.warning(f"✗ Failed to create grouped PR: {e}")

    return prs_created


def main():
    if not GITHUB_REPOSITORY:
        logger.error("Error: GITHUB_REPOSITORY environment variable is required")
        return

    if not GITHUB_TOKEN:
        logger.error("Error: GITHUB_TOKEN environment variable is required")
        return

    gh_api_client = GithubAPIClient(token=GITHUB_TOKEN)
    rhdh_config_loader = RHDHPluginsConfigLoader()
    rhdh_config_updater = RHDHPluginConfigUpdater()
    rhdh_plugins = rhdh_config_loader.load_rhdh_plugins()
    trimmed_file_path = DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH.replace(
        RHDHPluginUpdaterConfig.GH_RUNNER_PREFIX, ""
    )

    logger.info(f"found {len(rhdh_plugins)} RHDH plugins to check for updates")

    # list to cache updates for joint and grouped strategies
    plugin_updates: "list[RHDHPluginUpdate]" = []
    prs_created = 0

    for plugin in rhdh_plugins:
        logger.info(f"Processing plugin: {plugin.plugin_name}")

        package = gh_api_client.fetch_package(
            plugin.package_name, tag_prefix_filter=plugin.current_tag_prefix
        )
        if not package.versions:
            logger.warning(
                f"no versions found for package {plugin.package_name}, skipping..."
            )
            continue

        # sort by version, considering dual versions
        latest_package_version = sorted(
            package.versions, key=lambda v: (v.version, v.second_version or "")
        )[-1]
        latest_version = latest_package_version.version
        latest_second_version = latest_package_version.second_version

        if not rhdh_plugin_needs_update(
            latest_version,
            plugin.current_version,
            latest_second_version,
            plugin.current_second_version,
        ):
            logger.info(
                f"plugin {plugin.plugin_name} is up-to-date "
                f"(version: {plugin.current_version})"
            )
            continue

        latest_version_string = build_version_string(
            latest_version, latest_second_version
        )
        current_version_string = build_version_string(
            plugin.current_version, plugin.current_second_version
        )

        logger.info(
            f"newer version found for plugin {plugin.plugin_name}: "
            f"{latest_version_string} (current: {current_version_string})"
        )

        if UPDATE_PR_STRATEGY in (
            GithubPullRequestStrategy.JOINT,
            GithubPullRequestStrategy.GROUPED,
        ):
            logger.debug("caching plugin update for deferred PR creation...")
            plugin_updates.append(
                RHDHPluginUpdate(
                    rhdh_plugin=plugin,
                    new_version=latest_version,
                    new_second_version=latest_second_version,
                )
            )
            continue

        if PR_CREATION_LIMIT > 0 and prs_created >= PR_CREATION_LIMIT:
            logger.warning(
                f"reached the PR creation limit of {PR_CREATION_LIMIT}, stopping..."
            )
            break

        try:
            updated_yaml = rhdh_config_updater.update_rhdh_plugin(
                plugin, latest_version, latest_second_version
            )
            branch_name, pr_title, pr_body = _single_plugin_pr_info(
                plugin.plugin_name, current_version_string, latest_version_string
            )

            pr_url = gh_api_client.create_pull_request(
                repo_full_name=GITHUB_REPOSITORY,
                file_path=trimmed_file_path,
                new_content=updated_yaml,
                branch_name=branch_name,
                pr_title=pr_title,
                pr_body=pr_body,
                base_branch=GITHUB_REF,
            )
            logger.info(f"✓ Created PR: {pr_url}")
            prs_created += 1

        except GithubPRFailedException as e:
            logger.warning(f"✗ Failed to create PR for {plugin.plugin_name}: {e}")

    if UPDATE_PR_STRATEGY == GithubPullRequestStrategy.GROUPED and plugin_updates:
        logger.info(f"creating grouped PRs for {len(plugin_updates)} plugin updates...")
        prs_created += _create_grouped_pull_requests(
            gh_api_client,
            rhdh_config_updater,
            plugin_updates,
            trimmed_file_path,
        )

    elif plugin_updates:
        logger.info(f"creating joint PR for {len(plugin_updates)} plugin updates...")
        try:
            updated_yaml = rhdh_config_updater.bulk_update_rhdh_plugins(plugin_updates)

            pr_body = RHDHPluginUpdaterConfig.GH_BULK_PR_BODY_BASE.format(
                plugin_updates_count=len(plugin_updates)
            )
            pr_body += _plugin_update_details(plugin_updates)

            pr_url = gh_api_client.create_pull_request(
                repo_full_name=GITHUB_REPOSITORY,
                file_path=trimmed_file_path,
                new_content=updated_yaml,
                branch_name=RHDHPluginUpdaterConfig.GH_BULK_PR_BRANCH_NAME_BASE,
                pr_title=RHDHPluginUpdaterConfig.GH_BULK_PR_TITLE_BASE.format(
                    plugin_updates_count=len(plugin_updates)
                ),
                pr_body=pr_body,
                base_branch=GITHUB_REF,
            )
            prs_created += 1
            logger.info(f"✓ Created joint PR: {pr_url}")

        except GithubPRFailedException as e:
            logger.error(f"✗ Failed to create joint PR: {e}")
            sys.exit(1)

    logger.info(f"done! Created {prs_created} pull request(s)")


if __name__ == "__main__":
    main()
