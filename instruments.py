"""
instruments.py
----------------
Shared GPIB device wrappers used across the lab control scripts:

  PowerMeter            - Newport 1830-C optical power meter
  PolarizationController - HP/Agilent 8169A polarization controller

Also provides small CSV helpers used by several scripts' logging code.
"""

import csv
import os
import time

import numpy as np
import pyvisa
from pyvisa.constants import AccessModes
import matplotlib.pyplot as plt

# Repo root (parent of src/), and the results/ folder all run output lives
# under -- anchored to this file's location rather than the process's cwd,
# so `python src/calibration_gui.py` lands output in the same place
# regardless of which directory it's launched from.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_ROOT = os.path.join(REPO_ROOT, "results")


# ============================================================
# GUI helpers
# ============================================================

def pump_gui(pause_s=0.001):
    """Service open plot windows (redraw, accept close clicks) without blocking.

    No-ops if no figures are open, so it never pops up a blank window.
    """
    if plt.get_fignums():
        plt.pause(pause_s)


# ============================================================
# CSV helpers
# ============================================================

def ensure_folder_for_file(path):
    if path is None:
        return
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def next_run_dir(root, date_str=None):
    """
    Returns (and creates) root/date_str/runN, where N is one higher than
    the highest existing runN under root/date_str (starting at run1).
    Call this once per pipeline invocation and reuse the result across all
    of that run's dated_output_dir() calls, so multiple runs on the same
    day land in separate, clearly-numbered folders instead of all mixing
    together under the date.
    """
    if date_str is None:
        date_str = time.strftime("%Y%m%d")
    date_path = os.path.join(root, date_str)
    os.makedirs(date_path, exist_ok=True)

    existing = [
        int(name[3:]) for name in os.listdir(date_path)
        if name.startswith("run") and name[3:].isdigit()
    ]
    run_n = max(existing, default=0) + 1

    run_path = os.path.join(date_path, f"run{run_n}")
    os.makedirs(run_path, exist_ok=True)
    return run_path


def labeled_run_dir(root, label, date_str=None):
    """
    Returns (and creates) root/date_str/<label>_<HHMMSS>[_N], where `label`
    describes what produced this run's outputs (e.g. "calibration",
    "tomography_mle") -- unlike next_run_dir()'s bare "runN", this keeps
    different kinds of runs (and, for tomography, different reconstruction
    methods) in their own self-describing folders instead of forcing them
    to share one numbered folder. N is only appended if that exact name
    already exists (e.g. two runs started in the same second).
    """
    if date_str is None:
        date_str = time.strftime("%Y%m%d")
    date_path = os.path.join(root, date_str)
    os.makedirs(date_path, exist_ok=True)

    base_name = f"{label}_{time.strftime('%H%M%S')}"
    name = base_name
    n = 1
    while os.path.exists(os.path.join(date_path, name)):
        n += 1
        name = f"{base_name}_{n}"

    run_path = os.path.join(date_path, name)
    os.makedirs(run_path, exist_ok=True)
    return run_path


def dated_output_dir(run_dir, algorithm):
    """
    Returns (and creates) run_dir/algorithm, where run_dir is the path
    returned by next_run_dir(). Keeps a run's outputs organized by which
    algorithm/stage produced them, instead of hand-edited paths.
    """
    path = os.path.join(run_dir, algorithm)
    os.makedirs(path, exist_ok=True)
    return path


def append_csv_row(csv_path, header, row):
    """
    Append `row` to csv_path, writing `header` first if the file doesn't
    exist yet.
    """
    ensure_folder_for_file(csv_path)
    write_header = not os.path.exists(csv_path)

    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)


# ============================================================
# PowerMeter (Newport 1830-C)
# ============================================================

class PowerMeter:
    """
    Wraps the Newport 1830-C's C/Q?/D? read protocol over GPIB.

    Timing knobs (status_settle_s, pre_read_delay_s, max_retries) default
    to values matching the most common call sites, but should be set
    explicitly per script to match that script's tuned behavior.
    """

    def __init__(self, addr=6, timeout_ms=5000, status_settle_s=0.1,
                 pre_read_delay_s=0.0, read_deadline_s=5.0, max_retries=1):
        self.addr = addr
        self.timeout_ms = timeout_ms
        self.status_settle_s = status_settle_s
        self.pre_read_delay_s = pre_read_delay_s
        self.read_deadline_s = read_deadline_s
        self.max_retries = max_retries

        self.rm = None
        self.inst = None

    def open(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(
            f"GPIB0::{self.addr}::INSTR",
            access_mode=AccessModes.no_lock,
            open_timeout=2000
        )
        self.inst.timeout = self.timeout_ms
        self.inst.read_termination = "\n"
        self.inst.write_termination = "\n"

        self.inst.clear()
        time.sleep(1.0)

        self.inst.write("C")
        time.sleep(0.5)

        print(f"PM ready (Newport 1830-C @ GPIB {self.addr})")
        return self

    def close(self):
        try:
            if self.inst is not None:
                self.inst.close()
        except Exception:
            pass
        try:
            if self.rm is not None:
                self.rm.close()
        except Exception:
            pass

    def set_wavelength(self, wavelength_nm):
        """
        Sets the 1830-C's calibration wavelength (Wnnnn command, Section 6.2).
        Rounds to the nearest picometer (0.001 nm) so a 1 pm sweep retains
        per-point calibration. Confirms the change by reading it back with W?.
        """
        wl_pm = round(wavelength_nm * 1000.0)
        self.inst.write(f"W{wl_pm}")
        time.sleep(self.status_settle_s)
        self.inst.write("W?")
        time.sleep(self.status_settle_s)
        confirmed = self.inst.read().strip()
        print(f"Wavelength set to {confirmed} nm")
        return float(confirmed)

    def read_power_W(self):
        """
        Single power reading, following the manual's recommended sequence
        (Section 5.5.4): clear status, wait for Read Done bit (128), send
        D?, read response once.

        Retries the whole sequence up to `max_retries` times (clearing the
        instrument buffer between attempts) before re-raising the last
        error.
        """
        last_err = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.inst.write("C")
                time.sleep(self.status_settle_s)

                deadline = time.time() + self.read_deadline_s
                while True:
                    self.inst.write("Q?")
                    time.sleep(self.status_settle_s)
                    status_raw = self.inst.read().strip()
                    if not status_raw:
                        raise ValueError("Empty response from Q?")
                    status = int(status_raw)
                    if status & 0x80:
                        break
                    if time.time() > deadline:
                        raise TimeoutError("Timed out waiting for Read Done bit")
                    time.sleep(0.05)

                if self.pre_read_delay_s:
                    time.sleep(self.pre_read_delay_s)

                self.inst.write("D?")
                time.sleep(self.status_settle_s)
                raw = self.inst.read().strip()
                if not raw:
                    raise ValueError("Empty response from D?")
                return float(raw)

            except (ValueError, TimeoutError) as e:
                last_err = e
                if attempt < self.max_retries:
                    print(f"    [read_power_W] attempt {attempt}/{self.max_retries} "
                          f"failed: {e}. Clearing buffer and retrying...")
                    try:
                        self.inst.clear()
                    except Exception:
                        pass
                    time.sleep(0.3)

        raise last_err

    def read_power_robust_W(self, n=7, delay_s=0.05):
        """
        Robust low-power reading.

        Returns:
            median_power, std_power, all_values
        """
        vals = []
        for _ in range(n):
            vals.append(self.read_power_W())
            time.sleep(delay_s)

        vals = np.array(vals, dtype=float)
        median_power = float(np.median(vals))
        std_power = float(np.std(vals))
        return median_power, std_power, vals

    def read_power_avg(self, n=5):
        readings = [self.read_power_W() for _ in range(n)]
        return sum(readings) / len(readings)


# ============================================================
# PolarizationController (HP/Agilent 8169A)
# ============================================================

class PolarizationController:
    """
    Wraps the HP/Agilent 8169A's QWP/HWP/POL command set over GPIB.

    An optional `logger` callback is invoked with each WRITE command string
    before it's sent (used by the GUI to display a log). `write_delay_s` is
    slept after every write. `retries`/`retry_wait_s` retry a failed write
    before raising -- the 8169A has a known firmware lockup that sustained
    back-to-back moves can trigger, so callers issuing many moves in a row
    (e.g. run_tomography.py) should pass retries > 1.
    """

    def __init__(self, addr, timeout_ms=10000, use_no_lock_access=True,
                 open_timeout_ms=2000, logger=None, write_delay_s=0.0,
                 retries=1, retry_wait_s=1.0, angle_fmt=None):
        self.addr = addr
        self.timeout_ms = timeout_ms
        self.use_no_lock_access = use_no_lock_access
        self.open_timeout_ms = open_timeout_ms
        self.logger = logger
        self.write_delay_s = write_delay_s
        self.retries = retries
        self.retry_wait_s = retry_wait_s
        # angle_fmt: optional format spec (e.g. ".3f") applied to QWP/HWP
        # angles before sending. None means plain str(angle_deg).
        self.angle_fmt = angle_fmt

        self.rm = None
        self.inst = None
        self.idn = None

    def open(self):
        self.rm = pyvisa.ResourceManager()
        if self.use_no_lock_access:
            self.inst = self.rm.open_resource(
                f"GPIB0::{self.addr}::INSTR",
                access_mode=AccessModes.no_lock,
                open_timeout=self.open_timeout_ms
            )
        else:
            self.inst = self.rm.open_resource(f"GPIB0::{self.addr}::INSTR")

        self.inst.timeout = self.timeout_ms
        self.idn = self.inst.query("*IDN?").strip()
        return self

    def close(self):
        try:
            if self.inst is not None:
                self.inst.close()
        except Exception:
            pass
        try:
            if self.rm is not None:
                self.rm.close()
        except Exception:
            pass

    def _write(self, cmd, label=""):
        last_err = None
        for attempt in range(1, self.retries + 1):
            try:
                if self.logger:
                    self.logger(f"WRITE: {cmd}")
                self.inst.write(cmd)
                if self.write_delay_s:
                    time.sleep(self.write_delay_s)
                return
            except Exception as e:
                last_err = e
                if attempt < self.retries:
                    print(f"  [{label}] write failed (attempt {attempt}/{self.retries}): {e}")
                    time.sleep(self.retry_wait_s)

        raise RuntimeError(
            f"{label}: '{cmd}' failed after {self.retries} attempts. "
            f"If the controller's front panel is also unresponsive, this is "
            f"likely the known 8169A firmware lockup -- power-cycle the "
            f"controller before retrying."
        ) from last_err

    def _fmt_angle(self, angle_deg):
        if self.angle_fmt is not None:
            return format(angle_deg, self.angle_fmt)
        return angle_deg

    def set_qwp(self, angle_deg):
        self._write(f":INP:POS:QUAR {self._fmt_angle(angle_deg)}", label="QWP")

    def set_hwp(self, angle_deg):
        self._write(f":INP:POS:HALF {self._fmt_angle(angle_deg)}", label="HWP")

    def set_pol(self, value):
        self._write(f":INP:POS:POL {value}", label="POL")


# ============================================================
# Calibrated generation-side state presets (H/V/D/A/R/L)
# ============================================================
#
# QWP/HWP offsets for each state, plus a calibration offset that gets
# added to both and is also sent as the POL value. Shared by
# run_tomography.py, min_power_search.py, and polarization_controller_gui.py
# so there's a single source of truth for the convention.

DEFAULT_GEN_OFFSET = -55.2   # calibrated against H-state polarizer sweep

GEN_BASE_STATES = {
    'H': (0,    0),     # Horizontal
    'V': (0,    45),    # Vertical
    'D': (0,    22.5),  # Diagonal
    'A': (0,    67.5),  # Anti-diagonal
    'R': (45,   0),     # Right circular
    'L': (-45,  0),     # Left circular
}


def set_generation_state(pc, state, offset=DEFAULT_GEN_OFFSET):
    """
    Sets `pc` to one of the calibrated H/V/D/A/R/L generation states:
    QWP/HWP offsets from GEN_BASE_STATES, both shifted by `offset`,
    with `offset` also sent as the POL value.

    Does not sleep -- callers add their own settle time after calling.
    """
    base_qwp, base_hwp = GEN_BASE_STATES[state]
    qwp = base_qwp + offset
    hwp = base_hwp + offset

    pc.set_qwp(qwp)
    pc.set_hwp(hwp)
    pc.set_pol(offset)
    print(f"Generation set to {state}: QWP={qwp}, HWP={hwp}, POL={offset}")
    return qwp, hwp
