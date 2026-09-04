"""
IL.py
-----
Interactive WSS insertion-loss measurement.

Prompts the operator (key 1-4) to take wavelength sweeps for a baseline with the
WSS disconnected and for the WSS set to 50 / 20 / 10 GHz bandwidths (set in the
external WSS software).  Each sweep is saved to CSV immediately in dBm so a long
run is never lost.  Key 5 loads the saved sweeps and plots insertion loss
(ref - condition, in dB) on a single figure.

Runs on the bench PC, not this workstation.
"""

import os
import time

import numpy as np
import matplotlib.pyplot as plt
import pyvisa

from instruments import PowerMeter, append_csv_row, REPO_ROOT


# ============================================================
# Run configuration
# ============================================================

WL_START_NM = 1599.4
WL_END_NM = 1600.6
WL_RES_NM = 0.001

LASER_POWER_MW = 3.0

LASER_ADDR = 20   # 20 = Agilent, 24 = HP
PM_ADDR = 6       # Newport 1830-C

LASER_SETTLE_S = 1.5   # after each WAVE command
PM_SETTLE_S = 0.5      # after updating the meter's wavelength calibration

ROBUST_READS_N = 7     # readings per point for read_power_robust_W (median)

IL_DIR = os.path.join(REPO_ROOT, "results", "IL")

CONDITIONS = [
    # (menu key, label, bandwidth note used only for prompting)
    ("1", "reference", "baseline, WSS DISCONNECTED"),
    ("2", "50GHz", "WSS connected, 50 GHz bandwidth"),
    ("3", "20GHz", "WSS connected, 20 GHz bandwidth"),
    ("4", "10GHz", "WSS connected, 10 GHz bandwidth"),
]

COND_FILENAMES = {label: f"il_{label}_dBm.csv" for _, label, _ in CONDITIONS}


def build_wavelengths(start_nm, end_nm, res_nm):
    n_steps = int(round((end_nm - start_nm) / res_nm)) + 1
    return np.round(start_nm + np.arange(n_steps) * res_nm, 6)


def to_dBm(power_w):
    """Convert a linear-Watts reading (or array) to dBm."""
    return 10.0 * np.log10(np.asarray(power_w, dtype=float) / 1e-3)


def open_laser(addr):
    rm = pyvisa.ResourceManager()
    laser = rm.open_resource(f"GPIB0::{addr}::INSTR")
    laser.timeout = 5000
    laser.read_termination = "\n"
    laser.write_termination = "\n"
    return rm, laser


def read_condition_file(label):
    path = os.path.join(IL_DIR, COND_FILENAMES[label])
    if not os.path.exists(path):
        return None
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    return data


def take_sweep(label, wavelengths):
    """Take one full sweep for `label` and stream it to its CSV in dBm."""
    csv_path = os.path.join(IL_DIR, COND_FILENAMES[label])
    os.makedirs(IL_DIR, exist_ok=True)
    if os.path.exists(csv_path):
        os.remove(csv_path)   # overwrite partial / stale file for this condition

    rm = None
    laser = None
    pm = PowerMeter(PM_ADDR)
    try:
        pm.open()
        rm, laser = open_laser(LASER_ADDR)
        laser.write(f"POW {LASER_POWER_MW} W")
        time.sleep(2.0)
        laser.write("OUTP ON")

        if laser.query("OUTP?").strip() != "1":
            raise RuntimeError("Laser output is off")

        powers_w = np.full_like(wavelengths, np.nan, dtype=float)
        for i, wl_nm in enumerate(wavelengths):
            print(f"[{label}] {wl_nm:.4f} nm  ({i + 1}/{len(wavelengths)})")

            laser.write(f"WAVE {wl_nm * 1e-9:.7e}")
            time.sleep(LASER_SETTLE_S)

            pm.set_wavelength(wl_nm)
            time.sleep(PM_SETTLE_S)

            median_power, _, _ = pm.read_power_robust_W(n=ROBUST_READS_N)
            powers_w[i] = median_power
            append_csv_row(csv_path, ["Wavelengths_nm", "Power_dBm"],
                           [wl_nm, to_dBm(median_power)])

        print(f"[{label}] done -> {csv_path}")
        return powers_w
    finally:
        if laser is not None:
            try:
                laser.write("OUTP Off")
            except Exception:
                pass
            try:
                laser.close()
            except Exception:
                pass
        if rm is not None:
            try:
                rm.close()
            except Exception:
                pass
        pm.close()


def plot_il():
    """Load saved sweeps and plot insertion loss for each present condition."""
    ref = read_condition_file("reference")
    if ref is None:
        print("No reference sweep found. Press 1 first (WSS disconnected).")
        return

    wavelengths = ref[:, 0]
    ref_dbm = ref[:, 1]

    fig, ax = plt.subplots()
    plotted_any = False
    for key, label, note in CONDITIONS:
        if key == "1":
            continue
        cond = read_condition_file(label)
        if cond is None:
            print(f"No data for {label} ({note}). Skipping.")
            continue
        if len(cond) != len(ref):
            print(f"Length mismatch for {label}; skipping.")
            continue
        il_db = ref_dbm - cond[:, 1]
        ax.plot(wavelengths, il_db, "-o", label=label)
        plotted_any = True

    if not plotted_any:
        print("No condition sweeps found to plot (press 2/3/4 first).")
        return

    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Insertion loss (dB)")
    ax.set_xticks([wavelengths[0],
                   wavelengths[len(wavelengths) // 2],
                   wavelengths[-1]])
    ax.grid(True)
    ax.legend(title="Bandwidth")

    fig_path = os.path.join(IL_DIR, f"IL_{time.strftime('%Y%m%d_%H%M%S')}.png")
    os.makedirs(IL_DIR, exist_ok=True)
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    print(f"Graph saved to: {fig_path}")
    plt.show()


def menu():
    print("\n=== WSS Insertion Loss ===\n")
    print("Set up each measurement, then press the key:")
    print("  1  Baseline sweep  (WSS DISCONNECTED, input fiber straight to meter)")
    print("  2  WSS sweep @ 50 GHz  (set bandwidth in WSS software first)")
    print("  3  WSS sweep @ 20 GHz")
    print("  4  WSS sweep @ 10 GHz")
    print("  5  Plot insertion loss from saved sweeps")
    print("  q  Quit")
    return input("> ").strip().lower()


def main():
    wavelengths = build_wavelengths(WL_START_NM, WL_END_NM, WL_RES_NM)

    while True:
        choice = menu()

        if choice == "q":
            print("Done.")
            break

        if choice in ("1", "2", "3", "4"):
            _, label, note = next(c for c in CONDITIONS if c[0] == choice)
            print(f"\nStarting: {note}")
            take_sweep(label, wavelengths)
        elif choice == "5":
            plot_il()
        else:
            print("Unknown key.")


if __name__ == "__main__":
    main()
