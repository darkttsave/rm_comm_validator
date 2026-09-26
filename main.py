"""RM Communication Validator - Main entry point."""

import argparse
import sys
import time
from pathlib import Path

from protocol import Protocol
from decoder import Decoder
from validator import Validator
from can_transport import CANTransport
from recorder import Recorder
from dashboard import Dashboard
from rich.live import Live


class CommValidator:
    """Main validator application."""

    def __init__(self, protocol_path: str, interface: str = None):
        """Initialize validator."""
        # Load protocol
        print(f"Loading protocol: {protocol_path}")
        self.protocol = Protocol(protocol_path)

        # Override interface if specified
        if interface:
            self.protocol.transport.interface = interface

        print(f"Using interface: {self.protocol.transport.interface}")

        # Initialize components
        self.decoder = Decoder(self.protocol)
        self.validator = Validator(self.protocol)
        self.transport = CANTransport(self.protocol.transport.interface)
        self.recorder = Recorder()
        self.dashboard = Dashboard(
            protocol_name=Path(protocol_path).stem,
            interface=self.protocol.transport.interface
        )

    def monitor(self):
        """Start live monitoring mode."""
        print("Starting monitor mode...")
        print("Press Ctrl+C to stop\n")

        try:
            # Connect to CAN
            self.transport.connect()

            # Start recorder
            self.recorder.start()

            # Run live dashboard
            with Live(
                self.dashboard.generate_layout(),
                refresh_per_second=10,
                screen=True
            ) as live:
                def handle_frame(frame):
                    """Handle incoming CAN frame."""
                    # Decode
                    decoded = self.decoder.decode(
                        frame.can_id,
                        frame.data,
                        frame.timestamp
                    )

                    # Validate
                    validation = None
                    if decoded:
                        validation = self.validator.validate(decoded)

                    # Update dashboard
                    self.dashboard.update(decoded, validation, frame.can_id, frame.data)

                    # Record
                    self.recorder.record(
                        decoded,
                        validation,
                        frame.can_id,
                        frame.dlc,
                        frame.data,
                        frame.timestamp
                    )

                    # Update display
                    live.update(self.dashboard.generate_layout())

                # Start monitoring
                self.transport.start_monitoring(handle_frame)

        except KeyboardInterrupt:
            print("\nStopping...")
        except Exception as e:
            print(f"Error: {e}")
            return 1
        finally:
            self.transport.disconnect()
            self.recorder.stop()

        return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RM Communication Validator - CAN protocol validation tool"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Live monitoring mode')
    monitor_parser.add_argument(
        '--protocol',
        required=True,
        help='Protocol YAML file path'
    )
    monitor_parser.add_argument(
        '--interface',
        help='CAN interface (overrides protocol file)'
    )

    # Web command
    web_parser = subparsers.add_parser('web', help='Web UI mode')
    web_parser.add_argument(
        '--protocol',
        default='protocols/tongji_sentry.yaml',
        help='Protocol YAML file path (default: protocols/tongji_sentry.yaml)'
    )
    web_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host address (default: 127.0.0.1)'
    )
    web_parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port number (default: 5000)'
    )

    args = parser.parse_args()

    if args.command == 'monitor':
        validator = CommValidator(args.protocol, args.interface)
        return validator.monitor()
    elif args.command == 'web':
        # Import web_app here to avoid loading Flask if not needed
        from web_app import run_web
        run_web(args.protocol, args.host, args.port)
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
