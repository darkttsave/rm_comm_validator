"""Data recorder for CAN messages."""

import json
import os
from datetime import datetime
from typing import Optional, List
from decoder import DecodedMessage
from validator import ValidationResult


class Recorder:
    """JSONL recorder for CAN messages."""

    def __init__(self, log_dir: str = "logs"):
        """Initialize recorder."""
        self.log_dir = log_dir
        self.log_file = None
        self.file_handle = None

        # Create log directory
        os.makedirs(log_dir, exist_ok=True)

    def start(self, filename: Optional[str] = None):
        """Start recording to a new log file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comm_{timestamp}.jsonl"

        self.log_file = os.path.join(self.log_dir, filename)
        self.file_handle = open(self.log_file, 'w', encoding='utf-8')
        print(f"Recording to: {self.log_file}")

    def stop(self):
        """Stop recording and close file."""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
            print(f"Recording stopped: {self.log_file}")

    def record(
        self,
        decoded: Optional[DecodedMessage],
        validation: Optional[List[ValidationResult]],
        can_id: int,
        dlc: int,
        raw_data: bytes,
        timestamp: float,
        direction: str = "rx"
    ):
        """
        Record a CAN frame with decoded and validation results.

        Args:
            decoded: Decoded message (None if unknown)
            validation: Validation results (None if unknown)
            can_id: CAN ID
            dlc: Data length code
            raw_data: Raw payload bytes
            timestamp: Frame timestamp
            direction: rx or tx
        """
        if not self.file_handle:
            return

        # Build record
        record = {
            "timestamp": timestamp,
            "direction": direction,
            "can_id": f"0x{can_id:X}",
            "dlc": dlc,
            "raw": raw_data.hex(' ').upper()
        }

        if decoded:
            record["message"] = decoded.message_name
            record["valid"] = validation is not None and all(v.passed for v in validation)
            record["fields"] = decoded.fields

            if validation:
                record["validation"] = [
                    {
                        "check": v.check,
                        "passed": v.passed,
                        "message": v.message
                    }
                    for v in validation
                ]
        else:
            record["message"] = "unknown"
            record["valid"] = False

        # Write JSON line
        self.file_handle.write(json.dumps(record) + '\n')
        self.file_handle.flush()

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
