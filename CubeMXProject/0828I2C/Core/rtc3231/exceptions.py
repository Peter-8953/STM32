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


class DeviceI2CError(DeviceError):
    """Raised specifically when the Arduino reports ERR_I2C_FAILURE via
    CMD_ERR: it tried to talk to the DS3231 over I2C for this request and
    that specific transaction failed (bus contention, DS3231 momentarily
    unresponsive, a loose wire, etc.).

    A DeviceError, but semantically different from the base class's other
    codes (ERR_UNKNOWN_CMD / ERR_PAYLOAD_TOO_SHORT): those mean the
    request itself was malformed, and retrying the identical request
    always fails the same way. An I2C bus error is plausibly transient --
    retrying the same request a moment later might just succeed. So
    unlike plain DeviceError, this IS added to runner.py's ``except
    (CrcError, RtcTimeoutError, DeviceI2CError)`` retry clause.

    (Note: retrying only re-sends the request over the existing USB/serial
    link -- it doesn't reset the STM32's I2C peripheral or power-cycle the
    DS3231. If the I2C bus is genuinely, persistently stuck rather than
    just glitching, retries will keep failing the same way and this will
    still correctly run out MAX_RETRY/MAX_RECONNECTS and stop, same as
    any other persistent failure -- it just won't fix a truly broken I2C
    connection by itself.)
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