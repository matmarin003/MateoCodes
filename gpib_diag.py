"""
gpib_diag.py
------------
GPIB bus diagnostic for the optical bench.  Run this on the bench PC:

    python gpib_diag.py

It lists VISA resources and, for the power meter (GPIB0::6) and tunable laser
(GPIB0::20), tries to open / clear / talk to each so you can tell whether the
problem is the whole bus/adapter or just one instrument.

Safe: read-only queries, laser output is never enabled.
"""

import time

import pyvisa


def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def try_open(rm, addr, label):
    res = f"GPIB0::{addr}::INSTR"
    print(f"\n--- {label}: {res} ---")
    inst = None
    try:
        inst = rm.open_resource(res, open_timeout=2000)
        print("  open_resource  : OK")
    except Exception as e:
        print(f"  open_resource  : FAILED -> {e!r}")
        return

    try:
        inst.timeout = 5000
        inst.read_termination = "\n"
        inst.write_termination = "\n"
        print("  set timeout/terminations : OK")
    except Exception as e:
        print(f"  set timeout/terminations : FAILED -> {e!r}")

    try:
        inst.clear()
        print("  clear()        : OK")
    except Exception as e:
        print(f"  clear()        : FAILED -> {e!r}")

    try:
        inst.write("C")
        time.sleep(0.5)
        print("  write('C')     : OK")
    except Exception as e:
        print(f"  write('C')     : FAILED -> {e!r}")

    try:
        inst.write("Q?")
        time.sleep(0.3)
        resp = inst.read().strip()
        print(f"  read after Q?  : OK -> {resp!r}")
    except Exception as e:
        print(f"  read after Q?  : FAILED -> {e!r}")

    try:
        inst.close()
        print("  close()        : OK")
    except Exception as e:
        print(f"  close()        : FAILED -> {e!r}")


def main():
    section("STEP 1: VISA resources visible")
    rm = pyvisa.ResourceManager()
    print("VISA library :", rm)
    resources = rm.list_resources()
    print("Resources    :", resources)
    if not resources:
        print("\nNo resources at all -> the GPIB adapter/driver is the problem.")
        print("  - Unplug/replug the GPIB-USB adapter (or power-cycle it).")
        print("  - Reboot if needed; confirm it shows in NI-MAX > Devices.")
        return

    section("STEP 2: talk to the power meter (GPIB0::6)")
    try_open(rm, 6, "Power meter (Newport 1830-C)")

    section("STEP 3: talk to the tunable laser (GPIB0::20)")
    try_open(rm, 20, "Tunable laser")

    section("INTERPRETATION")
    print("- If STEP 1 lists nothing: GPIB adapter/driver, not the instruments.")
    print("- If the laser talks but addr 6 fails: meter address/cable/state.")
    print("- If BOTH fail: bus/adapter is wedged -> unplug-replug adapter or reboot.")
    print("- If clear() fails but write('C')/Q? work: harmless, ignore clear.")
    print("- If clear() AND write fail: no device listening at that address.")


if __name__ == "__main__":
    main()
