"""
GitHub Pages deployment — pushes chart PNGs to a gh-pages branch
and returns public URLs for embedding in the email.

Uses the GitHub API (via a personal access token) to commit files
directly to the gh-pages branch, avoiding the need for a full
git clone/push cycle in CI.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from pathlib import Path

import requests

from config import GITHUB_PAGES_BASE_URL, GITHUB_PAGES_BRANCH, GITHUB_PAGES_REPO, get_env

logger = logging.getLogger(__name__)


def deploy_charts(chart_paths: list[str]) -> dict[str, str]:
    """
    Deploy chart PNG files to GitHub Pages and return their public URLs.

    Commits each image to the gh-pages branch of the configured repo.
    Images are organized by date: charts/YYYY-MM-DD/filename.png

    Args:
        chart_paths: List of absolute paths to local PNG files.

    Returns:
        Dict mapping local filename (without path) to public URL.
        E.g. {"unrate_20240115.png": "https://user.github.io/repo/charts/2024-01-15/unrate_20240115.png"}
    """
    if not chart_paths:
        return {}

    token = get_env("GITHUB_TOKEN", required=False)
    if not token:
        logger.warning(
            "GITHUB_TOKEN not set — skipping GitHub Pages deployment. "
            "Charts will use local paths (email images won't load remotely)."
        )
        return _fallback_local_urls(chart_paths)

    date_folder = datetime.now().strftime("%Y-%m-%d")
    deployed_urls: dict[str, str] = {}

    for chart_path in chart_paths:
        path = Path(chart_path)
        if not path.exists():
            logger.warning("Chart file not found: %s", chart_path)
            continue

        filename = path.name
        remote_path = f"charts/{date_folder}/{filename}"

        try:
            # Read and base64-encode the file
            with open(path, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("utf-8")

            # Check if file already exists (to get its SHA for update)
            existing_sha = _get_file_sha(token, remote_path)

            # Create or update the file via GitHub API
            api_url = (
                f"https://api.github.com/repos/{GITHUB_PAGES_REPO}"
                f"/contents/{remote_path}"
            )

            payload: dict = {
                "message": f"Deploy chart: {filename}",
                "content": content_b64,
                "branch": GITHUB_PAGES_BRANCH,
            }
            if existing_sha:
                payload["sha"] = existing_sha

            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }

            response = requests.put(api_url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()

            public_url = f"{GITHUB_PAGES_BASE_URL}/{remote_path}"
            deployed_urls[filename] = public_url

            logger.info("Deployed: %s → %s", filename, public_url)

        except requests.HTTPError as e:
            logger.warning(
                "Failed to deploy %s: %s %s",
                filename,
                e.response.status_code if e.response else "unknown",
                e.response.text[:200] if e.response else "",
            )
        except Exception:
            logger.warning("Failed to deploy %s", filename, exc_info=True)

    logger.info("Deployed %d/%d charts to GitHub Pages", len(deployed_urls), len(chart_paths))
    return deployed_urls


def _get_file_sha(token: str, remote_path: str) -> str | None:
    """
    Get the SHA of an existing file on the gh-pages branch.

    Needed for the GitHub API's "update file" operation.

    Args:
        token: GitHub personal access token.
        remote_path: Path within the repo (e.g. "charts/2024-01-15/unrate.png").

    Returns:
        SHA string if file exists, None otherwise.
    """
    api_url = (
        f"https://api.github.com/repos/{GITHUB_PAGES_REPO}"
        f"/contents/{remote_path}?ref={GITHUB_PAGES_BRANCH}"
    )
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("sha")
    except requests.RequestException:
        pass

    return None


def _fallback_local_urls(chart_paths: list[str]) -> dict[str, str]:
    """
    Generate placeholder URLs using local file paths.

    Used when GITHUB_TOKEN is not available (local development).
    The email will render with broken images remotely but works
    for local preview.

    Args:
        chart_paths: List of absolute local file paths.

    Returns:
        Dict mapping filename to file:// URL.
    """
    urls: dict[str, str] = {}
    for chart_path in chart_paths:
        path = Path(chart_path)
        if path.exists():
            urls[path.name] = f"file://{path.resolve()}"
    return urls


def ensure_gh_pages_branch() -> bool:
    """
    Ensure the gh-pages branch exists in the repo.

    Creates it as an orphan branch with a placeholder index.html
    if it doesn't exist. Call this during initial setup.

    Returns:
        True if branch exists or was created, False on failure.
    """
    token = get_env("GITHUB_TOKEN", required=False)
    if not token:
        logger.warning("GITHUB_TOKEN not set — cannot create gh-pages branch")
        return False

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Check if branch exists
    branch_url = (
        f"https://api.github.com/repos/{GITHUB_PAGES_REPO}"
        f"/branches/{GITHUB_PAGES_BRANCH}"
    )
    try:
        response = requests.get(branch_url, headers=headers, timeout=10)
        if response.status_code == 200:
            logger.info("gh-pages branch already exists")
            return True
    except requests.RequestException:
        pass

    # Create branch — need a ref to base it on
    try:
        # Get default branch SHA
        repo_url = f"https://api.github.com/repos/{GITHUB_PAGES_REPO}"
        repo_resp = requests.get(repo_url, headers=headers, timeout=10)
        repo_resp.raise_for_status()
        default_branch = repo_resp.json().get("default_branch", "main")

        ref_url = f"https://api.github.com/repos/{GITHUB_PAGES_REPO}/git/ref/heads/{default_branch}"
        ref_resp = requests.get(ref_url, headers=headers, timeout=10)
        ref_resp.raise_for_status()
        sha = ref_resp.json()["object"]["sha"]

        # Create the gh-pages branch
        create_url = f"https://api.github.com/repos/{GITHUB_PAGES_REPO}/git/refs"
        create_resp = requests.post(
            create_url,
            json={"ref": f"refs/heads/{GITHUB_PAGES_BRANCH}", "sha": sha},
            headers=headers,
            timeout=10,
        )
        create_resp.raise_for_status()

        logger.info("Created gh-pages branch")
        return True

    except Exception:
        logger.error("Failed to create gh-pages branch", exc_info=True)
        return False
