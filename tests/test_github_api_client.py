from typing import Any
from unittest.mock import Mock, patch

import pytest
import requests
from github import GithubException
from github.ContentFile import ContentFile
from packaging.version import Version

from src.exceptions import GithubPRFailedException
from src.github_api_client import GithubAPIClient
from src.types import GithubPullRequestStrategy


class TestGithubAPIClientInit:
    """
    handles all tests for GithubAPIClient initialization.
    """

    def test_init_with_default_per_page(self, mock_github_token: "str") -> "None":
        with patch("src.github_api_client.Github"):
            client = GithubAPIClient(token=mock_github_token)
            assert client.token == mock_github_token
            assert client.per_page == 100

    def test_init_with_custom_per_page(self, mock_github_token: "str") -> "None":
        with patch("src.github_api_client.Github"):
            client = GithubAPIClient(token=mock_github_token, per_page=50)
            assert client.per_page == 50

    def test_init_creates_github_client(self, mock_github_token: "str") -> "None":
        with patch("src.github_api_client.Github") as mock_github:
            with patch("src.github_api_client.Auth") as mock_auth:
                GithubAPIClient(token=mock_github_token)
                mock_auth.Token.assert_called_once_with(mock_github_token)
                mock_github.assert_called_once()

    def test_init_creates_requests_session(self, mock_github_token: "str") -> "None":
        with patch("src.github_api_client.Github"):
            client = GithubAPIClient(token=mock_github_token)
            assert "Authorization" in client._session.headers
            assert (
                client._session.headers["Authorization"] == f"token {mock_github_token}"
            )
            assert client._session.headers["Accept"] == "application/vnd.github+json"
            assert client._session.headers["X-GitHub-Api-Version"] == "2022-11-28"


class TestFetchNext:
    """
    handles all tests for _fetch_next method.
    """

    def test_fetch_next_no_next_link(self, github_client: "GithubAPIClient") -> "None":
        response = Mock()
        response.links = {}
        url = "https://api.github.com/test"
        params = {"per_page": 100}

        next_url, next_params = github_client._fetch_next(response, url, params)

        assert next_url == ""
        assert next_params == params

    def test_fetch_next_with_next_link(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        response = Mock()
        response.links = {"next": {"url": "https://api.github.com/test?page=2"}}
        url = "https://api.github.com/test"
        params = {"per_page": 100}

        next_url, next_params = github_client._fetch_next(response, url, params)

        assert next_url == "https://api.github.com/test?page=2"
        assert next_params == {}


class TestPaginate:
    """
    handles all tests for _paginate method.
    """

    def test_paginate_single_page(
        self, github_client: "GithubAPIClient", mock_response: "Mock"
    ) -> "None":
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        github_client._session.get = Mock(return_value=mock_response)

        url = "https://api.github.com/test"
        result = github_client._paginate(url)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_paginate_multiple_pages(self, github_client: "GithubAPIClient") -> "None":
        # First page response
        response1 = Mock(spec=requests.Response)
        response1.json.return_value = [{"id": 1}]
        response1.links = {"next": {"url": "https://api.github.com/test?page=2"}}

        # Second page response
        response2 = Mock(spec=requests.Response)
        response2.json.return_value = [{"id": 2}]
        response2.links = {}

        github_client._session.get = Mock(side_effect=[response1, response2])

        url = "https://api.github.com/test"
        result = github_client._paginate(url)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_paginate_with_extra_params(
        self, github_client: "GithubAPIClient", mock_response: "Mock"
    ) -> "None":
        mock_response.json.return_value = []
        github_client._session.get = Mock(return_value=mock_response)

        url = "https://api.github.com/test"
        extra_params = {"state": "open"}
        github_client._paginate(url, extra_params=extra_params)

        # check that extra params were passed
        call_args = github_client._session.get.call_args
        assert call_args[1]["params"]["state"] == "open"
        assert call_args[1]["params"]["per_page"] == 100

    def test_paginate_http_error(self, github_client: "GithubAPIClient") -> "None":
        response = Mock(spec=requests.Response)
        response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        github_client._session.get = Mock(return_value=response)

        url = "https://api.github.com/test"

        with pytest.raises(requests.HTTPError):
            github_client._paginate(url)


class TestConvertToRHDHPluginPackage:
    """
    handles all tests for _convert_to_rhdh_plugin_package method.
    """

    def test_convert_valid_versions(
        self,
        github_client: "GithubAPIClient",
        sample_package_versions: "list[dict[str, Any]]",
    ) -> "None":
        package_name = "test-package"
        result = github_client._convert_to_rhdh_plugin_package(
            package_name, sample_package_versions
        )

        assert result.name == package_name

        # should only include versions with correct prefix (2 out of 3)
        assert len(result.versions) == 2
        assert result.versions[0].version == Version("0.1.2")
        assert result.versions[1].version == Version("0.1.3")

    def test_convert_filters_invalid_tag_prefix(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                # wrong prefix package
                "metadata": {"container": {"tags": ["v1.0.0"]}},
                "created_at": "2024-01-15T10:00:00Z",
            }
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions
        )

        assert len(result.versions) == 0

    def test_convert_handles_missing_metadata(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                "created_at": "2024-01-15T10:00:00Z",
                # no metadata
            }
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions
        )

        assert len(result.versions) == 0

    def test_convert_handles_missing_container(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                # no container
                "metadata": {},
                "created_at": "2024-01-15T10:00:00Z",
            }
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions
        )

        assert len(result.versions) == 0

    def test_convert_handles_missing_tags(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                # no tags
                "metadata": {"container": {}},
                "created_at": "2024-01-15T10:00:00Z",
            }
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions
        )

        assert len(result.versions) == 0

    def test_convert_handles_empty_tags_list(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                # empty tags
                "metadata": {"container": {"tags": []}},
                "created_at": "2024-01-15T10:00:00Z",
            }
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions
        )

        assert len(result.versions) == 0

    def test_convert_handles_missing_created_at(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                "metadata": {"container": {"tags": ["next__0.1.2"]}},
                # missing created_at
            }
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions
        )

        assert len(result.versions) == 0

    def test_convert_with_tag_prefix_filter(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                "metadata": {"container": {"tags": ["next__1.0.0"]}},
                "created_at": "2024-01-15T10:00:00Z",
            },
            {
                "name": "12346",
                "metadata": {"container": {"tags": ["next__1.1.0"]}},
                "created_at": "2024-01-16T10:00:00Z",
            },
            {
                "name": "12347",
                "metadata": {"container": {"tags": ["stable__2.0.0"]}},
                "created_at": "2024-01-17T10:00:00Z",
            },
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions, tag_prefix_filter="next__"
        )

        assert len(result.versions) == 2
        assert result.versions[0].version == Version("1.0.0")
        assert result.versions[1].version == Version("1.1.0")

    @patch(
        "src.github_api_client.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
        ["next__", "stable__", "previous__"],
    )
    def test_convert_with_tag_prefix_filter_excludes_other_prefixes(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                "metadata": {"container": {"tags": ["next__1.0.0"]}},
                "created_at": "2024-01-15T10:00:00Z",
            },
            {
                "name": "12346",
                "metadata": {"container": {"tags": ["previous__1.0.0"]}},
                "created_at": "2024-01-16T10:00:00Z",
            },
            {
                "name": "12347",
                "metadata": {"container": {"tags": ["stable__1.0.0"]}},
                "created_at": "2024-01-17T10:00:00Z",
            },
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions, tag_prefix_filter="stable__"
        )

        assert len(result.versions) == 1
        assert result.versions[0].version == Version("1.0.0")

    @patch(
        "src.github_api_client.RHDHPluginUpdaterConfig.GH_PACKAGE_TAG_PREFIX",
        ["next__", "stable__"],
    )
    def test_convert_without_tag_prefix_filter_includes_all_valid(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        package_name = "test-package"
        raw_versions = [
            {
                "name": "12345",
                "metadata": {"container": {"tags": ["next__1.0.0"]}},
                "created_at": "2024-01-15T10:00:00Z",
            },
            {
                "name": "12346",
                "metadata": {"container": {"tags": ["stable__2.0.0"]}},
                "created_at": "2024-01-16T10:00:00Z",
            },
        ]

        result = github_client._convert_to_rhdh_plugin_package(
            package_name, raw_versions, tag_prefix_filter=None
        )

        assert len(result.versions) == 2


class TestFetchPackage:
    """
    handles all tests for fetch_package method.
    """

    def test_fetch_package_success(
        self,
        github_client: "GithubAPIClient",
        sample_package_versions: "list[dict[str, Any]]",
    ) -> "None":
        github_client._paginate = Mock(return_value=sample_package_versions)

        package_name = "test-package"
        result = github_client.fetch_package(package_name)

        assert result.name == package_name
        assert len(result.versions) == 2

    def test_fetch_package_no_versions(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        github_client._paginate = Mock(return_value=[])

        package_name = "test-package"
        result = github_client.fetch_package(package_name)

        assert result.name == package_name
        assert len(result.versions) == 0

    def test_fetch_package_url_encoding(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        github_client._paginate = Mock(return_value=[])

        package_name = "org/package-name"
        github_client.fetch_package(package_name)

        # check that _paginate was called with encoded URL
        call_args = github_client._paginate.call_args
        url = call_args[1]["url"]
        assert "org%2Fpackage-name" in url

    def test_fetch_package_with_tag_prefix_filter(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        raw_versions = [
            {
                "name": "12345",
                "metadata": {"container": {"tags": ["next__1.0.0"]}},
                "created_at": "2024-01-15T10:00:00Z",
            },
            {
                "name": "12346",
                "metadata": {"container": {"tags": ["stable__2.0.0"]}},
                "created_at": "2024-01-16T10:00:00Z",
            },
        ]
        github_client._paginate = Mock(return_value=raw_versions)

        package_name = "test-package"
        result = github_client.fetch_package(package_name, tag_prefix_filter="next__")

        assert result.name == package_name
        assert len(result.versions) == 1
        assert result.versions[0].version == Version("1.0.0")


class TestBranchExists:
    """
    handles all tests for _branch_exists method.
    """

    @pytest.mark.parametrize(
        ("strict", "error", "expected"),
        [
            (False, None, True),
            (True, None, True),
            (False, Exception("Branch not found"), False),
            (True, GithubException(404, {"message": "Not Found"}), False),
        ],
    )
    def test_branch_exists(
        self,
        github_client: "GithubAPIClient",
        strict: "bool",
        error: "Exception | None",
        expected: "bool",
    ) -> "None":
        repo = Mock()
        repo.get_git_ref.side_effect = error

        assert (
            github_client._branch_exists(repo, "test-branch", strict=strict) is expected
        )
        repo.get_git_ref.assert_called_once_with("heads/test-branch")

    @pytest.mark.parametrize(
        "error",
        [
            GithubException(500, {"message": "Server Error"}),
            requests.Timeout("GitHub API timed out"),
        ],
    )
    def test_strict_branch_lookup_propagates_errors(
        self, github_client: "GithubAPIClient", error: "Exception"
    ) -> "None":
        repo = Mock()
        repo.get_git_ref.side_effect = error

        with pytest.raises(type(error)) as exc_info:
            github_client._branch_exists(repo, "test-branch", strict=True)

        assert exc_info.value is error


class TestHandleNewEndline:
    """
    handles all tests for _handle_new_endline method.
    """

    def test_add_newline_when_original_has_it(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        original = "line1\nline2\n"
        new = "line1\nline2"

        result = github_client._handle_new_endline(original, new)

        assert result == "line1\nline2\n"

    def test_remove_newline_when_original_lacks_it(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        original = "line1\nline2"
        new = "line1\nline2\n"

        result = github_client._handle_new_endline(original, new)

        assert result == "line1\nline2"

    def test_no_change_when_both_have_newline(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        original = "line1\nline2\n"
        new = "line1\nline3\n"

        result = github_client._handle_new_endline(original, new)

        assert result == "line1\nline3\n"

    def test_no_change_when_neither_has_newline(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        original = "line1\nline2"
        new = "line1\nline3"

        result = github_client._handle_new_endline(original, new)

        assert result == "line1\nline3"


class TestCreatePullRequest:
    """
    handles all tests for create_pull_request method.
    """

    @pytest.mark.parametrize("strategy", ["separate", "grouped"])
    def test_create_pr_success_new_branch(
        self, github_client: "GithubAPIClient", monkeypatch: "Any", strategy: "str"
    ) -> "None":
        monkeypatch.setattr("src.github_api_client.UPDATE_PR_STRATEGY", strategy)
        # Mock repository and related objects
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"
        mock_repo.get_git_ref.side_effect = [
            mock_base_ref,
            Exception("Branch not found"),
        ]
        mock_repo.create_git_ref.return_value = Mock()

        mock_contents = Mock(spec=ContentFile)
        mock_contents.decoded_content = b"old content\n"
        mock_contents.sha = "file_sha_123"
        mock_repo.get_contents.return_value = mock_contents
        mock_repo.update_file.return_value = Mock()

        mock_pr = Mock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/1"
        mock_repo.create_pull.return_value = mock_pr

        github_client.client.get_repo = Mock(return_value=mock_repo)

        result = github_client.create_pull_request(
            repo_full_name="owner/repo",
            file_path="config.yaml",
            new_content="new content",
            branch_name="update-plugin",
            pr_title="Update plugin",
            pr_body="Update plugin to version 1.0.0",
            base_branch="main",
        )

        assert result == "https://github.com/owner/repo/pull/1"
        mock_repo.create_git_ref.assert_called_once_with(
            "refs/heads/update-plugin", "base_sha_123"
        )
        mock_repo.update_file.assert_called_once()
        mock_repo.create_pull.assert_called_once()

    @pytest.mark.parametrize("strategy", ["separate", "grouped"])
    def test_create_pr_branch_exists_separate_or_grouped_strategy(
        self, github_client: "GithubAPIClient", monkeypatch: "Any", strategy: "str"
    ) -> "None":
        monkeypatch.setattr("src.github_api_client.UPDATE_PR_STRATEGY", strategy)
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"
        mock_repo.get_git_ref.return_value = mock_base_ref

        github_client.client.get_repo = Mock(return_value=mock_repo)
        github_client._branch_exists = Mock(return_value=True)

        with pytest.raises(GithubPRFailedException) as exc_info:
            github_client.create_pull_request(
                repo_full_name="owner/repo",
                file_path="config.yaml",
                new_content="new content",
                branch_name="update-plugin",
                pr_title="Update plugin",
                pr_body="Update plugin to version 1.0.0",
                base_branch="main",
            )

        assert "already exists" in str(exc_info.value)

        mock_repo.get_pulls.assert_not_called()
        mock_repo.create_git_ref.assert_not_called()
        mock_repo.update_file.assert_not_called()
        mock_repo.create_pull.assert_not_called()

    @patch("src.github_api_client.UPDATE_PR_STRATEGY", GithubPullRequestStrategy.JOINT)
    def test_create_pr_branch_exists_with_open_pr(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"
        mock_repo.get_git_ref.return_value = mock_base_ref
        mock_repo.owner.login = "owner"

        # mock existing open PR
        mock_existing_pr = Mock()
        mock_existing_pr.html_url = "https://github.com/owner/repo/pull/5"
        mock_repo.get_pulls.return_value = [mock_existing_pr]

        github_client.client.get_repo = Mock(return_value=mock_repo)
        github_client._branch_exists = Mock(return_value=True)

        with pytest.raises(GithubPRFailedException) as exc_info:
            github_client.create_pull_request(
                repo_full_name="owner/repo",
                file_path="config.yaml",
                new_content="new content",
                branch_name="update-plugin",
                pr_title="Update plugin",
                pr_body="Update plugin to version 1.0.0",
                base_branch="main",
            )

        assert "Open PR already exists" in str(exc_info.value)

    def test_create_pr_file_update_failure(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"
        mock_repo.get_git_ref.side_effect = [
            mock_base_ref,
            Exception("Branch not found"),
        ]
        mock_repo.create_git_ref.return_value = Mock()
        mock_repo.get_contents.side_effect = Exception("File not found")

        github_client.client.get_repo = Mock(return_value=mock_repo)

        with pytest.raises(GithubPRFailedException) as exc_info:
            github_client.create_pull_request(
                repo_full_name="owner/repo",
                file_path="config.yaml",
                new_content="new content",
                branch_name="update-plugin",
                pr_title="Update plugin",
                pr_body="Update plugin to version 1.0.0",
                base_branch="main",
            )

        assert "Failed to update file" in str(exc_info.value)

    def test_create_pr_creation_failure(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"
        mock_repo.get_git_ref.side_effect = [
            mock_base_ref,
            Exception("Branch not found"),
        ]
        mock_repo.create_git_ref.return_value = Mock()

        mock_contents = Mock(spec=ContentFile)
        mock_contents.decoded_content = b"old content\n"
        mock_contents.sha = "file_sha_123"
        mock_repo.get_contents.return_value = mock_contents
        mock_repo.update_file.return_value = Mock()
        mock_repo.create_pull.side_effect = Exception("PR creation failed")

        github_client.client.get_repo = Mock(return_value=mock_repo)

        with pytest.raises(GithubPRFailedException) as exc_info:
            github_client.create_pull_request(
                repo_full_name="owner/repo",
                file_path="config.yaml",
                new_content="new content",
                branch_name="update-plugin",
                pr_title="Update plugin",
                pr_body="Update plugin to version 1.0.0",
                base_branch="main",
            )

        assert "Failed to create PR" in str(exc_info.value)

    def test_create_pr_preserves_newline(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"
        mock_repo.get_git_ref.side_effect = [
            mock_base_ref,
            Exception("Branch not found"),
        ]
        mock_repo.create_git_ref.return_value = Mock()

        mock_contents = Mock(spec=ContentFile)
        mock_contents.decoded_content = b"old content\n"
        mock_contents.sha = "file_sha_123"
        mock_repo.get_contents.return_value = mock_contents
        mock_repo.update_file.return_value = Mock()

        mock_pr = Mock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/1"
        mock_repo.create_pull.return_value = mock_pr

        github_client.client.get_repo = Mock(return_value=mock_repo)

        github_client.create_pull_request(
            repo_full_name="owner/repo",
            file_path="config.yaml",
            new_content="new content",
            branch_name="update-plugin",
            pr_title="Update plugin",
            pr_body="Update plugin to version 1.0.0",
            base_branch="main",
        )

        call_args = mock_repo.update_file.call_args
        assert call_args[1]["content"] == "new content\n"

    def test_create_pr_deletes_branch_on_failure(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"

        mock_branch_ref = Mock()

        def get_git_ref_side_effect(ref_name):
            if ref_name == "heads/main":
                return mock_base_ref
            elif ref_name == "heads/update-plugin":
                if get_git_ref_side_effect.call_count == 0:
                    get_git_ref_side_effect.call_count += 1
                    raise Exception("Branch not found")
                else:
                    return mock_branch_ref
            return Mock()

        get_git_ref_side_effect.call_count = 0
        mock_repo.get_git_ref.side_effect = get_git_ref_side_effect
        mock_repo.create_git_ref.return_value = Mock()

        mock_contents = Mock(spec=ContentFile)
        mock_contents.decoded_content = b"old content\n"
        mock_contents.sha = "file_sha_123"
        mock_repo.get_contents.return_value = mock_contents
        mock_repo.update_file.return_value = Mock()
        mock_repo.create_pull.side_effect = Exception("PR creation failed")

        github_client.client.get_repo = Mock(return_value=mock_repo)

        with pytest.raises(GithubPRFailedException) as exc_info:
            github_client.create_pull_request(
                repo_full_name="owner/repo",
                file_path="config.yaml",
                new_content="new content",
                branch_name="update-plugin",
                pr_title="Update plugin",
                pr_body="Update plugin to version 1.0.0",
                base_branch="main",
            )

        assert "Failed to create PR" in str(exc_info.value)
        mock_branch_ref.delete.assert_called_once()

    def test_create_pr_handles_branch_deletion_failure(
        self, github_client: "GithubAPIClient"
    ) -> "None":
        mock_repo = Mock()
        mock_base_ref = Mock()
        mock_base_ref.object.sha = "base_sha_123"

        def get_git_ref_side_effect(ref_name):
            if ref_name == "heads/main":
                return mock_base_ref
            elif ref_name == "heads/update-plugin":
                if get_git_ref_side_effect.call_count == 0:
                    get_git_ref_side_effect.call_count += 1
                    raise Exception("Branch not found")
                else:
                    raise Exception("Cannot get branch for deletion")
            return Mock()

        get_git_ref_side_effect.call_count = 0
        mock_repo.get_git_ref.side_effect = get_git_ref_side_effect
        mock_repo.create_git_ref.return_value = Mock()

        mock_contents = Mock(spec=ContentFile)
        mock_contents.decoded_content = b"old content\n"
        mock_contents.sha = "file_sha_123"
        mock_repo.get_contents.return_value = mock_contents
        mock_repo.update_file.return_value = Mock()
        mock_repo.create_pull.side_effect = Exception("PR creation failed")

        github_client.client.get_repo = Mock(return_value=mock_repo)

        with pytest.raises(GithubPRFailedException) as exc_info:
            github_client.create_pull_request(
                repo_full_name="owner/repo",
                file_path="config.yaml",
                new_content="new content",
                branch_name="update-plugin",
                pr_title="Update plugin",
                pr_body="Update plugin to version 1.0.0",
                base_branch="main",
            )

        assert "Failed to create PR" in str(exc_info.value)
