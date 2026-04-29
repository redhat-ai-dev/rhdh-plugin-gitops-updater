import logging
import os

# DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH: is the path of the dynamic
# plugins config yaml file
DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH = os.getenv(
    "DYNAMIC_PLUGINS_CONFIG_YAML_FILE_PATH", "dynamic-plugins.yaml"
)

# DYNAMIC_PLUGINS_CONFIG_YAML_LOCATION: is the location of the dynamic
# plugins config inside the yaml file.
DYNAMIC_PLUGINS_CONFIG_YAML_LOCATION = os.getenv(
    "DYNAMIC_PLUGINS_CONFIG_YAML_LOCATION", "global.dynamic.plugins"
)

# DYNAMIC_PLUGINS_CONFIG_YAML_EXTRA_LOCATIONS: list of
# additional locations to check for plugins in the yaml file.
_extra_locations_str = os.getenv(
    "DYNAMIC_PLUGINS_CONFIG_YAML_EXTRA_LOCATIONS", "global.lightspeed.plugins"
)
DYNAMIC_PLUGINS_CONFIG_YAML_EXTRA_LOCATIONS = [
    loc.strip() for loc in _extra_locations_str.split(",") if loc.strip()
]

# GITHUB_TOKEN: is the GitHub token to use for authentication
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# UPDATE_PR_STRATEGY: is the strategy to use when creating
# the github pull requests. It can be either "separate" or "joint".
UPDATE_PR_STRATEGY = os.getenv("UPDATE_PR_STRATEGY", "separate")

# PR_CREATION_LIMIT: is the maximum number of pull requests to create.
PR_CREATION_LIMIT = int(os.getenv("PR_CREATION_LIMIT", "0"))

# GITHUB_REPOSITORY: is the Github repository where PRs will be
# created (format: owner/repo)
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")

# GITHUB_REF: is the base branch for PRs; BASE_BRANCH takes explicit precedence
_base_branch = os.getenv("BASE_BRANCH", "")
if not _base_branch:
    _github_ref = os.getenv("GITHUB_REF", "main")
    _base_branch = (
        _github_ref.replace("refs/heads/", "")
        if _github_ref.startswith("refs/heads/")
        else _github_ref
    )
GITHUB_REF = _base_branch

# VERBOSE: is the verbosity level (0 = normal, 1 = verbose)
VERBOSE = int(os.getenv("VERBOSE", 0))

# GH_PACKAGE_TAG_PREFIXES: newline-separated or comma-separated list
# of tag prefixes to consider when checking for plugin updates (e.g.,
# "next__\nprevious__" or "next__,previous__")
_tag_prefixes_str = os.getenv("GH_PACKAGE_TAG_PREFIXES", "next__")

# check if there are new lines in the string to determine the separator
if "\n" in _tag_prefixes_str:
    GH_PACKAGE_TAG_PREFIXES = [
        prefix.strip() for prefix in _tag_prefixes_str.split("\n") if prefix.strip()
    ]
else:
    GH_PACKAGE_TAG_PREFIXES = [
        prefix.strip() for prefix in _tag_prefixes_str.split(",") if prefix.strip()
    ]

# LOGGING_LEVEL: is the logging level based on verbosity
LOGGING_LEVEL = "DEBUG" if VERBOSE > 0 else "INFO"

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOGGING_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)
