"""Drive the Xiaomi vacuum like an RC car with a PS5 (DualSense) controller.

Controls:
  Cross (X)     enter remote mode
  Circle (O)    stop and exit remote mode
  Triangle      exit remote mode and send it back to the dock
  Left stick    up = forward, left/right = turn (D-pad works too)
                down = spin around to face the other way (the vacuum has
                no reverse), then keep driving forward while still held;
                a quick pull only spins
  Options       quit

The vacuum only moves while a button press keeps being re-sent, so the
script repeats the current direction every REPEAT_S seconds and sends the
matching release as soon as the stick is centered.

Usage:
  .venv/bin/python vacuum_rc.py              drive the vacuum
  .venv/bin/python vacuum_rc.py --dry-run    print commands, never contact the vacuum
  .venv/bin/python vacuum_rc.py --show-input print raw buttons/axes to check the mapping
  .venv/bin/python vacuum_rc.py --spin-test 2.5
                                             turn left for 2.5s, to tune SPIN_180_S
"""
import argparse
import os
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

# Button indices for the DualSense through SDL's game-controller layout.
BTN_CROSS, BTN_CIRCLE, BTN_SQUARE, BTN_TRIANGLE = 0, 1, 2, 3
BTN_OPTIONS = 6
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 11, 12, 13, 14
AXIS_LX, AXIS_LY = 0, 1

DEADZONE = 0.5
TICK_S = 0.05
REPEAT_S = 0.2
# How long holding Left takes to turn the vacuum about 180 degrees.
# Tune with --spin-test on your own floor.
SPIN_180_S = 2.5

# MIoT spec for xiaomi.vacuum.ov51gl, service 2 (Robot Cleaner).
SIID = 2
AIID_STOP_AND_DOCK, AIID_REMOTE_BUTTON, AIID_ENTER_REMOTE, AIID_EXIT_REMOTE = 3, 26, 28, 29
PIID_BUTTON = 39
PRESS = {"forward": 1, "left": 3, "right": 5}
RELEASE = {"forward": 2, "left": 4, "right": 6}


class Vacuum:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.remote = False
        if not dry_run:
            from miio_client import Miio, load_device
            self.m = Miio(*load_device(), timeout=0.5)

    def _call(self, label, fn):
        if self.dry_run:
            print("[dry-run]", label)
            return True
        try:
            reply = fn()
        except Exception as e:
            print(label, "failed:", e)
            return False
        code = reply.get("result", {}).get("code", reply.get("error", {}).get("code", 0))
        if code != 0:
            print(label, "rejected:", reply)
        return code == 0

    def _action(self, label, aiid, ins=()):
        return self._call(label, lambda: self.m.action(SIID, aiid, ins))

    def button(self, value, label):
        return self._action(label, AIID_REMOTE_BUTTON, [{"piid": PIID_BUTTON, "value": value}])

    def enter_remote(self):
        if self._action("enter remote", AIID_ENTER_REMOTE):
            self.remote = True
            print("Remote mode on. Drive with the left stick.")

    def exit_remote(self):
        if self.remote:
            self._action("exit remote", AIID_EXIT_REMOTE)
            self.remote = False
            print("Remote mode off.")

    def dock(self):
        self.exit_remote()
        if self._action("go to dock", AIID_STOP_AND_DOCK):
            print("Heading back to the dock.")


def wanted_direction(js):
    x, y = js.get_axis(AXIS_LX), js.get_axis(AXIS_LY)
    buttons = js.get_numbuttons()

    def pressed(i):
        return i < buttons and js.get_button(i)

    if pressed(BTN_DPAD_LEFT):
        return "left"
    if pressed(BTN_DPAD_RIGHT):
        return "right"
    if pressed(BTN_DPAD_UP):
        return "forward"
    if pressed(BTN_DPAD_DOWN):
        return "back"
    # The vacuum takes one direction at a time, so follow whichever stick axis
    # is pushed further; a slightly diagonal "up" still drives forward.
    if max(abs(x), abs(y)) < DEADZONE:
        return None
    if abs(x) > abs(y):
        return "left" if x < 0 else "right"
    return "forward" if y < 0 else "back"


def wait_for_controller():
    print("Waiting for a controller (pair it in System Settings > Bluetooth)...")
    while True:
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEADDED:
                js = pygame.joystick.Joystick(event.device_index)
                print("Connected:", js.get_name())
                return js
        time.sleep(0.2)


def show_input():
    js = wait_for_controller()
    print("Press buttons and move sticks. Ctrl-C to stop.")
    last_axes = None
    while True:
        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                print("button", event.button)
            elif event.type == pygame.JOYHATMOTION:
                print("hat", event.value)
        axes = tuple(round(js.get_axis(i), 1) for i in range(js.get_numaxes()))
        if axes != last_axes:
            print("axes", axes)
            last_axes = axes
        time.sleep(0.05)


def spin_test(seconds):
    vac = Vacuum(dry_run=False)
    vac.enter_remote()
    try:
        end = time.time() + seconds
        while time.time() < end:
            vac.button(PRESS["left"], "hold left")
            time.sleep(REPEAT_S)
    finally:
        vac.button(RELEASE["left"], "release left")
        vac.exit_remote()
    print("Spun left for %.1fs. Set SPIN_180_S so it lands at 180 degrees." % seconds)


def drive(dry_run):
    vac = Vacuum(dry_run)
    js = wait_for_controller()
    print(__doc__.split("Usage:")[0])
    current, last_sent = None, 0.0
    spin_until, back_latched = 0.0, False
    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEREMOVED:
                    print("Controller disconnected, stopping.")
                    return
                if event.type == pygame.JOYBUTTONDOWN:
                    if event.button == BTN_CROSS and not vac.remote:
                        vac.enter_remote()
                    elif event.button == BTN_CIRCLE:
                        if current:
                            vac.button(RELEASE[current], "release " + current)
                            current = None
                        spin_until = 0.0
                        vac.exit_remote()
                    elif event.button == BTN_TRIANGLE:
                        current, spin_until = None, 0.0
                        vac.dock()
                    elif event.button == BTN_OPTIONS:
                        return

            if vac.remote:
                stick = wanted_direction(js)
                now = time.time()
                # "back" starts one timed spin per pull, then drives forward
                # for as long as the stick stays down. The stick has to leave
                # "back" before the next pull spins again.
                if stick == "back" and not back_latched:
                    spin_until = now + SPIN_180_S
                    print("Spinning around.")
                back_latched = stick == "back"
                if now < spin_until:
                    wanted = "left"
                else:
                    wanted = "forward" if stick == "back" else stick
                if wanted != current:
                    if current:
                        vac.button(RELEASE[current], "release " + current)
                    if wanted:
                        vac.button(PRESS[wanted], "press " + wanted)
                        last_sent = now
                    current = wanted
                elif current and now - last_sent >= REPEAT_S:
                    if not dry_run:  # keep dry-run output to one line per change
                        vac.button(PRESS[current], "hold " + current)
                    last_sent = now
            time.sleep(TICK_S)
    finally:
        if current:
            vac.button(RELEASE[current], "release " + current)
        vac.exit_remote()


def main():
    parser = argparse.ArgumentParser(description="Drive the vacuum with a PS5 controller.")
    parser.add_argument("--dry-run", action="store_true", help="print commands, never contact the vacuum")
    parser.add_argument("--show-input", action="store_true", help="print raw controller input")
    parser.add_argument("--spin-test", type=float, metavar="SECONDS", help="turn left for SECONDS, then stop")
    args = parser.parse_args()

    pygame.init()
    pygame.joystick.init()
    try:
        if args.spin_test:
            spin_test(args.spin_test)
        elif args.show_input:
            show_input()
        else:
            drive(args.dry_run)
    except KeyboardInterrupt:
        print()
    finally:
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
