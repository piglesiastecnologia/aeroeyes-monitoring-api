import secrets
import time
import uuid
from uuid import UUID


def uuid7() -> UUID:
    native_uuid7 = getattr(uuid, "uuid7", None)
    if native_uuid7 is not None:
        return native_uuid7()

    timestamp_ms = time.time_ns() // 1_000_000
    if not 0 <= timestamp_ms < 1 << 48:
        raise ValueError("UUIDv7 timestamp is outside the supported range")

    random_bits = secrets.randbits(74)
    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)

    value = (
        (timestamp_ms << 80)
        | (0b0111 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return UUID(int=value)
