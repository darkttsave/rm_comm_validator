"""Protocol registry for runtime protocol switching."""

import os
from pathlib import Path
from typing import List, Dict
import yaml


class ProtocolRegistry:
    """
    Registry of available protocols loaded from protocols/*.yaml.

    Provides a whitelist of protocols that can be loaded at runtime,
    preventing arbitrary file path injection from the Web UI.
    """

    def __init__(self, protocols_dir=None):
        if protocols_dir is None:
            protocols_dir = Path(__file__).parent / 'protocols'
        self.protocols_dir = Path(protocols_dir)
        self._protocols = []
        self._load_registry()

    def _load_registry(self):
        """Scan protocols directory and build registry."""
        self._protocols = []

        if not self.protocols_dir.exists():
            return

        for yaml_file in self.protocols_dir.glob('*.yaml'):
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)

                # Extract transport type from config
                transport_type = config.get('transport', {}).get('type', 'unknown')

                # Build protocol entry
                protocol_id = yaml_file.stem
                display_name = self._make_display_name(protocol_id, config)

                self._protocols.append({
                    'id': protocol_id,
                    'name': display_name,
                    'transport': transport_type,
                    'path': str(yaml_file)
                })
            except Exception as e:
                # Skip malformed protocol files
                print(f"Warning: Failed to load protocol {yaml_file.name}: {e}")
                continue

    def _make_display_name(self, protocol_id, config):
        """Generate a human-readable display name from protocol ID."""
        # Try to extract from config metadata if present
        if 'metadata' in config and 'name' in config['metadata']:
            return config['metadata']['name']

        # Otherwise, generate from filename
        # tongji_sentry -> Tongji Sentry CAN
        # tongji_gimbal_serial -> Tongji Gimbal Serial
        parts = protocol_id.split('_')
        capitalized = [p.capitalize() for p in parts]
        name = ' '.join(capitalized)

        # Add transport suffix if not already present
        transport = config.get('transport', {}).get('type', '')
        if transport == 'socketcan' and 'can' not in name.lower():
            name += ' CAN'
        elif transport == 'serial' and 'serial' not in name.lower():
            name += ' Serial'

        return name

    def get_all(self) -> List[Dict]:
        """Get all registered protocols."""
        return self._protocols.copy()

    def get_by_transport(self, transport: str) -> List[Dict]:
        """Get protocols filtered by transport type."""
        return [p for p in self._protocols if p['transport'] == transport]

    def get_by_id(self, protocol_id: str) -> Dict:
        """Get a specific protocol by ID."""
        for p in self._protocols:
            if p['id'] == protocol_id:
                return p.copy()
        return None

    def get_path(self, protocol_id: str) -> str:
        """Get the filesystem path for a protocol ID (safe lookup)."""
        protocol = self.get_by_id(protocol_id)
        if protocol:
            return protocol['path']
        return None
