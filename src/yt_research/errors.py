"""Domain exceptions and stable CLI exit codes."""

from __future__ import annotations


class YTResearchError(Exception):
    """Base class for expected, user-facing failures."""

    exit_code = 5


class InvalidInputError(YTResearchError):
    exit_code = 2


class CredentialsError(YTResearchError):
    exit_code = 3


class NotFoundError(YTResearchError):
    exit_code = 4


class AmbiguousChannelError(NotFoundError):
    """Raised when research is attempted with an unresolvable plain name."""


class UpstreamError(YTResearchError):
    exit_code = 5


class QuotaError(UpstreamError):
    pass


class NetworkError(UpstreamError):
    pass
