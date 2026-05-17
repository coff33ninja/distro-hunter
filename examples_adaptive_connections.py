"""
Practical example: Using adaptive connection pool for downloads

This demonstrates how to integrate adaptive download connection management
into a real download workflow.
"""

from distro_hunter.connection_pool import AdaptiveConnectionPool


def example_basic_usage():
    """Example 1: Basic pool creation and metrics tracking."""
    print("=" * 60)
    print("Example 1: Basic Usage")
    print("=" * 60)

    # Create pool with reasonable defaults
    pool = AdaptiveConnectionPool(
        initial_workers=3,
        min_workers=1,
        max_workers=8,
    )

    print(f"✓ Created pool with {pool.get_current_workers()} workers")

    # Simulate some downloads
    # Worker 0: mostly successful
    for _ in range(8):
        pool.metrics.record_success(worker_id=0)
    pool.metrics.record_failure(worker_id=0)  # 1 failure

    # Worker 1: some failures
    for _ in range(3):
        pool.metrics.record_success(worker_id=1)
    pool.metrics.record_failure(worker_id=1)
    pool.metrics.record_failure(worker_id=1)

    # Worker 2: consistently failing
    pool.metrics.record_failure(worker_id=2)
    pool.metrics.record_failure(worker_id=2)
    pool.metrics.record_failure(worker_id=2)
    pool.metrics.record_failure(worker_id=2)

    print("\nPool status:")
    stats = pool.get_status_summary()
    print(f"  Workers: {stats['current_workers']}")
    print(f"  Active: {stats['active_connections']}")
    print(f"  Healthy: {stats['healthy_connections']}")
    print(f"  Failing: {stats['failing_connections']}")
    print(f"  Success rate: {stats['success_rate']*100:.1f}%")
    print(f"  Total downloads: {stats['total_downloads']}")


def example_scaling_decisions():
    """Example 2: Adaptive scaling based on health."""
    print("\n" + "=" * 60)
    print("Example 2: Adaptive Scaling Decisions")
    print("=" * 60)

    pool = AdaptiveConnectionPool(
        initial_workers=3,
        min_workers=1,
        max_workers=8,
    )

    print(f"Starting with {pool.get_current_workers()} workers")

    # Scenario: 5 workers become healthy
    print("\n→ Simulating 5 healthy connections...")
    for worker_id in range(5):
        for _ in range(10):
            pool.metrics.record_success(worker_id)

    # Check if we should scale
    should_scale, reason = pool.evaluate_scaling()
    print(f"  Should scale? {should_scale}")
    print(f"  Reason: {reason}")

    if should_scale and pool.get_current_workers() < pool.max_workers:
        new_count, reason = pool.scale_up()
        print(f"  ✓ Scaled up to {new_count} workers: {reason}")

    # Scenario: 3 connections start failing
    print("\n→ Simulating 3 workers failing...")
    for worker_id in range(3):
        for _ in range(5):
            pool.metrics.record_failure(worker_id)

    should_scale, reason = pool.evaluate_scaling()
    print(f"  Should scale? {should_scale}")
    print(f"  Reason: {reason}")

    if should_scale and pool.get_current_workers() > pool.min_workers:
        new_count, reason = pool.scale_down()
        print(f"  ✓ Scaled down to {new_count} workers: {reason}")


def example_connection_states():
    """Example 3: Connection state transitions."""
    print("\n" + "=" * 60)
    print("Example 3: Connection State Transitions")
    print("=" * 60)

    pool = AdaptiveConnectionPool()

    # Track worker 0 state over time
    print("Tracking connection states:")

    # Initially: IDLE
    metrics = pool.metrics.get_metrics(0)
    print(f"  Initial: {metrics.state.value}")

    # After successes: HEALTHY
    for _ in range(10):
        pool.metrics.record_success(0)
    metrics = pool.metrics.get_metrics(0)
    print(
        f"  After 10 successes: {metrics.state.value} (rate: {metrics.success_rate*100:.0f}%)"
    )

    # Add some failures
    for _ in range(5):
        pool.metrics.record_failure(0)
    metrics = pool.metrics.get_metrics(0)
    state_name = metrics.state.value
    print(f"  After 5 failures: {state_name} (rate: {metrics.success_rate*100:.0f}%)")

    # More failures
    for _ in range(5):
        pool.metrics.record_failure(0)
    metrics = pool.metrics.get_metrics(0)
    print(
        f"  After 10 total failures: {metrics.state.value} (rate: {metrics.success_rate*100:.0f}%)"
    )


def example_detailed_metrics():
    """Example 4: Detailed per-connection metrics."""
    print("\n" + "=" * 60)
    print("Example 4: Connection Details")
    print("=" * 60)

    pool = AdaptiveConnectionPool(initial_workers=3)

    # Simulate different worker patterns
    patterns = [
        ("stable", [(0, 8)]),  # Worker 0: 8 successes
        ("degraded", [(1, 5), (1, 3)]),  # Worker 1: 5 successes, 3 failures
        ("failing", [(2, 2), (2, 5)]),  # Worker 2: 2 successes, 5 failures
    ]

    worker_id = 0
    for pattern_name, actions in patterns:
        for wid, count in actions:
            for _ in range(count):
                if "success" in pattern_name or pattern_name == "stable":
                    if count > 3:
                        pool.metrics.record_success(worker_id)
                    else:
                        pool.metrics.record_failure(worker_id)
                else:
                    pool.metrics.record_failure(worker_id)

        worker_id += 1

    # Redo for clarity
    pool.metrics.get_metrics(0)  # stable
    for _ in range(8):
        pool.metrics.record_success(0)

    pool.metrics.get_metrics(1)  # degraded
    for _ in range(5):
        pool.metrics.record_success(1)
    for _ in range(3):
        pool.metrics.record_failure(1)

    pool.metrics.get_metrics(2)  # failing
    for _ in range(2):
        pool.metrics.record_success(2)
    for _ in range(5):
        pool.metrics.record_failure(2)

    # Display details
    print("\nConnection metrics table:")
    print("ID  │ State     │ ✓  │ ✗  │ Rate")
    print("─────┼───────────┼────┼────┼─────")

    for conn in pool.get_connection_details():
        worker_id = conn.get("worker_id")
        state = conn.get("state", "unknown")
        successes = conn.get("successes", 0)
        failures = conn.get("failures", 0)
        rate = conn.get("success_rate", "0%")

        state_emoji = {
            "healthy": "●",
            "degraded": "◐",
            "failing": "○",
            "idle": "◯",
        }.get(state, "?")

        print(
            f"{worker_id}   │ {state_emoji} {state:<6} │ {successes:>2} │ {failures:>2} │ {rate:>5}"
        )


def example_scaling_callbacks():
    """Example 5: Responding to scaling events."""
    print("\n" + "=" * 60)
    print("Example 5: Scaling Callbacks")
    print("=" * 60)

    pool = AdaptiveConnectionPool(initial_workers=3)

    scale_events = []

    def on_scale(new_count, reason):
        scale_events.append((new_count, reason))
        print(f"  🔄 {reason}")

    pool.set_scale_callback(on_scale)

    print("Simulating scaling events...")

    # Get healthy
    for i in range(3):
        for _ in range(8):
            pool.metrics.record_success(i)

    pool.scale_up()
    pool.scale_up()

    print(f"\nRecorded {len(scale_events)} scale events:")
    for i, (count, reason) in enumerate(scale_events, 1):
        print(f"  {i}. {reason}")


if __name__ == "__main__":
    example_basic_usage()
    example_scaling_decisions()
    example_connection_states()
    example_detailed_metrics()
    example_scaling_callbacks()

    print("\n" + "=" * 60)
    print("✓ All examples completed successfully!")
    print("=" * 60)
