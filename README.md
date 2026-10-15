# vacuum-rc

Drive a Xiaomi robot vacuum like an RC car with a PS5 DualSense controller.

The script talks to the vacuum directly over your home Wi-Fi (the local Mi Home
protocol on UDP 54321), so there is no cloud round trip while you drive.

Built and tested with a `xiaomi.vacuum.ov51gl` on macOS. Other Xiaomi vacuums
that expose the same MIoT remote-control actions should work too; see
[Other models](#other-models).

## Controls

| Input | Action |
|---|---|
| Cross (X) | Enter remote mode |
| Left stick up / D-pad up | Drive forward |
| Left stick left/right / D-pad left/right | Turn on the spot |
| Left stick down / D-pad down | Spin around (about 180 degrees). Keep holding to drive forward after the spin; a quick pull only spins |
| Circle (O) | Stop and exit remote mode |
| Triangle | Exit remote mode and send the vacuum back to the dock |
| Options | Quit |

The vacuum has no reverse in remote mode, so stick-down fakes it with a spin.
When the stick is pushed diagonally, the axis pushed further wins.

Quitting, Ctrl-C, or the controller disconnecting always releases the current
button and exits remote mode, so the vacuum never keeps driving on its own.

## Requirements

- macOS (should also work on Linux and Windows, untested)
- Python 3.9 or newer
- A PS5 DualSense controller paired over Bluetooth
  (hold **PS + Create** until the light bar flashes, then pair it in
  System Settings > Bluetooth)
- The vacuum on the same network as the computer, and its **token**

## Setup

```bash
git clone https://github.com/baygut/vacuum-rc.git
cd vacuum-rc
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Get the device token

Every command to the vacuum is encrypted with a per-device token. Get it with
[Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor):
log in with your Xiaomi account (the QR code option avoids typing a password)
and pass `-o` to save the result as JSON:

```bash
python token_extractor.py -o /path/to/vacuum-rc/device.json
```

The script reads the first device of the first home in that file, so if your
account has several devices, trim it down to the vacuum.
`device.example.json` shows the fields that are used.

`device.json` holds a secret: it is git-ignored, keep it that way and
`chmod 600 device.json`.

## Usage

Try the controller mapping without touching the vacuum:

```bash
.venv/bin/python vacuum_rc.py --dry-run
```

Drive for real:

```bash
.venv/bin/python vacuum_rc.py
```

Other modes:

| Command | What it does |
|---|---|
| `vacuum_rc.py --show-input` | Print raw button numbers and stick axes, to check or fix the mapping |
| `vacuum_rc.py --spin-test 2.5` | Turn left for 2.5 s, to tune `SPIN_180_S` |
| `miio_client.py` | Print status, battery, charging state and fault code |

## Tuning

Constants at the top of `vacuum_rc.py`:

| Constant | Default | Meaning |
|---|---|---|
| `DEADZONE` | `0.5` | How far the stick must move before it counts |
| `REPEAT_S` | `0.2` | How often a held direction is re-sent. Lower it if movement stutters; going much faster makes the vacuum drop commands |
| `SPIN_180_S` | `2.5` | How long a left turn takes to reach about 180 degrees. Measure with `--spin-test` on your floor |

## How it works

`miio_client.py` is a minimal miIO client: a hello handshake to learn the
device id and clock, then AES-128-CBC encrypted JSON-RPC (`get_properties`,
`action`) keyed from the token. It re-handshakes and retries once on a timeout.

Remote driving uses the MIoT spec of the Robot Cleaner service (`siid 2`):

| Action | `aiid` | Notes |
|---|---|---|
| Enter Remote | 28 | Status switches to 8 (Remote) and charging stops |
| Remote Control | 26 | Takes property 39, a button event |
| Exit Remote | 29 | |
| Stop And Go Charge | 3 | Used by Triangle |

Button events for property 39: `1`/`2` press/release Up, `3`/`4` press/release
Left, `5`/`6` press/release Right. There is no Down; values `7`/`8` are accepted
but do nothing (`probe_reverse.py` is the test that showed it).

A single short press does not move the vacuum. It only drives while the press
keeps being re-sent, which is why the script repeats the held direction every
`REPEAT_S` seconds and sends the release as soon as the stick is centered.

## Other models

Look your model up on [miot-spec.org](https://home.miot-spec.org/) and check
that its Robot Cleaner service has Enter Remote, Remote Control and Exit Remote
actions. If the ids differ, change `SIID`, the `AIID_*` constants,
`PIID_BUTTON`, and the `PRESS`/`RELEASE` values in `vacuum_rc.py`.

## Troubleshooting

- **`No route to host` on start:** the vacuum's Wi-Fi was dozing. Run it again.
  If it keeps happening, check that macOS allows your terminal app under
  System Settings > Privacy & Security > Local Network.
- **Commands are accepted but nothing moves:** the vacuum answers `code 0` to
  almost anything, so a clean reply does not prove it moved. Make sure it is in
  remote mode (press X first) and off the dock with room to move.
- **A button does the wrong thing:** run `--show-input`, press it, and update
  the `BTN_*` constants.

## Files

| File | Purpose |
|---|---|
| `vacuum_rc.py` | The controller-to-vacuum driver |
| `miio_client.py` | Local miIO/MIoT client |
| `probe_reverse.py` | One-off test for an undocumented reverse button |
| `device.example.json` | Shape of the token file |
| `device.json` | Your token file (git-ignored, not in the repo) |
