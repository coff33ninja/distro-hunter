"""Adaptive download connection management with health tracking."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ConnectionState(Enum):
    """Connection health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    IDLE = "idle"


@dataclass(slots=True)
class ConnectionMetrics:
    """Metrics for a single connection."""

    worker_id: int
    total_attempts: int = 0
    successful_downloads: int = 0
    failed_downloads: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_activity: datetime | None = None
    state: ConnectionState = ConnectionState.IDLE

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_attempts == 0:
            return 1.0
        return self.successful_downloads / self.total_attempts

    @property
    def is_active(self) -> bool:
        """Check if connection has been active recently (within last 30 seconds)."""
        if self.last_activity is None:
            return False
        return datetime.now() - self.last_activity < timedelta(seconds=30)

    def record_success(self) -> None:
        """Record a successful download."""
        self.total_attempts += 1
        self.successful_downloads += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_activity = datetime.now()
        self._update_state()

    def record_failure(self) -> None:
        """Record a failed download."""
        self.total_attempts += 1
        self.failed_downloads += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_activity = datetime.now()
        self._update_state()

    def _update_state(self) -> None:
        """Update connection state based on metrics."""
        if self.total_attempts == 0:
            self.state = ConnectionState.IDLE
        elif self.consecutive_failures >= 3:
            self.state = ConnectionState.FAILING
        elif self.success_rate < 0.5:
            self.state = ConnectionState.DEGRADED
        else:
            self.state = ConnectionState.HEALTHY


@dataclass(slots=True)
class PoolMetrics:
    """Aggregate metrics for the connection pool."""

    connections: dict[int, ConnectionMetrics] = field(default_factory=dict)
    total_downloads: int = 0
    total_successes: int = 0
    total_failures: int = 0
    pool_resize_events: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def active_connections(self) -> int:
        """Count currently active connections."""
        with self._lock:
            return sum(1 for m in self.connections.values() if m.is_active)

    @property
    def healthy_connections(self) -> int:
        """Count healthy connections."""
        with self._lock:
            return sum(
                1
                for m in self.connections.values()
                if m.state == ConnectionState.HEALTHY
            )

    @property
    def failing_connections(self) -> int:
        """Count failing connections."""
        with self._lock:
            return sum(
                1
                for m in self.connections.values()
                if m.state == ConnectionState.FAILING
            )

    @property
    def overall_success_rate(self) -> float:
        """Calculate overall pool success rate."""
        if self.total_downloads == 0:
            return 1.0
        return self.total_successes / self.total_downloads

    def get_metrics(self, worker_id: int) -> ConnectionMetrics:
        """Get or create metrics for a worker."""
        with self._lock:
            if worker_id not in self.connections:
                self.connections[worker_id] = ConnectionMetrics(worker_id)
            return self.connections[worker_id]

    def record_success(self, worker_id: int) -> None:
        """Record successful download on worker."""
        with self._lock:
            self.total_downloads += 1
            self.total_successes += 1
            if worker_id in self.connections:
                self.connections[worker_id].record_success()

    def record_failure(self, worker_id: int) -> None:
        """Record failed download on worker."""
        with self._lock:
            self.total_downloads += 1
            self.total_failures += 1
            if worker_id in self.connections:
                self.connections[worker_id].record_failure()

    def record_resize(self) -> None:
        """Record a pool resize event."""
        with self._lock:
            self.pool_resize_events += 1


class AdaptiveConnectionPool:
    """Manages adaptive scaling of download connections based on health metrics."""

    def __init__(
        self,
        initial_workers: int = 3,
        min_workers: int = 1,
        max_workers: int = 8,
        scale_up_threshold: int = 5,
        scale_down_threshold: int = 3,
    ) -> None:
        """Initialize adaptive connection pool.

        Args:
            initial_workers: Starting number of worker connections
            min_workers: Minimum allowed connections
            max_workers: Maximum allowed connections
            scale_up_threshold: Consecutive successes needed to add a connection
            scale_down_threshold: Consecutive failures needed to remove a connection
        """
        self.initial_workers = initial_workers
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold

        self.current_workers = initial_workers
        self.metrics = PoolMetrics()
        self._lock = threading.Lock()
        self._on_scale_callback: Callable[[int, str], None] | None = None

    def set_scale_callback(self, callback: Callable[[int, str], None]) -> None:
        """Set callback for pool scaling events.

        Args:
            callback: Function(new_worker_count, reason) called on scale operations
        """
        self._on_scale_callback = callback

    def get_current_workers(self) -> int:
        """Get current number of worker connections."""
        with self._lock:
            return self.current_workers

    def evaluate_scaling(self) -> tuple[bool, str]:
        """Evaluate if pool should scale up/down.

        Returns:
            (should_scale, reason) tuple
        """
        with self._lock:
            failing = self.metrics.failing_connections
            healthy = self.metrics.healthy_connections
            current = self.current_workers

            # Consider scaling down if too many failures
            if failing >= self.scale_down_threshold and current > self.min_workers:
                return True, f"Scale down: {failing} connections failing"

            # Consider scaling up if healthy and not at max
            if (
                healthy >= self.scale_up_threshold
                and current < self.max_workers
                and self.metrics.overall_success_rate > 0.8
            ):
                return True, "Scale up: all connections healthy"

            return False, "No scaling needed"

    def scale_up(self) -> tuple[int, str]:
        """Add a connection to the pool.

        Returns:
            (new_worker_count, reason) tuple
        """
        with self._lock:
            should_scale, reason = self.evaluate_scaling()
            if not should_scale or self.current_workers >= self.max_workers:
                return self.current_workers, "Cannot scale up"

            self.current_workers += 1
            self.metrics.record_resize()
            reason = (
                f"Scaled to {self.current_workers} connections: improving reliability"
            )

            if self._on_scale_callback:
                self._on_scale_callback(self.current_workers, reason)

            return self.current_workers, reason

    def scale_down(self) -> tuple[int, str]:
        """Remove a connection from the pool.

        Returns:
            (new_worker_count, reason) tuple
        """
        with self._lock:
            if self.current_workers <= self.min_workers:
                return self.current_workers, "Already at minimum connections"

            self.current_workers -= 1
            self.metrics.record_resize()
            reason = f"Scaled to {self.current_workers} connections: reducing failing connections"

            if self._on_scale_callback:
                self._on_scale_callback(self.current_workers, reason)

            return self.current_workers, reason

    def get_status_summary(self) -> dict[str, object]:
        """Get current pool status summary.

        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            return {
                "current_workers": self.current_workers,
                "active_connections": self.metrics.active_connections,
                "healthy_connections": self.metrics.healthy_connections,
                "failing_connections": self.metrics.failing_connections,
                "total_downloads": self.metrics.total_downloads,
                "total_successes": self.metrics.total_successes,
                "total_failures": self.metrics.total_failures,
                "success_rate": self.metrics.overall_success_rate,
                "resize_events": self.metrics.pool_resize_events,
            }

    def get_connection_details(self) -> list[dict[str, object]]:
        """Get detailed metrics for each connection.

        Returns:
            List of connection metric dictionaries
        """
        with self._lock:
            return [
                {
                    "worker_id": m.worker_id,
                    "state": m.state.value,
                    "successes": m.successful_downloads,
                    "failures": m.failed_downloads,
                    "attempts": m.total_attempts,
                    "success_rate": f"{m.success_rate * 100:.1f}%",
                    "consecutive_failures": m.consecutive_failures,
                    "consecutive_successes": m.consecutive_successes,
                    "is_active": m.is_active,
                }
                for m in sorted(
                    self.metrics.connections.values(), key=lambda x: x.worker_id
                )
            ]
