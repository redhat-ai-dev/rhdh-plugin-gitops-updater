from typing import Any
from urllib.parse import quote

import requests
from github import Auth, Github
from github.ContentFile import ContentFile
from github.Repository import Repository
from requests import Response

from src.constants import GITHUB_REF, UPDATE_PR_STRATEGY, logger
from src.exceptions import GithubPRFailedException
from src.types import (
    GithubPullRequestStrategy,
    RHDHPluginPackage,
    RHDHPluginPackageVersion,
    RHDHPluginUpdaterConfig,
)
from src.utils import match_tag_prefix, parse_dual_version


class GithubAPIClient:
    """
    Handles all GitHub-related operations.
    """

    def __init__(self, token: "str", per_page=100) -> "None":
        self.token = token
        self.per_page = per_page

        self.client = Github(auth=Auth.Token(token))

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _fetch_next(
        self, response: "Response", url: "str", params: "dict[str, str | int]"
    ) -> "tuple[str, dict[str, str | int]]":
        """
        extracts the next URL from the response links if available
        """
        if "next" not in response.links:
            return "", params

        # params unset as the next URL already contains query params
        params = {}
        url = response.links["next"]["url"]

        return url, params

    def _paginate(
        self, url: "str", extra_params: "dict[str, str] | None" = None
    ) -> "list[dict[str, Any]]":
        """
        handles pagination for GitHub API requests

        ::raises:: requests.HTTPError If the API request fails
        """
        items: "list[dict[str, Any]]" = []
        params: "dict[str, str | int]" = {
            "per_page": self.per_page,
        }

        if extra_params:
            params.update(extra_params)

        while url:
            logger.debug(f"fetching (GET) {url}")
            response = self._session.get(url, params=params)
            response.raise_for_status()

            resp_items = response.json()
            items.extend(resp_items)

            # handle pagination case
            url, params = self._fetch_next(response, url, params)
        return items

    def _convert_to_rhdh_plugin_package(
        self,
        package_name: "str",
        raw_versions: "list[dict[str, Any]]",
        tag_prefix_filter: "str | None" = None,
    ) -> "RHDHPluginPackage":
        """
        converts a list of package versions into an RHDHPluginPackage
        """
        versions = []
        for v in raw_versions:
            metadata = v.get("metadata")
            if not isinstance(metadata, dict):
                continue

            container = metadata.get("container")
            if not isinstance(container, dict):
                continue

            tags = container.get("tags")
            if not isinstance(tags, list) or not tags:
                continue

            tag = str(tags[0])
            matched_prefix = match_tag_prefix(tag)
            if not matched_prefix:
                continue

            if tag_prefix_filter and matched_prefix != tag_prefix_filter:
                logger.debug(
                    f"skipping version {tag} for package {package_name} "
                    f"(prefix {matched_prefix} != {tag_prefix_filter})"
                )
                continue

            created_at = v.get("created_at")
            if not isinstance(created_at, str):
                continue

            # remove prefix and parse potential dual version
            version_string = tag.replace(matched_prefix, "")
            version, second_version = parse_dual_version(version_string)

            logger.debug(f"found version {tag} for package {package_name}")
            versions.append(
                RHDHPluginPackageVersion(
                    name=str(v.get("name", "")),
                    version=version,
                    created_at=created_at,
                    second_version=second_version,
                )
            )

        return RHDHPluginPackage(name=package_name, versions=versions)

    def fetch_package(
        self,
        package_name: "str",
        org=RHDHPluginUpdaterConfig.GH_ORG_NAME,
        tag_prefix_filter: "str | None" = None,
    ) -> "RHDHPluginPackage":
        """
        fetch the RHDHPluginPackage for the given package name
        """
        # URL-encode the package name to handle slashes
        logger.debug(f"fetching package {package_name}")
        encoded_package_name = quote(package_name, safe="")
        raw_versions = self._paginate(
            url=RHDHPluginUpdaterConfig.GH_PACKAGES_VERSION_BASE_URL.format(
                org=org, package_type="container", package_name=encoded_package_name
            )
        )

        # fallback to package without versions
        if not raw_versions:
            logger.warning(f"no versions found for package {package_name}")
            return RHDHPluginPackage(name=package_name, versions=[])

        return self._convert_to_rhdh_plugin_package(
            package_name, raw_versions, tag_prefix_filter
        )

    def _branch_exists(self, repo: "Repository", branch_name: "str") -> "bool":
        """
        checks if a branch exists in the given repository
        """
        try:
            repo.get_git_ref(f"heads/{branch_name}")
            logger.debug(f"branch {branch_name} already exists")
            return True
        except Exception:
            logger.debug(f"branch {branch_name} does not exist, will create it")
            return False

    def _handle_new_endline(self, original_content: "str", new_content: "str") -> "str":
        """
        handles the new_endline formating issue
        """
        original_ends_with_newline = original_content.endswith("\n")

        if original_ends_with_newline and not new_content.endswith("\n"):
            new_content += "\n"
        elif not original_ends_with_newline and new_content.endswith("\n"):
            new_content = new_content.rstrip("\n")

        return new_content

    def create_pull_request(
        self,
        repo_full_name: "str",
        file_path: "str",
        new_content: "str",
        branch_name: "str",
        pr_title: "str",
        pr_body: "str",
        base_branch=GITHUB_REF,
    ) -> str:
        """
        creates a pull request with file changes.

        ::raises:: GithubPRFailedException: If PR creation fails
        """
        logger.debug(f"creating PR in {repo_full_name} on branch {branch_name}")
        repo = self.client.get_repo(repo_full_name)
        base_ref = repo.get_git_ref(f"heads/{base_branch}")
        base_sha = base_ref.object.sha

        if self._branch_exists(repo, branch_name):
            # skip for separate pr strategy
            if UPDATE_PR_STRATEGY == GithubPullRequestStrategy.SEPARATE:
                logger.debug(f"checking for existing open PR for branch {branch_name}")
                raise GithubPRFailedException(f"Branch {branch_name} already exists")

            # if branch exists, check if there's an open PR for it
            try:
                pulls = repo.get_pulls(
                    state="open",
                    head=f"{repo.owner.login}:{branch_name}",
                    base=base_branch,
                )
            except Exception as e:
                logger.debug(f"no open PR found for branch {branch_name}: {e}")

            for pr in pulls:
                raise GithubPRFailedException(
                    f"Open PR already exists for branch {branch_name}: {pr.html_url}"
                )
        else:
            try:
                repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)
                logger.debug(f"created branch {branch_name}")
            except Exception as e:
                raise GithubPRFailedException(
                    f"Failed to create branch {branch_name}: {e}"
                ) from e

        try:
            contents = repo.get_contents(file_path, ref=branch_name)

            # ensure we have a single ContentFile
            if not isinstance(contents, ContentFile):
                raise GithubPRFailedException(
                    f"Expected a file at {file_path}, "
                    "but got a directory or invalid response"
                )

            logger.debug(f"updating file {file_path} in branch {branch_name}")
            repo.update_file(
                path=file_path,
                message=f"Update {file_path}",
                content=self._handle_new_endline(
                    original_content=contents.decoded_content.decode("utf-8"),
                    new_content=new_content,
                ),
                sha=contents.sha,
                branch=branch_name,
            )
        except Exception as update_error:
            raise GithubPRFailedException(
                f"Failed to update file {file_path}: {update_error}"
            ) from update_error

        try:
            logger.debug(f"opening pull request {pr_title}")
            pr = repo.create_pull(
                title=pr_title, body=pr_body, head=branch_name, base=base_branch
            )
            return pr.html_url
        except Exception as pr_error:
            try:
                logger.warning(
                    f"PR creation failed, attempting to delete branch {branch_name}"
                )
                ref = repo.get_git_ref(f"heads/{branch_name}")
                ref.delete()
                logger.debug(f"deleted branch {branch_name} after PR creation failure")
            except Exception as cleanup_error:
                logger.error(f"failed to cleanup branch {branch_name}: {cleanup_error}")

            raise GithubPRFailedException(
                f"Failed to create PR: {pr_error}"
            ) from pr_error
