"""
gpib_diag.py
------------
GPIB bus diagnostic for the optical bench.  Run this on the bench PC:

    python gpib_diag.py

It lists VISA resources, tries to talk to the power meter (GPIB0::6) and tunable
laser (GPIB0::20), then scans GPIB addresses 1-30 to find where the 1830-C power
meter is actually answering (it can be moved by its rear DIP switches).

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


def scan_addresses(rm, first=1, last=30):
    """
    Probe each GPIB primary address and report what is listening there.

    For every address we try (a) a SCPI `*IDN?` (identifies SCPI instruments)
    and (b) the Newport 1830-C handshake (`C` then `Q?`).  Absent addresses
    fail fast with NLISTENERS.  Read-only: no state-changing writes.
    """
    responders = []
    for addr in range(first, last + 1):
        res = f"GPIB0::{addr}::INSTR"
        inst = None
        try:
            inst = rm.open_resource(res, open_timeout=500)
        except Exception as e:
            print(f"  addr {addr:2d}: open FAILED -> {e!r}")
            continue

        try:
            inst.timeout = 800
            inst.read_termination = "\n"
            inst.write_termination = "\n"

            idn = None
            try:
                idn = inst.query("*IDN?").strip()
            except Exception:
                idn = None

            q_resp = None
            q_err = None
            try:
                inst.write("C")
                time.sleep(0.2)
                inst.write("Q?")
                time.sleep(0.2)
                q_resp = inst.read().strip()
            except Exception as e:
                q_err = e

            if q_resp is not None:
                print(f"  addr {addr:2d}: 1830-C LISTENER  (Q? -> {q_resp!r})"
                      + (f"  IDN={idn!r}" if idn else ""))
                responders.append((addr, "1830-C", idn, q_resp))
            elif idn:
                print(f"  addr {addr:2d}: responds  IDN={idn!r}")
                responders.append((addr, "SCPI", idn, None))
            else:
                err = q_err if q_err is not None else "no response"
                print(f"  addr {addr:2d}: no listener ({err})")
        finally:
            try:
                inst.close()
            except Exception:
                pass

    return responders


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

    section("STEP 4: scan GPIB addresses 1-30 for listeners")
    responders = scan_addresses(rm, 1, 30)
    print("\nSummary of responders:")
    if responders:
        for addr, kind, idn, q_resp in responders:
            extra = f" IDN={idn!r}" if idn else ""
            extra += f" Q?={q_resp!r}" if q_resp is not None else ""
            print(f"  GPIB0::{addr}::{kind}{extra}")
    else:
        print("  (none)")

    section("INTERPRETATION")
    print("- If STEP 1 lists nothing: GPIB adapter/driver, not the instruments.")
    print("- If the laser talks but addr 6 fails: meter address/cable/state.")
    print("- If BOTH fail: bus/adapter is wedged -> unplug-replug adapter or reboot.")
    print("- If clear() fails but write('C')/Q? work: harmless, ignore clear.")
    print("- If clear() AND write fail: no device listening at that address.")
    print("- STEP 4 shows where the 1830-C actually answers: set its rear DIP")
    print("  switches (SW1/SW2) back to address 6, then power-cycle/RESET.")


if __name__ == "__main__":
    main()
