import json
import csv
import shutil
import datetime
import fmpy
from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave

# --- 1. 读取JSON配置 ---
def load_json_config(control_file, config_file):
    try:
        with open(control_file, 'r', encoding='utf-8') as f:
            control_data = json.load(f)
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        return control_data, config_data
    except Exception as e:
        print(f"配置文件读取错误: {e}")
        return None, None

# --- 2. 映射参数 ---
def map_parameters(control_data, config_data):
    start_values = {}
    
    # === A. Control Stages ===
    stages = control_data.get('control_stages', {})
    
    for i, stage_key in enumerate(['Stage1_Boredown', 'Stage2_Melting', 'Stage3_Foaming', 'Stage4_Refining']):
        s_data = stages.get(stage_key, {})
        idx = i + 1

        start_values[f'EAF.Control.Stage{idx}.k_tap'] = s_data.get(f'k_tap_{idx}')
        start_values[f'EAF.Control.Stage{idx}.Z_set'] = s_data.get(f'Z_set_{idx}')
        start_values[f'EAF.Control.Stage{idx}.O2']    = s_data.get(f'mass_flow_O2_{idx}')
        start_values[f'EAF.Control.Stage{idx}.C']     = s_data.get(f'mass_flow_CO2_{idx}')

    # === B. Fixed Parameters ===
    fixed = config_data.get('fixed_parameters', {})
    
    # Electrical
    elec = fixed.get('electrical', {})
    start_values['EAF.Fixed.R_sys'] = elec.get('R_sys')
    start_values['EAF.Fixed.X_sys'] = elec.get('X_sys')

    tap_vals = elec.get('Tap_Lookup_V', [])
    for i, val in enumerate(tap_vals):
        var_name = f'EAF.Fixed.Tap_Lookup_V[1,{i+1}]'
        start_values[var_name] = val

    # Geometry
    geo = fixed.get('geometry', {})
    start_values['EAF.Fixed.R_fur'] = geo.get('R_fur')
    start_values['EAF.Fixed.R_ele'] = geo.get('R_ele')
    if 'A_furnace' in geo:
        start_values['EAF.Fixed.A_furnace'] = geo.get('A_furnace')

    # Materials
    mat = fixed.get('materials', {})
    start_values['EAF.Fixed.rho_solid'] = mat.get('rho_solid')
    
    # Environment
    env = fixed.get('environment', {})
    start_values['EAF.Fixed.T_amb'] = env.get('T_amb')
    start_values['EAF.Fixed.T_out_steel'] = env.get('T_out_steel_target')
    
    # === C. Initial States ===
    init = config_data.get('initial_states', {})
    mass = init.get('mass', {})
    start_values['EAF.State.m_solid_0'] = mass.get('m_solid_0')
    start_values['EAF.State.m_liq'] = mass.get('m_liq_0') 
    
    temp = init.get('temperature', {})
    start_values['EAF.State.T_solid'] = temp.get('T_solid_0')
    start_values['EAF.State.T_liq']   = temp.get('T_liq_0')

    return {k: v for k, v in start_values.items() if v is not None}


def get_vr(model_description, var_name):

    for variable in model_description.modelVariables:
        if variable.name == var_name:
            return variable.valueReference, variable.type
            
    normalized_target = var_name.replace('.', '_').replace(' ', '')
    
    for variable in model_description.modelVariables:
        normalized_current = variable.name.replace('.', '_').replace(' ', '')
        if normalized_current == normalized_target:
            return variable.valueReference, variable.type
            
    return None, None

# ---  主仿真逻辑 ---
def run_simulation_realtime(fmu_path, json_control, json_config, output_csv, stop_var_name="stop"):
    control_data, config_data = load_json_config(json_control, json_config)
    if not control_data: return
    
    param_map = map_parameters(control_data, config_data)
    

    output_names = [
        "EAF_Power_arc",
        "EAF_State_T_liq",
        "EAF_P_loss_elec",
        "EAF_P_loss_water",
        "EAF_P_loss_gas",
        "EAF_P_loss_total",
        "EAF_State_m_liq"
    ]

    print(f"正在解压 FMU: {fmu_path} ...")
    unzip_dir = extract(fmu_path)
    
    try:
        model_description = read_model_description(unzip_dir, validate=False)

        output_vrs = []
        found_output_names = []
        for name in output_names:
            vr, _ = get_vr(model_description, name)
            if vr is not None:
                output_vrs.append(vr)
                found_output_names.append(name)
            else:
                print(f"警告: FMU中未找到输出变量 '{name}' (请检查 inspect 脚本)")

        vr_stop, type_stop = get_vr(model_description, stop_var_name)
        if vr_stop is None:
            print(f"错误: FMU中未找到停止信号变量 '{stop_var_name}'")

        fmu = FMU2Slave(guid=model_description.guid,
                        unzipDirectory=unzip_dir,
                        modelIdentifier=model_description.coSimulation.modelIdentifier,
                        instanceName='EAF_Instance')

        fmu.instantiate()
        fmu.setupExperiment(startTime=0.0)
        fmu.enterInitializationMode()
        
        print("正在写入初始参数...")
        for name, value in param_map.items():
            vr, v_type = get_vr(model_description, name)
            if vr is not None:
                if v_type == 'Real':
                    fmu.setReal([vr], [float(value)])
                elif v_type == 'Integer':
                    fmu.setInteger([vr], [int(value)])
                elif v_type == 'Boolean':
                    fmu.setBoolean([vr], [bool(value)])


        fmu.exitInitializationMode()

        time = 0.0
        step_size = 1.0
        max_time = 10000 
        
        print(f"创建文件 '{output_csv}' 并开始仿真...")

        with open(output_csv, mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file)

            header = ["Time"] + found_output_names
            writer.writerow(header)
            
            print(f"开始步进 (步长={step_size}s), 实时数据正在写入...")
            
            while time <= max_time:

                fmu.doStep(currentCommunicationPoint=time, communicationStepSize=step_size)
                
                time += step_size

                is_stopped = False
                if vr_stop is not None:
                    if type_stop == 'Boolean':
                        val = fmu.getBoolean([vr_stop])[0]
                        is_stopped = val
                    elif type_stop == 'Real':
                        val = fmu.getReal([vr_stop])[0]
                        is_stopped = (val >= 0.99)
                    elif type_stop == 'Integer':
                        val = fmu.getInteger([vr_stop])[0]
                        is_stopped = (val == 1)

                vals = fmu.getReal(output_vrs)

                row = [time] + vals
                writer.writerow(row)

                if is_stopped:
                    print(f"*** 检测到 Stop 信号 (t={time}s) ***")
                    print("仿真正常停止。")
                    break
            
            print(f"仿真结束，数据已完整保存至: {output_csv}")

        fmu.terminate()
        fmu.freeInstance()

    except Exception as e:
        print(f"运行出错: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if 'unzip_dir' in locals():
            try:
                shutil.rmtree(unzip_dir)
            except:
                pass


if __name__ == "__main__":

    FMU_FILE = 'D:/钢铁电力负荷预测/eaf_sim_v3.0/simulink_EAF/setup_EAF_text.fmu'
    JSON_CONTROL = 'D:/钢铁电力负荷预测/eaf_sim_v3.0/python/control_params.json'
    JSON_CONFIG = 'D:/钢铁电力负荷预测/eaf_sim_v3.0/python/config_params.json'
    
    current_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_CSV = f'D:/钢铁电力负荷预测/eaf_sim_v3.0/result/eaf_simulation_log_{current_timestamp}.csv'
    print(f"本次仿真结果将保存至: {OUTPUT_CSV}")

    STOP_VARIABLE_NAME = "stop" 
    
    run_simulation_realtime(FMU_FILE, JSON_CONTROL, JSON_CONFIG, OUTPUT_CSV, STOP_VARIABLE_NAME)