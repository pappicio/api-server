#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

CONFIG_ROOT = Path.home() / "printer_data" / "config"
MANIFEST = "oc_tunneled_component"
CACHE_SECONDS = 600

_cache = {"time": 0, "projects": None}
_lock = threading.Lock()


def git(path, *args):
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def github_repository(url):
    try:
        parsed = urlparse(url)
        if parsed.hostname not in ("github.com", "www.github.com"):
            return None

        parts = parsed.path.strip("/").removesuffix(".git").split("/")
        if len(parts) != 2 or not all(parts):
            return None

        return parts[0], parts[1]
    except (TypeError, ValueError):
        return None


def github_api(path):
    request = Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "OpenCreator-Dashboard"
        }
    )
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def check_github(owner, repo, branch, local_commit):
    base = f"/repos/{quote(owner)}/{quote(repo)}"

    try:
        remote = github_api(
            f"{base}/commits/{quote(branch, safe='')}"
        )
        remote_commit = remote["sha"]

        result = {
            "remote_reachable": True,
            "remote_commit": remote_commit,
            "remote_message": remote.get("commit", {}).get(
                "message", ""
            ).splitlines()[0],
            "updates_available": 0,
            "local_ahead": 0,
            "error": None
        }

        if remote_commit == local_commit:
            return result

        comparison = github_api(
            f"{base}/compare/{local_commit}...{remote_commit}"
        )

        result["updates_available"] = comparison.get("ahead_by", 0)
        result["local_ahead"] = comparison.get("behind_by", 0)
        result["comparison_status"] = comparison.get("status")
        return result

    except (HTTPError, URLError, TimeoutError, OSError,
            ValueError, KeyError) as exc:
        return {
            "remote_reachable": False,
            "remote_commit": None,
            "updates_available": None,
            "local_ahead": None,
            "error": str(exc)
        }


def discover_projects():
    projects = []
    ignored = {
        ".git", "__pycache__", ".venv", "venv",
        ".opencreator-updater"
    }

    for current, dirs, files in os.walk(CONFIG_ROOT):
        dirs[:] = [d for d in dirs if d not in ignored]

        if MANIFEST not in files:
            continue

        folder = Path(current)

        try:
            manifest = json.loads(
                (folder / MANIFEST).read_text(encoding="utf-8")
            )

            if manifest.get("schema") != 1:
                continue

            repo_root = git(folder, "rev-parse", "--show-toplevel")
            if not repo_root or Path(repo_root).resolve() != folder.resolve():
                continue

            repository_url = manifest.get("repository", "")
            repository = github_repository(repository_url)

            branch = git(folder, "branch", "--show-current")
            local_commit = git(folder, "rev-parse", "HEAD")
            dirty = bool(git(
                folder, "status", "--porcelain",
                "--untracked-files=normal"
            ))

            item = {
                "id": manifest.get("id"),
                "name": manifest.get("name"),
                "description": manifest.get("description", ""),
                "author": manifest.get("author", ""),
                "repository": repository_url,
                "components": manifest.get("components", []),
                "branch": branch,
                "local_commit": local_commit,
                "dirty": dirty,
                "path": str(folder),
                "remote_reachable": False,
                "remote_commit": None,
                "updates_available": None,
                "local_ahead": None,
                "error": None
            }

            if (
                item["id"] and item["name"]
                and repository and branch and local_commit
            ):
                owner, repo = repository
                item.update(
                    check_github(owner, repo, branch, local_commit)
                )

            projects.append(item)

        except (OSError, ValueError, TypeError):
            continue

    return projects


def collect_custom_projects(force=False):
    now = time.time()

    with _lock:
        if (
            not force
            and _cache["projects"] is not None
            and now - _cache["time"] < CACHE_SECONDS
        ):
            return {"projects": _cache["projects"], "cached": True}

        projects = discover_projects()
        _cache["time"] = now
        _cache["projects"] = projects

        return {"projects": projects, "cached": False}
