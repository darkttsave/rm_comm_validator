# Mock Serial Node

Mock Tongji Gimbal Serial Node for testing Serial Live infrastructure.

## Requirements

```bash
pip install pyserial
```

## Linux PTY Pair Testing

Create virtual serial port pair using `socat`:

```bash
# Install socat
sudo apt install socat

# Create PTY pair
socat -d -d pty,raw,echo=0 pty,raw,echo=0
```

Example output:
```
2024/09/28 10:00:00 socat[1234] N PTY is /dev/pts/3
2024/09/28 10:00:00 socat[1234] N PTY is /dev/pts/4
```

## Run Mock Gimbal

In one terminal, run the mock on one PTY:

```bash
python tools/mock_serial_node/mock_gimbal.py /dev/pts/3 --mode normal --rate 10
```

In another terminal, run the validator on the other PTY:

```bash
./start_web.sh --protocol protocols/tongji_gimbal_serial.yaml
```

Then connect Web UI to `/dev/pts/4` at 9600 baud.

## Test Modes

- `normal`: Valid frames
- `invalid_mode`: Invalid mode enum value
- `invalid_quaternion`: Non-normalized quaternion
- `bad_crc`: Corrupted CRC16

## Example

```bash
# Normal mode at 10 Hz
python tools/mock_serial_node/mock_gimbal.py /dev/pts/3 --mode normal --rate 10

# Test CRC validation
python tools/mock_serial_node/mock_gimbal.py /dev/pts/3 --mode bad_crc --rate 5
```
