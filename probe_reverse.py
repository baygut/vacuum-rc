"""Probe for an undocumented reverse: hold button value 7 for 1.5s, then send 8."""
import time

from miio_client import Miio, load_device

m = Miio(*load_device())


def button(value):
    return m.action(2, 26, [{"piid": 39, "value": value}])


try:
    print("enter remote:", m.action(2, 28))
    time.sleep(2.0)
    replies = []
    end = time.time() + 1.5
    while time.time() < end:
        replies.append(button(7))
        time.sleep(0.2)
    print("press 7 (first):", replies[0])
    print("press 7 (distinct replies):", {str(r.get("result", r.get("error"))) for r in replies})
    print("release 8:", button(8))
    time.sleep(0.5)
    print("action result / status:", m.get_props((2, 67), (2, 2)))
finally:
    for value in (8, 2, 4, 6):
        try:
            button(value)
        except Exception:
            pass
    print("exit remote:", m.action(2, 29))
