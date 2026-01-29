import sys
import logging
import numpy as np
import os
import csv
import datetime
from fmpy import simulate_fmu

logging.getLogger().setLevel(logging.ERROR)

if len(sys.argv) != 4:
    print("Error: Usage is 'python run_cc_fmu.py <inlet_temp> <mass_kg> <cast_speed>'", file=sys.stderr)
    sys.exit(1)

inlet_temp = float(sys.argv[1])
mass_kg    = float(sys.argv[2])
cast_speed = float(sys.argv[3])

input_data = np.array(
    [(0.0, inlet_temp, mass_kg, cast_speed)],
    dtype=[
        ('time', np.float64), 
        ('T_in', np.float64), 
        ('m_in', np.float64), 
        ('v_cast', np.float64)
    ]
)

fmu_filename = 'D:/钢铁电力负荷预测/simulink_CC/setup_CC_simulink.fmu'
log_dir = r'D:\钢铁电力负荷预测\simulink_CC'

try:
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    result = simulate_fmu(
        filename=fmu_filename,
        start_time=0,
        stop_time=20000, 
        input=input_data, 
        output=['T_out', 'total_energy'],
        step_size=1.0 
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    csv_filename = f"CC_Simulation_Log_{timestamp}.csv"
    csv_path = os.path.join(log_dir, csv_filename)

    # 写入 CSV 文件
    with open(csv_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Time', 'Temperature_C', 'Total_Energy_kWh'])
        for i in range(len(result)):
            t = result['time'][i]
            temp = result['T_out'][i]
            energy = result['total_energy'][i]
            writer.writerow([t, temp, energy])

    final_temp = result['T_out'][-1]
    energy_kwh = result['total_energy'][-1]

    print(f"{final_temp},{energy_kwh}")

except Exception as e:

    err_log = os.path.join(log_dir, "python_error_log.txt")
    with open(err_log, "a") as ef:
        ef.write(f"{datetime.datetime.now()} - ERROR: {e}\n")
    print(f"ERROR: {e}")