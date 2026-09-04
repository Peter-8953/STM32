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


class StaleResponseError(RtcError):
    """Raised by DS3231._recv_matching() when repeated responses don't
    match the SEQ of the request that was just sent, even after
    discarding a bounded number of stale frames first.

    Most likely cause: a previous request timed out (RtcTimeoutError),
    runner.py's retry sent a brand new request with a new SEQ, but the
    late response to the OLD request arrives on the wire first and gets
    read before the real answer to the new one. Without this check, that
    stale frame would silently be accepted as the answer to the current
    request -- wrong data written to the DB, no error raised anywhere.

    Deliberately NOT added to runner.py's ``except (CrcError,
    RtcTimeoutError)`` retry clause: _recv_matching() already discards a
    few stale frames internally before giving up, so by the time this is
    raised, retrying blindly again at the runner level risks masking a
    more persistent problem rather than fixing a one-off timing glitch --
    same reasoning as why FrameError isn't retried there either.
    """