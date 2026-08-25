"""
Diagnostic script - run this BEFORE the full sweep to check:
  1. That PyVISA can see your GPIB instruments
  2. The exact raw reply format from the power meter's 'read2:pow?' query
  3. Whether termination characters need adjusting

Requires: pyvisa
    pip install pyvisa
"""

import time
import pyvisa

print('=' * 60)
print('STEP 1: List all visible VISA resources')
print('=' * 60)
rm = pyvisa.ResourceManager()
resources = rm.list_resources()
print('Resources found:', resources)

if not resources:
    print('\nNo resources found! Check that:')
    print('  - NI-VISA (or your VISA backend) is installed')
    print('  - GPIB adapter is connected and recognized by the OS')
    print('  - Instruments are powered on')
    raise SystemExit(1)

print()
print('=' * 60)
print('STEP 2: Connect to the power meter (GPIB0::4::INSTR)')
print('=' * 60)

PWM_ADDR = 'GPIB0::4::INSTR'   # change if your address differs
pwm = rm.open_resource(PWM_ADDR)
pwm.timeout = 5000

# Try default termination first
print(f'Default read_termination: {pwm.read_termination!r}')
print(f'Default write_termination: {pwm.write_termination!r}')

# Basic identification query - most SCPI instruments support *IDN?
try:
    idn = pwm.query('*IDN?').strip()
    print(f'*IDN? reply: {idn!r}')
except Exception as e:
    print(f'*IDN? failed: {e}')

print()
print('=' * 60)
print('STEP 3: Configure power meter and take one reading')
print('=' * 60)

pwm.write('sens2:pow:unit 1')
time.sleep(0.3)
pwm.write('sens2:pow:rang:auto 2')
time.sleep(0.3)
pwm.write('sens2:pow:wl1600 nm')
time.sleep(0.5)

# Try the read query a few different ways to see what comes back
print('\n--- Attempt A: pwm.query("read2:pow?") ---')
try:
    response = pwm.query('read2:pow?')
    print(f'Raw reply: {response!r}')
    print(f'Stripped: {response.strip()!r}')
except Exception as e:
    print(f'Query failed: {e}')

print('\n--- Attempt B: separate write + read ---')
try:
    pwm.write('read2:pow?')
    time.sleep(0.5)
    response = pwm.read()
    print(f'Raw reply: {response!r}')
except Exception as e:
    print(f'Write/read failed: {e}')

print('\n--- Attempt C: read raw bytes (bypasses termination parsing) ---')
try:
    pwm.write('read2:pow?')
    time.sleep(0.5)
    raw_bytes = pwm.read_raw()
    print(f'Raw bytes: {raw_bytes!r}')
except Exception as e:
    print(f'Raw read failed: {e}')

pwm.close()

print()
print('=' * 60)
print('DONE. Compare the three attempts above to figure out:')
print('  - Does the reply contain "NDCW+" or similar prefix?')
print('  - Is it empty in some attempts but not others?')
print('  - Are there stray \\r or \\n characters causing early cutoff?')
print('=' * 60)