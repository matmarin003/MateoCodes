"""
TEST PROGRAM FOR OPENING AND CLOSING CONNECTIONS WITH DEVICES
Python translation of Power_wl_meas.m

Performs a wavelength sweep on a tunable laser source, reading back power
from a power meter at each wavelength step, then plots and saves the data.

Requires: pyvisa, numpy, pandas, matplotlib
    pip install pyvisa numpy pandas matplotlib
You will also need a VISA backend (e.g. NI-VISA, or the pure-Python
'pyvisa-py' backend) installed and able to see your GPIB interface.
"""

import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pyvisa

# -------------------------------------------------------------------------
# Wavelength Definition
# -------------------------------------------------------------------------
wl_start = 1599.4   # beginning of wavelength (nm) sweep for tunable laser source
wl_end = 1600.6     # end of wavelength (nm) sweep for tunable laser source
res = 0.001         # resolution of sweep (nm)

# np.arange can accumulate float error over many steps, so round to avoid drift
n_steps = round((wl_end - wl_start) / res) + 1
wavelengths = np.round(wl_start + np.arange(n_steps) * res, 6)

p = 3  # output power of the device (mW)

power_msr = np.full(wavelengths.shape, np.nan)  # preallocate measurement array


def main():
    rm = pyvisa.ResourceManager()  # equivalent of MATLAB's instrument driver layer

    # ---------------------------------------------------------------
    # Setup Power meter (GPIB board 0, address 4)
    # ---------------------------------------------------------------
    pwm = rm.open_resource('GPIB0::4::INSTR')
    pwm.timeout = 5000            # ms; increase if reads still come back empty/timeout
    pwm.read_termination = '\n'   # adjust if instrument uses '\r\n' or none
    pwm.write_termination = '\n'
    pwm.write('sens2:pow:unit 1')       # units of power: 0 = dBm, 1 = Watts
    time.sleep(0.3)
    pwm.write('sens2:pow:rang:auto 2')  # enable auto-ranging
    time.sleep(0.3)
    pwm.write(f'sens2:pow:wl{1600} nm')  # initial wavelength calibration
    time.sleep(0.5)

    # ---------------------------------------------------------------
    # Setup Tunable Laser (GPIB board 0, address 20)
    # ---------------------------------------------------------------
    tls = rm.open_resource('GPIB0::20::INSTR')  # 20 for Agilent, 24 for HP
    tls.timeout = 5000
    tls.read_termination = '\n'
    tls.write_termination = '\n'
    tls.write(f'POW {p} W')  # set laser output power
    time.sleep(2)
    tls.write('OUTP ON')

    out_state = tls.query('OUTP?').strip()
    if out_state == '1':
        print('Laser output is on')
    else:
        raise RuntimeError('Output is off')

    # ---------------------------------------------------------------
    # Sweep wavelengths
    # ---------------------------------------------------------------
    try:
        for i, wl_nm in enumerate(wavelengths):
            print([wl_nm, i + 1])  # MATLAB used 1-based index; kept for parity

            tls.write(f'WAVE {wl_nm * 1e-9:1.7e}')
            time.sleep(1.5)

            pwm.write(f'sens2:pow:wave {wl_nm} nm')
            time.sleep(0.5)

            # Query power reading. Instrument reply is expected in the form
            # "NDCW+<value>" (matches the original MATLAB 'NDCW+%f' scan),
            # e.g. "NDCW+1.234E-03". Strip the "NDCW+" prefix before parsing.
            response = pwm.query('read2:pow?').strip()
            print(f'  raw power meter reply: {response!r}')  # DEBUG - remove once format is confirmed

            if response == '':
                print('  WARNING: empty reply from power meter, skipping this point')
                power_msr[i] = np.nan
                continue

            value_str = response.split('NDCW+')[-1]
            power_msr[i] = float(value_str)

    finally:
        # -------------------------------------------------------------
        # Cleanup (always turn off laser & close connections, even on error)
        # -------------------------------------------------------------
        tls.write('OUTP Off')
        tls.close()
        pwm.close()

    # ---------------------------------------------------------------
    # Plot
    # ---------------------------------------------------------------
    plt.figure()
    plt.plot(wavelengths, power_msr, '-o')
    plt.xlabel('Wavelength (nm)')
    plt.ylabel('Power (W)')
    plt.grid(True)
    plt.show()

    # ---------------------------------------------------------------
    # Save Data to CSV
    # ---------------------------------------------------------------
    df = pd.DataFrame({
        'Wavelengths_nm': wavelengths,
        'Power_W': power_msr,
    })
    filename = 'wavelength_sweep_1599_1601nm_1pm.csv'
    df.to_csv(filename, index=False)
    print(f'Data saved to: {filename}')


if __name__ == '__main__':
    main()