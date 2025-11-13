# orion/version.py
"""
Dynamic version retrieval using setuptools_scm.
The version is determined at runtime from git tags.
"""

try:
    from setuptools_scm import get_version
    from pathlib import Path
    # Get version from git repo root (parent of version.py location)
    repo_root = Path(__file__).parent
    __version__ = get_version(root=str(repo_root))
except (ImportError, LookupError):
    # Fallback if setuptools_scm is not available or not in a git repo
    try:
        from importlib.metadata import version
        __version__ = version('orion')
    except ImportError:
        try:
            from importlib_metadata import version
            __version__ = version('orion')
        except ImportError:
            __version__ = "0.0.0.dev0+unknown"
