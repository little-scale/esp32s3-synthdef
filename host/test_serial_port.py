"""Modem-line opening regression without hardware or serial I/O."""
import errno
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import serial
import serial_port as tool


class SerialPortTests(unittest.TestCase):
    def test_all_line_combinations_update_once_and_preserve_other_bits(self):
        import termios
        for dtr,rts in ((False,False),(False,True),(True,False),(True,True)):
            link=SimpleNamespace(fd=42,dtr=dtr,rts=rts)
            with self.subTest(dtr=dtr,rts=rts), \
                 patch('fcntl.ioctl',side_effect=[struct.pack('I',0x80|termios.TIOCM_DTR|termios.TIOCM_RTS),0]) as ioctl:
                tool.set_modem_lines(link)
                expected=0x80|(termios.TIOCM_DTR if dtr else 0)|(termios.TIOCM_RTS if rts else 0)
                self.assertEqual(ioctl.call_args_list[1].args,(42,termios.TIOCMSET,struct.pack('I',expected)))
                self.assertEqual(ioctl.call_count,2)  # One GET and one SET, no separate bit clears.

    def test_atomic_hooks_use_the_same_combined_path(self):
        link=SimpleNamespace()
        with patch.object(tool,'set_modem_lines') as combined:
            tool.AtomicSerial._update_dtr_state(link);tool.AtomicSerial._update_rts_state(link)
        self.assertEqual(combined.call_count,2)
        self.assertTrue(all(call.args==(link,) for call in combined.call_args_list))

    def test_unsupported_atomic_update_is_not_silently_ignored(self):
        with patch('fcntl.ioctl',side_effect=OSError(errno.ENOTTY,'unsupported')):
            with self.assertRaises(serial.SerialException) as error:
                tool.set_modem_lines(SimpleNamespace(fd=42,dtr=False,rts=False))
        self.assertIsNone(error.exception.errno)

    def test_auto_targets_only_macos_native_esp_usb(self):
        with patch.object(tool.sys,'platform','darwin'),patch.object(tool,'native_usb_port',return_value=True):
            self.assertEqual(tool.select_policy('native'),'atomic')
        with patch.object(tool.sys,'platform','darwin'),patch.object(tool,'native_usb_port',return_value=False):
            self.assertEqual(tool.select_policy('uart'),'legacy')
        for platform in ('linux','win32'):
            with patch.object(tool.sys,'platform',platform),patch.object(tool,'native_usb_port') as detect:
                self.assertEqual(tool.select_policy('port'),'legacy');detect.assert_not_called()

    def test_port_detection_checks_exact_path_vid_and_pid(self):
        rows=[SimpleNamespace(device='native',vid=0x303a,pid=0x1001),
              SimpleNamespace(device='uart',vid=0x10c4,pid=0xea60)]
        with patch('serial.tools.list_ports.comports',return_value=rows):
            self.assertTrue(tool.native_usb_port('native'));self.assertFalse(tool.native_usb_port('uart'))
            self.assertFalse(tool.native_usb_port('missing'))

    def test_open_sets_both_states_before_opening(self):
        link=SimpleNamespace(dtr=True,rts=True,port=None)
        link.open=Mock(side_effect=lambda:self.assertEqual((link.dtr,link.rts,link.port),(False,False,'port')))
        with patch.object(tool,'AtomicSerial',return_value=link) as cls:
            result=tool.open_port('port',policy='atomic',baudrate=115200)
        self.assertIs(result,link);cls.assert_called_once_with(baudrate=115200);link.open.assert_called_once()

    def test_legacy_factory_remains_available(self):
        link=SimpleNamespace(open=Mock())
        with patch.object(tool.serial,'Serial',return_value=link) as cls:
            self.assertIs(tool.open_port('uart',policy='legacy',timeout=.1),link)
        cls.assert_called_once_with(timeout=.1)
        with self.assertRaises(ValueError):tool.select_policy('port','unknown')


if __name__=='__main__':unittest.main()
