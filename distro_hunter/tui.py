from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, ProgressBar, RichLog, SelectionList, Static

from distro_hunter.backup import create_source_backup
from distro_hunter.config import load_settings
from distro_hunter.core import DistroHunter, DiscoverySelection, discovery_rows
from distro_hunter.plugin_loader import PluginSpec
from distro_hunter.utils import human_size


def filter_plugins(plugins: list[PluginSpec], query: str) -> list[PluginSpec]:
    terms = [term.strip().lower() for term in query.split() if term.strip()]
    if not terms:
        return list(plugins)

    filtered: list[PluginSpec] = []
    for plugin in plugins:
        metadata = plugin.resolved_metadata()
        haystack = " ".join(
            [
                plugin.name,
                plugin.slug,
                metadata.family,
                metadata.architecture or "",
                metadata.edition_type or "",
                metadata.source_kind or "",
            ]
        ).lower()
        if all(term in haystack for term in terms):
            filtered.append(plugin)
    return filtered


def build_plugin_options(plugins: list[PluginSpec], selected_slugs: set[str]) -> list[tuple[str, str, bool]]:
    return [
        (f"{plugin.name} [{plugin.slug}]", plugin.slug, plugin.slug in selected_slugs)
        for plugin in plugins
    ]


def ordered_selected_plugin_slugs(plugins: list[PluginSpec], selected_slugs: set[str]) -> list[str]:
    return [plugin.slug for plugin in plugins if plugin.slug in selected_slugs]


def plugin_filter_summary(query: str, *, total: int, visible: int, selected: int) -> str:
    if query:
        return f'Filter "{query}": showing {visible} of {total} plugins, selected {selected} total'
    return f"Showing {visible} of {total} plugins, selected {selected} total"


class DistroHunterApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        height: 1fr;
        layout: horizontal;
    }

    #plugin-panel {
        width: 40;
        min-width: 32;
        margin: 0 1 1 1;
    }

    #plugin-filter {
        margin-bottom: 1;
    }

    #plugin-summary {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    #plugins {
        border: round $accent;
        height: 1fr;
    }

    #right {
        width: 1fr;
        margin: 0 1 1 0;
    }

    #status {
        height: 3;
        padding: 1;
        border: round $accent;
        margin-bottom: 1;
    }

    #bars {
        border: round $accent;
        padding: 1;
        margin-bottom: 1;
    }

    #log {
        height: 1fr;
        border: round $accent;
    }

    #controls {
        height: auto;
        padding: 0 1 1 1;
    }

    Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("/", "focus_filter", "Filter"),
        ("escape", "clear_filter", "Clear Filter"),
        ("a", "select_all", "Select All"),
        ("x", "clear_all", "Clear"),
        ("d", "discover", "Discover"),
        ("r", "run", "Run"),
        ("y", "dry_run", "Dry Run"),
        ("c", "cancel", "Cancel"),
        ("b", "backup", "Backup"),
    ]

    def __init__(self, config_path: str) -> None:
        super().__init__()
        self.config_path = config_path
        self.settings = load_settings(config_path)
        self.hunter = DistroHunter(self.settings)
        self._all_plugins = self.hunter.list_plugins()
        self._selected_plugin_slugs = {plugin.slug for plugin in self._all_plugins}
        self._filter_query = ""
        self._rebuilding_plugin_list = False
        self._busy = False
        self._busy_mode: str | None = None
        self._cancel_event: Event | None = None

    def compose(self) -> ComposeResult:
        plugin_options = build_plugin_options(self._visible_plugins(), self._selected_plugin_slugs)
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="plugin-panel"):
                yield Input(placeholder="Filter plugins by name or slug", id="plugin-filter")
                yield Static("", id="plugin-summary")
                yield SelectionList(*plugin_options, id="plugins")
            with Vertical(id="right"):
                yield Static("Ready. Select the builds you want, then discover or run.", id="status")
                with Vertical(id="bars"):
                    yield Static("Overall progress", id="overall-label")
                    yield ProgressBar(total=1, id="overall-progress")
                    yield Static("File progress", id="file-label")
                    yield ProgressBar(total=1, id="file-progress")
                yield RichLog(id="log", wrap=True, markup=False, highlight=True)
        with Horizontal(id="controls"):
            yield Button("Select All", id="select-all")
            yield Button("Clear", id="clear-all")
            yield Button("Discover", id="discover")
            yield Button("Dry Run", id="dry-run")
            yield Button("Run", id="run")
            yield Button("Cancel", id="cancel", disabled=True)
            yield Button("Backup", id="backup")
            yield Button("Quit", id="quit")
        yield Footer()

    def on_mount(self) -> None:
        self._log(f"Loaded config: {self.settings.config_path}")
        self._log(f"Enabled plugins: {len(self._all_plugins)}")
        for warning in self.hunter.startup_warnings():
            self._log(f"Startup warning: {warning}")
        self._update_plugin_summary()

    def action_select_all(self) -> None:
        visible_slugs = {plugin.slug for plugin in self._visible_plugins()}
        self._selected_plugin_slugs.update(visible_slugs)
        self.query_one(SelectionList).select_all()
        self._update_plugin_summary()

    def action_clear_all(self) -> None:
        visible_slugs = {plugin.slug for plugin in self._visible_plugins()}
        self._selected_plugin_slugs.difference_update(visible_slugs)
        self.query_one(SelectionList).deselect_all()
        self._update_plugin_summary()

    def action_focus_filter(self) -> None:
        self.query_one("#plugin-filter", Input).focus()

    def action_clear_filter(self) -> None:
        filter_input = self.query_one("#plugin-filter", Input)
        if filter_input.value:
            filter_input.value = ""
        else:
            self.query_one(SelectionList).focus()

    def action_discover(self) -> None:
        self._launch("discover")

    def action_run(self) -> None:
        self._launch("run")

    def action_dry_run(self) -> None:
        self._launch("dry-run")

    def action_backup(self) -> None:
        self._launch("backup")

    def action_cancel(self) -> None:
        if not self._busy or self._cancel_event is None:
            return
        if self._busy_mode == "backup":
            return
        if self._cancel_event.is_set():
            return
        self._cancel_event.set()
        mode = self._busy_mode or "job"
        self._set_status(f"Cancellation requested for {mode}; finishing the current step...")
        self._log(f"Cancellation requested for {mode}; waiting for the current step to finish cleanly.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "select-all":
            self.action_select_all()
        elif button_id == "clear-all":
            self.action_clear_all()
        elif button_id == "discover":
            self.action_discover()
        elif button_id == "dry-run":
            self.action_dry_run()
        elif button_id == "run":
            self.action_run()
        elif button_id == "cancel":
            self.action_cancel()
        elif button_id == "backup":
            self.action_backup()
        elif button_id == "quit":
            self.exit()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "plugin-filter":
            return
        if not self._rebuilding_plugin_list:
            self._sync_selected_from_widget()
        self._filter_query = event.value
        self._rebuild_plugin_list()

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        if event.selection_list.id != "plugins" or self._rebuilding_plugin_list:
            return
        self._sync_selected_from_widget()
        self._update_plugin_summary()

    def _visible_plugins(self) -> list[PluginSpec]:
        return filter_plugins(self._all_plugins, self._filter_query)

    def _rebuild_plugin_list(self) -> None:
        selection_list = self.query_one(SelectionList)
        self._rebuilding_plugin_list = True
        try:
            selection_list.clear_options()
            selection_list.add_options(build_plugin_options(self._visible_plugins(), self._selected_plugin_slugs))
        finally:
            self._rebuilding_plugin_list = False
        self._update_plugin_summary()

    def _sync_selected_from_widget(self) -> None:
        visible_slugs = {plugin.slug for plugin in self._visible_plugins()}
        current_selected = set(self.query_one(SelectionList).selected)
        self._selected_plugin_slugs.difference_update(visible_slugs)
        self._selected_plugin_slugs.update(current_selected)

    def _update_plugin_summary(self) -> None:
        self.query_one("#plugin-summary", Static).update(
            plugin_filter_summary(
                self._filter_query,
                total=len(self._all_plugins),
                visible=len(self._visible_plugins()),
                selected=len(self._selected_plugin_slugs),
            )
        )

    def _selected_slugs(self) -> list[str]:
        return ordered_selected_plugin_slugs(self._all_plugins, self._selected_plugin_slugs)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self.query(Button):
            if button.id == "quit":
                continue
            if button.id == "cancel":
                button.disabled = (not busy) or self._busy_mode == "backup"
                continue
            button.disabled = busy
        self.query_one("#plugin-filter", Input).disabled = busy
        self.query_one(SelectionList).disabled = busy

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _log(self, message: str) -> None:
        self.query_one(RichLog).write(message)

    def _update_overall(self, *, total: int, progress: int, label: str) -> None:
        self.query_one("#overall-label", Static).update(label)
        self.query_one("#overall-progress", ProgressBar).update(total=max(total, 1), progress=progress)

    def _update_file_progress(self, downloaded: int, total: int | None, filename: str) -> None:
        label = f"{filename}: {human_size(downloaded)}"
        if total:
            label += f" / {human_size(total)}"
            self.query_one("#file-progress", ProgressBar).update(total=total, progress=min(downloaded, total))
        else:
            self.query_one("#file-progress", ProgressBar).update(total=max(downloaded, 1), progress=max(downloaded, 1))
        self.query_one("#file-label", Static).update(label)

    def _reset_file_progress(self, label: str = "File progress") -> None:
        self.query_one("#file-label", Static).update(label)
        self.query_one("#file-progress", ProgressBar).update(total=1, progress=0)

    def _launch(self, mode: str) -> None:
        if self._busy:
            self._log("A job is already running.")
            return
        asyncio.create_task(self._run_mode(mode))

    def _cancel_requested(self) -> bool:
        return bool(self._cancel_event and self._cancel_event.is_set())

    async def _run_mode(self, mode: str) -> None:
        self._busy_mode = mode
        self._cancel_event = Event()
        self._set_busy(True)
        try:
            if mode == "backup":
                await self._run_backup()
                return

            selected = self._selected_slugs()
            if not selected:
                self._set_status("No builds selected.")
                self._log("No builds selected.")
                return

            discoveries = await self._discover_selected(selected)
            if self._cancel_requested():
                self._set_status("Cancelled.")
                self._log(f"Cancelled after discovering {len(discoveries)} plugin(s).")
                return
            if mode == "discover":
                self._set_status("Discovery complete.")
                return

            await self._download_selected(discoveries, dry_run=(mode == "dry-run"))
            if self._cancel_requested():
                self._set_status("Cancelled.")
            else:
                self._set_status("Run complete.")
        finally:
            self._busy_mode = None
            self._cancel_event = None
            self._set_busy(False)

    async def _run_backup(self) -> None:
        self._set_status("Creating source backup...")
        self._update_overall(total=1, progress=0, label="Backup")
        self._reset_file_progress("Packaging source tree")
        backup_path = await asyncio.to_thread(
            create_source_backup,
            Path(self.settings.config_path).parent,
        )
        self._update_overall(total=1, progress=1, label="Backup complete")
        self._reset_file_progress("Backup complete")
        self._log(f"Backup created: {backup_path}")
        self._set_status(f"Backup created: {backup_path.name}")

    async def _discover_selected(self, selected: list[str]) -> list[DiscoverySelection]:
        self._reset_file_progress("Waiting for downloads")
        self._update_overall(total=len(selected), progress=0, label="Discovery progress")
        self._set_status(f"Discovering {len(selected)} plugin(s)...")

        def callback(discovery: DiscoverySelection, completed: int, total: int) -> None:
            row = discovery_rows([discovery])[0]
            self.call_from_thread(self._log, row)
            self.call_from_thread(
                self._set_status,
                f"Discovered {discovery.plugin.slug} ({completed}/{total})",
            )
            self.call_from_thread(
                self._update_overall,
                total=total,
                progress=completed,
                label="Discovery progress",
            )

        return await asyncio.to_thread(
            self.hunter.discover,
            selected_plugins=set(selected),
            progress_callback=callback,
            should_cancel=self._cancel_requested,
        )

    async def _download_selected(self, discoveries: list[DiscoverySelection], *, dry_run: bool) -> None:
        runnable = [discovery for discovery in discoveries if discovery.selected]
        self._update_overall(total=max(len(runnable), 1), progress=0, label="Download progress")
        if not runnable:
            self._set_status("Nothing to download.")
            self._log("Nothing to download from the current selection.")
            return

        for index, discovery in enumerate(runnable, start=1):
            if self._cancel_requested():
                self._log(f"Cancelled after processing {index - 1} of {len(runnable)} download(s).")
                return
            self._set_status(f"{'Dry run for' if dry_run else 'Downloading'} {discovery.plugin.slug} ({index}/{len(runnable)})")
            self._reset_file_progress(discovery.selected.filename or discovery.plugin.slug)

            def callback(downloaded: int, total: int | None, filename: str) -> None:
                self.call_from_thread(self._update_file_progress, downloaded, total, filename)

            result = await asyncio.to_thread(
                self.hunter.download_one,
                discovery,
                dry_run=dry_run,
                progress_callback=callback,
            )
            if result.downloaded:
                self._log(f"{result.plugin_slug}: downloaded {result.path}")
            else:
                self._log(f"{result.plugin_slug}: skipped {result.skipped_reason}")
            if result.pruned_paths:
                pruned = ", ".join(path.name for path in result.pruned_paths)
                self._log(f"{result.plugin_slug}: pruned {len(result.pruned_paths)} old file(s): {pruned}")
            if result.checksum and result.checksum.status == "verified":
                self._log(f"{result.plugin_slug}: checksum verified ({result.checksum.algorithm})")
            elif result.checksum and result.checksum.status == "unavailable" and self.settings.download.verify_checksums:
                self._log(f"{result.plugin_slug}: checksum unavailable")
            if not dry_run and result.path and result.path.exists():
                drive, copied = await asyncio.to_thread(self.hunter.sync_download_result, result)
                if drive is not None and copied:
                    self._log(f"{result.plugin_slug}: synced {len(copied)} file(s) to Ventoy at {drive}")
            self._update_overall(total=len(runnable), progress=index, label="Download progress")

        if self._cancel_requested():
            self._log("Cancellation requested; skipping Ventoy sync.")
            return
        if not dry_run:
            self._set_status("Syncing to Ventoy if available...")
            self._update_overall(total=1, progress=0, label="Ventoy sync")
            drive, copied = await asyncio.to_thread(self.hunter.sync_ventoy)
            if drive is None:
                self._log("Ventoy drive not detected; local library updated only.")
            elif copied:
                self._log(f"Ventoy synced to {drive} with {len(copied)} copied file(s).")
            else:
                self._log(f"Ventoy detected at {drive}; nothing needed copying.")
            self._update_overall(total=1, progress=1, label="Ventoy sync")


def run_tui(config_path: str) -> None:
    app = DistroHunterApp(config_path)
    app.run()
