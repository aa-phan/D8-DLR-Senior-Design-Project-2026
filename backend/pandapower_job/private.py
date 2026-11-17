"""
The private-path guard of the owner's commands (pandapower-solver Phase 1, plan 01-09: PSE-04, D-08).

The anti-pattern this prevents (research, "Anti-Patterns to Avoid"): a report, a converted copy or
an extracted session written somewhere the repository tracks. The repository is public and git
history is permanent, so every file the owner's commands write goes through this module, which
refuses a path unless all of these hold:

- it resolves (symbolic links followed) to a place inside `<repo>/data/private/`;
- git reports it as ignored (`git check-ignore`, so the ignore rule the repository really has is the
  judge, not a copy of it written here);
- it is not reached through a symbolic link that leads out of `data/private/`;
- for a new file or folder, it does not exist yet (the default, so nothing is overwritten).

`PrivatePathRefused.reason` is one of `REFUSAL_REASONS`; the message holds the reason word and no
path. Files are created with owner-only permissions and without following a link at the last name.

`repo_root` is a parameter everywhere so the tests can point the guard at a throwaway git
repository; it defaults to the repository this file lives in.
"""

import json
import os
import subprocess

REFUSAL_REASONS = (
    "outside_private_root", "not_ignored", "not_a_git_checkout", "symlink_escape", "exists")

_GIT_TIMEOUT_SECONDS = 30


class PrivatePathRefused(ValueError):
    """A path is not a safe private location. `reason` is one of REFUSAL_REASONS."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "private path refused: %s" % reason)


def _default_repo():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))   # backend/pandapower_job -> backend -> repo


def _repo(repo_root):
    return os.path.realpath(repo_root if repo_root is not None else _default_repo())


def private_root(repo_root=None):
    """`<repo>/data/private` (not resolved further, so a link in place of it is noticed)."""
    return os.path.join(_repo(repo_root), "data", "private")


def _inside(path, root):
    return path == root or path.startswith(root + os.sep)


def _is_ignored(repo, resolved):
    relative = os.path.relpath(resolved, repo)
    env = dict(os.environ)
    # git must not look for a repository above the one named, or a folder that is not a checkout
    # could borrow an enclosing repository's ignore rules.
    env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(repo)
    try:
        completed = subprocess.run(
            ["git", "-C", repo, "check-ignore", "-q", "--", relative], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=_GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        raise PrivatePathRefused("not_a_git_checkout")
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise PrivatePathRefused("not_a_git_checkout")


def require_private(path, repo_root=None):
    """
    The resolved path of `path` when it is inside `<repo>/data/private/` and git-ignored; a
    PrivatePathRefused (reasons "outside_private_root", "symlink_escape", "not_a_git_checkout",
    "not_ignored") otherwise. The path need not exist.
    """
    repo = _repo(repo_root)
    root = os.path.join(repo, "data", "private")
    resolved = os.path.realpath(path)
    if not _inside(resolved, root):
        lexical = os.path.abspath(path)
        given = os.path.abspath(repo_root) if repo_root is not None else repo
        if _inside(lexical, root) or _inside(lexical, os.path.join(given, "data", "private")):
            raise PrivatePathRefused("symlink_escape")
        raise PrivatePathRefused("outside_private_root")
    if resolved == root:
        raise PrivatePathRefused("outside_private_root")
    if not _is_ignored(repo, resolved):
        raise PrivatePathRefused("not_ignored")
    return resolved


def make_private_dir(path, repo_root=None, exclusive=True):
    """Create the folder `path` (and missing parents) after `require_private`; returns its resolved
    path. With `exclusive` (the default) an existing name is refused with reason "exists"."""
    resolved = require_private(path, repo_root)
    if exclusive and os.path.lexists(resolved):
        raise PrivatePathRefused("exists")
    os.makedirs(resolved, exist_ok=not exclusive)
    return resolved


def write_private_bytes(path, data, repo_root=None, exclusive=True):
    """
    Write `data` (bytes) to `path` after `require_private`; returns the resolved path. With
    `exclusive` (the default) an existing file is refused with reason "exists". Missing parent
    folders are created. The file is owner-readable only.
    """
    resolved = require_private(path, repo_root)
    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    try:
        descriptor = os.open(resolved, flags, 0o600)
    except FileExistsError:
        raise PrivatePathRefused("exists")
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(bytes(data))
    return resolved


def write_private_json(path, obj, marker, repo_root=None, exclusive=True):
    """
    Write the dict `obj` as JSON with the key `marker` set to 1 (so the leak guard flags a stray
    copy by its shape), sorted keys and no NaN, through `write_private_bytes`.
    """
    if not isinstance(obj, dict):
        raise ValueError("a private JSON file must hold an object")
    document = dict(obj)
    document[marker] = 1
    text = json.dumps(document, sort_keys=True, allow_nan=False, indent=1) + "\n"
    return write_private_bytes(path, text.encode("ascii"), repo_root, exclusive)
