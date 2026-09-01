"""Custom exception hierarchy for the rtc3231 package.

All exceptions inherit from RtcError, so callers that don't care about
the specific failure mode can catch just that one base class.
"""


class RtcError(Exception):
    """Base class for every exception raised by rtc3231."""


class CrcError(RtcError):
    """Raised when a received frame's CRC16 does not match the calculated value."""


class RtcTimeoutError(RtcError):
    """Raised when a serial read times out.

    Deliberately NOT named ``TimeoutError``. Python's built-in
    ``TimeoutError`` is a subclass of ``OSError``, and ``serial.Serial()``
    can raise it directly when a connection fails. If our exception
    reused that name, ``except (TimeoutError, ...)`` would only ever
    catch our custom one -- the built-in would slip through unhandled
    and crash ``auto_detect()`` instead of being caught and retried.
    """


class FrameError(RtcError):
    """Raised when a frame is malformed: bad SOF, bad length, unsupported
    protocol version, or an unexpected CMD value."""


class DeviceError(RtcError):
    """Raised when the Arduino explicitly reports failure via CMD_ERR
    with FLAG_IS_ERROR set in the response flags.

    Distinct from FrameError: this means the peer understood the request
    and validly answered "no" (e.g. unknown CMD, payload too short) --
    not that the response was malformed or of an unexpected type. The
    failure is deterministic, so callers should not retry the identical
    request; runner.py's ``except (CrcError, RtcTimeoutError)`` retry
    clause deliberately does not catch this, same as it doesn't catch
    FrameError.

    Firmware built before this flag existed always sends flags=0x00,
    even on CMD_ERR, so this is never raised against older boards --
    callers fall through to the pre-existing FrameError check instead.
    """