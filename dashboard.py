"""Real-time terminal dashboard using Rich."""

import time
from typing import Dict, Optional, List
from collections import defaultdict, deque
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

from decoder import DecodedMessage
from validator import ValidationResult


class Dashboard:
    """Real-time terminal dashboard."""

    def __init__(self, protocol_name: str, interface: str):
        """Initialize dashboard."""
        self.protocol_name = protocol_name
        self.interface = interface
        self.console = Console()

        # Statistics
        self.start_time = time.time()
        self.total_frames = 0
        self.valid_frames = 0
        self.invalid_frames = 0
        self.unknown_frames = 0

        # Per-message state
        self.latest_by_message: Dict[str, DecodedMessage] = {}
        self.validation_by_message: Dict[str, List[ValidationResult]] = {}

        # Frame rate tracking
        self.frame_times = deque(maxlen=100)
        self.frames_by_id: Dict[int, deque] = defaultdict(lambda: deque(maxlen=50))

        # Recent events
        self.events = deque(maxlen=10)

    def update(
        self,
        decoded: Optional[DecodedMessage],
        validation: Optional[List[ValidationResult]],
        can_id: int,
        raw_data: bytes
    ):
        """Update dashboard with new frame."""
        self.total_frames += 1
        self.frame_times.append(time.time())
        self.frames_by_id[can_id].append(time.time())

        if decoded is None:
            self.unknown_frames += 1
            self.events.append(f"{self._current_time()}  Unknown CAN ID 0x{can_id:X}")
        else:
            # Check validation
            if validation and all(v.passed for v in validation):
                self.valid_frames += 1
            else:
                self.invalid_frames += 1
                # Log validation failures
                if validation:
                    for v in validation:
                        if not v.passed:
                            self.events.append(
                                f"{self._current_time()}  {decoded.message_name}: {v.check} failed"
                            )

            # Update latest message state
            self.latest_by_message[decoded.message_name] = decoded
            if validation:
                self.validation_by_message[decoded.message_name] = validation

    def _current_time(self) -> str:
        """Get current time string."""
        return time.strftime("%H:%M:%S")

    def _get_runtime(self) -> str:
        """Get runtime string."""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _get_frame_rate(self) -> float:
        """Calculate overall frame rate."""
        if len(self.frame_times) < 2:
            return 0.0
        elapsed = self.frame_times[-1] - self.frame_times[0]
        if elapsed == 0:
            return 0.0
        return len(self.frame_times) / elapsed

    def _get_rate_by_id(self, can_id: int) -> float:
        """Calculate frame rate for specific CAN ID."""
        times = self.frames_by_id[can_id]
        if len(times) < 2:
            return 0.0
        elapsed = times[-1] - times[0]
        if elapsed == 0:
            return 0.0
        return len(times) / elapsed

    def generate_layout(self) -> Layout:
        """Generate Rich layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="events", size=12)
        )

        # Header
        header_text = Text()
        header_text.append("RM Communication Validator\n", style="bold cyan")
        header_text.append(f"Protocol: {self.protocol_name}  |  Interface: {self.interface}", style="dim")
        layout["header"].update(Panel(header_text, border_style="cyan"))

        # Body - split into stats and messages
        layout["body"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="messages", ratio=2)
        )

        # Statistics table
        stats_table = Table(show_header=False, box=None, padding=(0, 1))
        stats_table.add_column("Metric", style="bold")
        stats_table.add_column("Value")

        stats_table.add_row("Runtime", self._get_runtime())
        stats_table.add_row("Total Frames", str(self.total_frames))
        stats_table.add_row("Valid", f"[green]{self.valid_frames}[/green]")
        stats_table.add_row("Invalid", f"[red]{self.invalid_frames}[/red]")
        stats_table.add_row("Unknown", f"[yellow]{self.unknown_frames}[/yellow]")
        stats_table.add_row("Rate", f"{self._get_frame_rate():.1f} Hz")
        stats_table.add_row("", "")

        # Per-ID rates
        stats_table.add_row("[bold]Per CAN ID Rates[/bold]", "")
        for can_id in sorted(self.frames_by_id.keys()):
            rate = self._get_rate_by_id(can_id)
            stats_table.add_row(f"  0x{can_id:02X}", f"{rate:.1f} Hz")

        layout["stats"].update(Panel(stats_table, title="Statistics", border_style="blue"))

        # Messages panel
        messages_content = self._generate_messages_view()
        layout["messages"].update(Panel(messages_content, title="Latest Messages", border_style="green"))

        # Events panel
        events_table = Table(show_header=False, box=None, expand=True)
        events_table.add_column("Event", style="yellow")

        for event in list(self.events)[-10:]:
            events_table.add_row(event)

        layout["events"].update(Panel(events_table, title="Recent Events", border_style="yellow"))

        return layout

    def _generate_messages_view(self) -> Table:
        """Generate messages view."""
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Message", style="bold cyan")
        table.add_column("Fields")
        table.add_column("Validation", style="dim")

        for msg_name in sorted(self.latest_by_message.keys()):
            decoded = self.latest_by_message[msg_name]
            validation = self.validation_by_message.get(msg_name, [])

            # Format fields
            fields_text = ""
            for key, value in decoded.fields.items():
                if isinstance(value, float):
                    fields_text += f"{key}={value:.4f}\n"
                else:
                    fields_text += f"{key}={value}\n"

            # Format validation
            val_text = ""
            all_pass = True
            for v in validation:
                if v.passed:
                    val_text += f"[green]✓[/green] {v.check}\n"
                else:
                    val_text += f"[red]✗[/red] {v.check}\n"
                    all_pass = False

            # Add row with color coding
            msg_style = "green" if all_pass else "red"
            table.add_row(
                f"[{msg_style}]{msg_name}[/{msg_style}]\n0x{decoded.can_id:02X} DLC={decoded.dlc}",
                fields_text.strip(),
                val_text.strip()
            )

        return table

    def run_live(self, update_interval: float = 0.1):
        """
        Run live dashboard (for testing).

        Args:
            update_interval: Screen refresh interval in seconds
        """
        with Live(self.generate_layout(), console=self.console, refresh_per_second=10) as live:
            try:
                while True:
                    time.sleep(update_interval)
                    live.update(self.generate_layout())
            except KeyboardInterrupt:
                pass
