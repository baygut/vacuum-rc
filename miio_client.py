"""Minimal local miIO / MIoT client for the vacuum (UDP 54321)."""
import hashlib
import json
import os
import socket
import struct
import sys
import time

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

DEVICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "device.json")


def load_device():
    data = json.load(open(DEVICES_FILE))
    dev = data[0]["homes"][0]["devices"][0]
    return dev["localip"], bytes.fromhex(dev["token"])


class Miio:
    def __init__(self, ip, token, timeout=2.0):
        self.ip, self.token = ip, token
        self.key = hashlib.md5(token).digest()
        self.iv = hashlib.md5(self.key + token).digest()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.msg_id = int(time.time()) % 10000
        self.handshake()

    def handshake(self):
        self.sock.sendto(bytes.fromhex("21310020" + "ff" * 28), (self.ip, 54321))
        reply, _ = self.sock.recvfrom(1024)
        self.did, stamp = struct.unpack(">II", reply[8:16])
        self.stamp_offset = stamp - time.time()

    def send(self, method, params):
        """Send one command; on timeout re-handshake and retry once."""
        try:
            return self._send_once(method, params)
        except socket.timeout:
            self.handshake()
            return self._send_once(method, params)

    def _send_once(self, method, params):
        self.msg_id += 1
        payload = json.dumps({"id": self.msg_id, "method": method, "params": params}).encode()
        body = AES.new(self.key, AES.MODE_CBC, self.iv).encrypt(pad(payload, 16))
        stamp = int(time.time() + self.stamp_offset) + 1
        header = struct.pack(">HHIII", 0x2131, 32 + len(body), 0, self.did, stamp)
        checksum = hashlib.md5(header + self.token + body).digest()
        self.sock.sendto(header + checksum + body, (self.ip, 54321))
        while True:
            reply, _ = self.sock.recvfrom(4096)
            if len(reply) <= 32:
                continue
            plain = unpad(AES.new(self.key, AES.MODE_CBC, self.iv).decrypt(reply[32:]), 16)
            msg = json.loads(plain.rstrip(b"\x00").decode())
            if msg.get("id") == self.msg_id:
                return msg

    def get_props(self, *pairs):
        return self.send("get_properties", [{"did": str(self.did), "siid": s, "piid": p} for s, p in pairs])

    def action(self, siid, aiid, ins=()):
        return self.send("action", {"did": str(self.did), "siid": siid, "aiid": aiid, "in": list(ins)})


if __name__ == "__main__":
    ip, token = load_device()
    m = Miio(ip, token)
    print(json.dumps(m.get_props((2, 2), (3, 1), (3, 2), (2, 3), (1, 4)), indent=1))
