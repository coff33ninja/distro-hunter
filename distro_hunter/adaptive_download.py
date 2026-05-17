"""Download manager with adaptive connection pool integration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from distro_hunter.connection_pool import AdaptiveConnectionPool

if TYPE_CHECKING:
    from distro_hunter.core import DiscoverySelection, DownloadResult


class AdaptiveDownloadManager:
    """Wraps downloads with adaptive connection pool management.

    This manager automatically scales the download thread pool based on:
    - Success rate of individual connections
    - Number of failing connections
    - Overall pool health
    """

    def __init__(
        self,
        base_download_fn,
        initial_workers: int = 3,
        min_workers: int = 1,
        max_workers: int = 8,
    ) -> None:
        """Initialize adaptive download manager.

        Args:
            base_download_fn: Function to call for each download: (discovery) -> DownloadResult
            initial_workers: Starting number of concurrent downloads
            min_workers: Minimum connections
            max_workers: Maximum connections
        """
        self.base_download_fn = base_download_fn
        self.pool = AdaptiveConnectionPool(
            initial_workers=initial_workers,
            min_workers=min_workers,
            max_workers=max_workers,
        )
        self.should_cancel = False

    def set_scale_callback(self, callback):
        """Set callback for pool scaling events."""
        self.pool.set_scale_callback(callback)

    def download_all(
        self,
        discoveries: list[DiscoverySelection],
        should_cancel_fn=None,
    ) -> list[DownloadResult]:
        """Download all discoveries with adaptive connection management.

        Args:
            discoveries: List of DiscoverySelection items to download
            should_cancel_fn: Optional function that returns True to cancel

        Returns:
            List of DownloadResult objects
        """
        results: list[DownloadResult] = []

        # Flatten into executable tasks
        tasks_by_id = {}
        for i, discovery in enumerate(discoveries):
            if discovery.selected is None:
                continue
            tasks_by_id[i] = discovery

        if not tasks_by_id:
            return results

        # Start with initial worker count
        current_workers = self.pool.get_current_workers()

        with ThreadPoolExecutor(
            max_workers=current_workers, thread_name_prefix="download-adaptive"
        ) as executor:
            # Submit initial batch
            futures_to_id = {}
            pending_ids = list(tasks_by_id.keys())

            # Fill initial worker slots
            while pending_ids and len(futures_to_id) < current_workers:
                task_id = pending_ids.pop(0)
                discovery = tasks_by_id[task_id]
                future = executor.submit(
                    self._download_with_tracking, task_id, discovery
                )
                futures_to_id[future] = task_id

            # Process completions and adaptively scale
            while futures_to_id:
                if should_cancel_fn and should_cancel_fn():
                    break

                # Wait for next completion
                for future in as_completed(futures_to_id):
                    task_id = futures_to_id.pop(future)

                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        # Record failure for adaptive scaling
                        self.pool.metrics.record_failure(
                            task_id % self.pool.get_current_workers()
                        )

                    # Evaluate and potentially scale
                    should_scale, reason = self.pool.evaluate_scaling()
                    if should_scale:
                        # Check if we should scale up or down
                        if self.pool.metrics.failing_connections >= 3:
                            self.pool.scale_down()
                        elif self.pool.metrics.healthy_connections >= 5:
                            self.pool.scale_up()

                    # Submit next pending task if available
                    if pending_ids:
                        task_id = pending_ids.pop(0)
                        discovery = tasks_by_id[task_id]
                        future = executor.submit(
                            self._download_with_tracking, task_id, discovery
                        )
                        futures_to_id[future] = task_id

                    break  # Process one completion at a time

        return results

    def _download_with_tracking(
        self, task_id: int, discovery: DiscoverySelection
    ) -> DownloadResult:
        """Download and track success/failure for connection pool metrics.

        Args:
            task_id: Identifier for this task
            discovery: The discovery selection to download

        Returns:
            DownloadResult
        """
        worker_id = task_id % self.pool.get_current_workers()

        try:
            result = self.base_download_fn(discovery)

            # Track success if download succeeded and no skip reason
            if result.downloaded and not result.skipped_reason:
                self.pool.metrics.record_success(worker_id)
            else:
                self.pool.metrics.record_failure(worker_id)

            return result
        except Exception:
            self.pool.metrics.record_failure(worker_id)
            raise

    def get_pool_status(self) -> dict[str, object]:
        """Get current pool status summary."""
        return self.pool.get_status_summary()

    def get_connection_details(self) -> list[dict[str, object]]:
        """Get detailed metrics for each connection."""
        return self.pool.get_connection_details()
