"""Open native ESP USB without separate POSIX DTR/RTS transitions."""
import os
import struct
import sys

import serial


def set_modem_lines(link):
    """One control-line update, preserving all other modem bits.

    On macOS, pySerial's separate DTR/RTS ioctls can pass through the ESP's
    reset combination during open, even when both were configured False.
    TIOCMSET updates the pair together, as in esptool's Unix tight strategy.
    """
    import fcntl
    import termios
    # pySerial invokes these hooks during open(), before fileno() is enabled.
    descriptor=link.fd
    try:
        state=struct.unpack('I',fcntl.ioctl(descriptor,termios.TIOCMGET,struct.pack('I',0)))[0]
        state &= ~(termios.TIOCM_DTR|termios.TIOCM_RTS)
        if link.dtr:state |= termios.TIOCM_DTR
        if link.rts:state |= termios.TIOCM_RTS
        fcntl.ioctl(descriptor,termios.TIOCMSET,struct.pack('I',state))
    except OSError as error:
        # pySerial otherwise silently ignores ENOTTY/EINVAL during open. Do
        # not fall back to the reset-inducing sequential path on this device.
        raise serial.SerialException('Combined DTR/RTS update failed: '+str(error)) from error


class AtomicSerial(serial.Serial):
    def _update_dtr_state(self):set_modem_lines(self)
    def _update_rts_state(self):set_modem_lines(self)


def native_usb_port(port):
    from serial.tools import list_ports
    return any(p.device==port and p.vid==0x303a and p.pid==0x1001
               for p in list_ports.comports())


def select_policy(port,policy='auto'):
    if policy not in ('auto','legacy','atomic'):raise ValueError('Unknown serial opening policy')
    if policy=='auto':return 'atomic' if sys.platform=='darwin' and native_usb_port(port) else 'legacy'
    return policy


def open_port(port, policy='auto', **kwargs):
    policy=select_policy(port,policy)
    if policy=='atomic' and os.name!='posix':raise ValueError('Atomic modem updates require POSIX')
    link=(AtomicSerial if policy=='atomic' else serial.Serial)(**kwargs)
    link.dtr=link.rts=False
    link.port=port
    link.open()
    return link
