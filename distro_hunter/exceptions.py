"""Exception classes for Distro Hunter."""

from __future__ import annotations


class DistroHunterError(Exception):
    """Base exception for all Distro Hunter errors."""

    pass


class ChecksumError(DistroHunterError):
    """Base class for checksum-related errors."""

    pass


class ChecksumMismatchError(ChecksumError):
    """Raised when file checksum does not match expected value.
    
    Attributes:
        message: Description of the mismatch
        expected: The expected checksum value
        actual: The actual checksum value
        algorithm: The checksum algorithm used (sha256, sha512, etc.)
    """

    def __init__(
        self,
        message: str,
        *,
        expected: str | None = None,
        actual: str | None = None,
        algorithm: str | None = None,
    ) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual
        self.algorithm = algorithm


class ChecksumUnavailableError(ChecksumError):
    """Raised when checksum cannot be retrieved or calculated.
    
    Attributes:
        message: Description of why checksum is unavailable
        url: The URL where checksum lookup was attempted
    """

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class DownloadError(DistroHunterError):
    """Base class for download-related errors."""

    pass


class DownloadAttemptError(DownloadError):
    """Raised when a download attempt fails.
    
    Attributes:
        message: Description of the failure
        candidate: The Candidate that failed to download
        remote: Optional RemoteFileInfo with URL details
    """

    def __init__(self, message: str, *, candidate: object, remote: object | None = None) -> None:
        super().__init__(message)
        self.candidate = candidate
        self.remote = remote


class RunLockError(DistroHunterError):
    """Raised when another Distro Hunter process already holds the run lock.
    
    This prevents concurrent execution of certain commands (discover, run, sync, etc.)
    to avoid conflicts with plugin state and downloads.
    """

    pass
