"""
WavelengthSweepTunableLaser.py
-------------------------------
Python port of ExistingControl/Filter response/Power_wl_meas.m.

Sweeps the Agilent/HP tunable laser across a wavelength range while
reading optical power with the Newport 1830-C power meter (instruments.py),
then saves Wavelengths_nm / Power_W to CSV and plots the response.

Runs on the bench PC, not this workstation.
"""

import os
import time

import numpy as np
import matplotlib.pyplot as plt
import pyvisa

from instruments import PowerMeter, append_csv_row


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

CSV_FILENAME = "wavelength_sweep_1599_1601nm_1pm.csv"


def build_wavelengths(start_nm, end_nm, res_nm):
    n_steps = int(round((end_nm - start_nm) / res_nm)) + 1
    return np.round(start_nm + np.arange(n_steps) * res_nm, 6)


def open_laser(addr):
    rm = pyvisa.ResourceManager()
    laser = rm.open_resource(f"GPIB0::{addr}::INSTR")
    laser.timeout = 5000
    laser.read_termination = "\n"
    laser.write_termination = "\n"
    return rm, laser


def main():
    wavelengths = build_wavelengths(WL_START_NM, WL_END_NM, WL_RES_NM)
    csv_path = os.path.join(os.getcwd(), CSV_FILENAME)

    pm = PowerMeter(PM_ADDR)
    rm = None
    laser = None

    try:
        pm.open()

        rm, laser = open_laser(LASER_ADDR)
        laser.write(f"POW {LASER_POWER_MW} W")
        time.sleep(2.0)
        laser.write("OUTP ON")

        if laser.query("OUTP?").strip() == "1":
            print("Laser output is on")
        else:
            raise RuntimeError("Laser output is off")

        powers = np.full_like(wavelengths, np.nan, dtype=float)

        for i, wl_nm in enumerate(wavelengths):
            print(f"{wl_nm:.4f} nm  ({i + 1}/{len(wavelengths)})")

            laser.write(f"WAVE {wl_nm * 1e-9:.7e}")
            time.sleep(LASER_SETTLE_S)

            pm.set_wavelength(wl_nm)
            time.sleep(PM_SETTLE_S)

            median_power, std_power, _ = pm.read_power_robust_W(n=ROBUST_READS_N)
            powers[i] = median_power
            append_csv_row(csv_path, ["Wavelengths_nm", "Power_W"],
                           [wl_nm, powers[i]])

        png_path = os.path.join(os.getcwd(),
                                CSV_FILENAME.replace(".csv", ".png"))
        plt.figure()
        plt.plot(wavelengths, powers, "-o")
        plt.xlabel("Wavelength (nm)")
        plt.ylabel("Power (W)")
        plt.grid(True)
        plt.savefig(png_path, dpi=150)

        print(f"Data saved to: {csv_path}")
        print(f"Graph saved to: {png_path}")

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


if __name__ == "__main__":
    main()
