"""JSON IPC with bounded reads for Windows mpv named pipes."""
import ctypes
import json
import os
import socket
import time

DEFAULT_PIPE = r'\\.\pipe\race-analysis'

class MpvConnection:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.sock = None
        self.buffer = b''
        self.request_id = 0

    def close(self):
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self.buffer = b''

    def connect(self):
        self.close()
        if os.name == 'nt':
            self.sock = open(self.socket_path, 'r+b', buffering=0)
        else:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(0.3)
            self.sock.connect(self.socket_path)

    def _read(self, deadline):
        if os.name != 'nt':
            return self.sock.recv(4096)
        import msvcrt
        from ctypes import wintypes
        peek = ctypes.WinDLL('kernel32', use_last_error=True).PeekNamedPipe
        peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        peek.restype = wintypes.BOOL
        available = wintypes.DWORD()
        handle = msvcrt.get_osfhandle(self.sock.fileno())
        while time.monotonic() < deadline:
            if not peek(handle, None, 0, None, ctypes.byref(available), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if available.value:
                return self.sock.read(min(4096, available.value))
            time.sleep(0.005)
        raise TimeoutError('mpv did not reply in time.')

    def _request(self, command):
        if self.sock is None:
            self.connect()
        self.request_id += 1
        rid = self.request_id
        payload = (json.dumps({'command': command, 'request_id': rid}) + '\n').encode()
        if os.name == 'nt':
            self.sock.write(payload)
        else:
            self.sock.sendall(payload)
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line:
                    response = json.loads(line)
                    if response.get('request_id') == rid:
                        return response
            chunk = self._read(deadline)
            if not chunk:
                raise ConnectionError('mpv closed its connection.')
            self.buffer += chunk
        raise TimeoutError('mpv did not reply in time.')

    def get_property(self, name):
        response = self._request(['get_property', name])
        return response.get('data') if response.get('error') == 'success' else None

    def command(self, *args):
        return self._request(list(args)).get('error') == 'success'
