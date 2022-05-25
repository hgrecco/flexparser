"""
    flexcache
    ~~~~~~~~~

    Classes for persistent caching and invalidating cached objects,
    which are built from a source object and a (potentially expensive)
    conversion function.

    :copyright: 2022 by flexcache Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""


import pkg_resources

try:  # pragma: no cover
    __version__ = pkg_resources.get_distribution("flexparser").version
except Exception:  # pragma: no cover
    # we seem to have a local copy not installed without setuptools
    # so the reported version will be unknown
    __version__ = "unknown"

