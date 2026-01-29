import sys
from fmpy import simulate_fmu
import csv
from datetime import datetime
import numpy as np
import os
import io
import contextlib

# --- 步骤 1: 获取命令行参数 ---
if len(sys.argv) != 4:
    print("Error: Usage is 'python run_lf_fmu.py <mass_kg> <initial_temp> <target_temp>'", file=sys.stderr)
    sys.exit(1)

initial_mass_kg = float(sys.argv[1])
initial_temp_from_eaf = float(sys.argv[2])
target_temp_lf = float(sys.argv[3])

# --- 步骤 2: 设置 FMU 和输入信号 ---
fmu_filename = 'D:/钢铁电力负荷预测/simulink_LF/setup_LF_simulink.fmu'

input_dtype = [('time', '<f8'), 
               ('start_cmd', '<f8'), 
               ('m', '<f8'), 
               ('initial_temperature', '<f8'), 
               ('T_setpoint_LF', '<f8')]

input_data = [

    (0.0, 1.0, initial_mass_kg, initial_temp_from_eaf, target_temp_lf),
    (0.1, 0.0, initial_mass_kg, initial_temp_from_eaf, target_temp_lf),
]

input_signal = np.array(input_data, dtype=input_dtype)

output_vars = ['final_temperature', 'final_mass', 'final_state', 'total_energy']

# --- 步骤 3: 运行协同仿真 ---
stop_time_seconds = 2400 

try:
    temp_stdout = io.StringIO()
    with contextlib.redirect_stdout(temp_stdout):
        result = simulate_fmu(
            filename=fmu_filename,
            start_time=0,
            stop_time=stop_time_seconds,
            start_values={},
            input=input_signal,
            output=output_vars
        )

    
except Exception as e:
    print(f"Error during FMU simulation: {e}", file=sys.stderr)
    sys.exit(1)


# --- 日志保存部分 (保持您原有的逻辑) ---
try:
    save_directory = "D:/钢铁电力负荷预测/simulink_LF"
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = os.path.join(save_directory, f"lf_simulation_log_{timestamp}.csv")

    # 提取结果数据
    time_series = result['time']
    temp_series = result['final_temperature']
    energy_series = result['total_energy']
    state_series = result['final_state']

    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Time (s)', 'LF Temperature (C)', '耗电量 (kW)', 'LF State'])
        for i in range(len(time_series)):
            csv_writer.writerow([time_series[i], temp_series[i], energy_series[i], state_series[i]])
            
    print(f"Successfully saved detailed LF log to {csv_filename}", file=sys.stderr)

except Exception as e:
    print(f"Error saving LF CSV file: {e}", file=sys.stderr)

# --- 步骤 4: 提取最终结果并打印给AnyLogic  ---
final_temp_lf = result['final_temperature'][-1]
final_mass_lf = result['final_mass'][-1]
print(f"{final_temp_lf},{final_mass_lf}")
