"""CRC algorithms for serial protocols."""


def tongji_crc16(data: bytes) -> int:
    """
    Tongji CRC16 algorithm.

    Based on Tongji sp_vision_25 tools/crc.cpp implementation.

    Parameters:
    - init = 0xFFFF
    - reflected polynomial = 0x8408
    - no final xor

    Args:
        data: Bytes to calculate CRC over (excluding CRC field itself)

    Returns:
        CRC16 value as unsigned 16-bit integer
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc = crc >> 1

    return crc & 0xFFFF
