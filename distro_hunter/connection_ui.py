"""TUI component for displaying connection pool status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Static

from distro_hunter.connection_pool import AdaptiveConnectionPool, ConnectionState


STATE_DISPLAY: dict[ConnectionState, tuple[str, str]] = {
    ConnectionState.HEALTHY: ("●", "green"),
    ConnectionState.DEGRADED: ("◐", "yellow"),
    ConnectionState.FAILING: ("○", "red"),
    ConnectionState.IDLE: ("◯", "cyan"),
}


def _coerce_connection_state(value: object) -> ConnectionState | None:
    """Convert pool detail values into a typed connection state."""
    if isinstance(value, ConnectionState):
        return value
    if isinstance(value, str):
        try:
            return ConnectionState(value)
        except ValueError:
            return None
    return None


class ConnectionPoolStatus(Static):
    """Display current connection pool status and health metrics."""

    connection_pool: AdaptiveConnectionPool | None = reactive(None)

    DEFAULT_CSS = """
    ConnectionPoolStatus {
        height: auto;
        border: solid $accent;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, pool: AdaptiveConnectionPool | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.connection_pool = pool

    def render(self) -> str:
        """Render connection pool status."""
        if not self.connection_pool:
            return "⊙ Connection Pool: Not initialized"

        stats = self.connection_pool.get_status_summary()
        current_workers = stats.get("current_workers", 0)
        active = stats.get("active_connections", 0)
        healthy = stats.get("healthy_connections", 0)
        failing = stats.get("failing_connections", 0)
        success_rate = stats.get("success_rate", 1.0)
        total = stats.get("total_downloads", 0)

        # Derive an overall state for the pool using the same enum as the metrics model.
        if failing > 0:
            overall_state = ConnectionState.FAILING
        elif active == 0:
            overall_state = ConnectionState.IDLE
        elif healthy < current_workers:
            overall_state = ConnectionState.DEGRADED
        else:
            overall_state = ConnectionState.HEALTHY

        health_icon, health_color = STATE_DISPLAY[overall_state]

        # Build status line
        status = f"[{health_color}]{health_icon}[/] "
        status += (
            f"Connections: {current_workers} (active: {active}, healthy: {healthy}"
        )
        if failing > 0:
            status += f", [red]failing: {failing}[/red]"
        status += f") | Success: {success_rate*100:.1f}% ({total} total)"

        return status


class ConnectionPoolDetails(Static):
    """Display detailed metrics for each connection in the pool."""

    connection_pool: AdaptiveConnectionPool | None = reactive(None)

    DEFAULT_CSS = """
    ConnectionPoolDetails {
        height: auto;
        border: solid $accent;
        padding: 1;
        background: $surface;
    }
    """

    def __init__(self, pool: AdaptiveConnectionPool | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.connection_pool = pool

    def render(self) -> str:
        """Render detailed connection metrics."""
        if not self.connection_pool:
            return ""

        details = self.connection_pool.get_connection_details()
        if not details:
            return "No connection metrics yet"

        lines = ["Connection Details:"]
        lines.append("ID  │ State     │ ✓      │ ✗    │ Rate")
        lines.append("─────┼───────────┼────────┼──────┼─────────")

        for conn in details:
            worker_id = conn.get("worker_id", "?")
            state = _coerce_connection_state(conn.get("state"))
            successes = conn.get("successes", 0)
            failures = conn.get("failures", 0)
            rate = conn.get("success_rate", "0%")

            state_icon, state_color = STATE_DISPLAY.get(state, ("?", "dim"))
            state_label = state.value if state else "unknown"
            state_cell = f"[{state_color}]{state_icon}[/] {state_label:<8}"
            row = (
                f"{worker_id:<3} │ {state_cell} │ {successes:>5} │ "
                f"{failures:>4} │ {rate:>6}"
            )

            lines.append(row)

        return "\n".join(lines)


class PoolScalingIndicator(Static):
    """Show when pool is scaling up/down with reason."""

    connection_pool: AdaptiveConnectionPool | None = reactive(None)
    last_message: str = reactive("Ready")

    DEFAULT_CSS = """
    PoolScalingIndicator {
        height: 1;
        border: solid $accent;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, pool: AdaptiveConnectionPool | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.connection_pool = pool
        if pool:
            pool.set_scale_callback(self._on_pool_scale)

    def _on_pool_scale(self, new_worker_count: int, reason: str) -> None:
        """Called when pool scales."""
        self.last_message = f"[cyan]{reason}[/cyan]"

    def render(self) -> str:
        """Render scaling indicator."""
        return f"Pool: {self.last_message}"


class ConnectionPoolPanel(Container):
    """Group connection pool widgets into one reusable layout container."""

    connection_pool: AdaptiveConnectionPool | None = reactive(None)

    DEFAULT_CSS = """
    ConnectionPoolPanel {
        height: auto;
        layout: vertical;
    }
    """

    def __init__(self, pool: AdaptiveConnectionPool | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.connection_pool = pool

    def compose(self) -> ComposeResult:
        """Compose the pool status widgets inside a dedicated container."""
        yield ConnectionPoolStatus(self.connection_pool)
        yield PoolScalingIndicator(self.connection_pool)
        yield ConnectionPoolDetails(self.connection_pool)
