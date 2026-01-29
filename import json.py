import json
import shutil
import fmpy
from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave

# --- 1. 读取配置 ---
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

# --- 2. 全量参数映射 ---
def map_all_parameters(control_data, config_data):
    p_map = {}
    
    # === A. Control Stages===
    stages = control_data.get('control_stages', {})
    for i, stage_key in enumerate(['Stage1_Boredown', 'Stage2_Melting', 'Stage3_Foaming', 'Stage4_Refining']):
        s_data = stages.get(stage_key, {})
        idx = i + 1
        p_map[f'EAF.Control.Stage{idx}.k_tap'] = s_data.get(f'k_tap_{idx}')
        p_map[f'EAF.Control.Stage{idx}.Z_set'] = s_data.get(f'Z_set_{idx}')
        p_map[f'EAF.Control.Stage{idx}.O2']    = s_data.get(f'mass_flow_O2_{idx}')
        p_map[f'EAF.Control.Stage{idx}.C']     = s_data.get(f'mass_flow_{idx}')

    # === B. Fixed Parameters ===
    fixed = config_data.get('fixed_parameters', {})
    
    # Electrical
    elec = fixed.get('electrical', {})
    p_map['EAF.Fixed.R_sys'] = elec.get('R_sys')
    p_map['EAF.Fixed.X_sys'] = elec.get('X_sys')
    
    # Tap_Lookup_V
    tap_vals = elec.get('Tap_Lookup_V', [])
    for i, val in enumerate(tap_vals):
        p_map[f'EAF.Fixed.Tap_Lookup_V[1,{i+1}]'] = val

    # Geometry
    geo = fixed.get('geometry', {})
    p_map['EAF.Fixed.R_fur'] = geo.get('R_fur')
    p_map['EAF.Fixed.R_ele'] = geo.get('R_ele')
    if 'A_furnace' in geo:
        p_map['EAF.Fixed.A_furnace'] = geo.get('A_furnace')

    # Materials
    mat = fixed.get('materials', {})
    p_map['EAF.Fixed.rho_solid'] = mat.get('rho_solid')

    # Environment
    env = fixed.get('environment', {})
    p_map['EAF.Fixed.T_amb'] = env.get('T_amb')
    p_map['EAF.Fixed.T_out_steel'] = env.get('T_out_steel_target')

    # === C. Initial States ===
    init = config_data.get('initial_states', {})
    mass = init.get('mass', {})
    p_map['EAF.State.m_solid_0'] = mass.get('m_solid_0')
    p_map['EAF.State.m_liq']     = mass.get('m_liq_0')

    temp = init.get('temperature', {})
    p_map['EAF.State.T_solid'] = temp.get('T_solid_0')
    p_map['EAF.State.T_liq']   = temp.get('T_liq_0')

    return {k: v for k, v in p_map.items() if v is not None}

# --- 3. 智能查找变量 ---
def get_vr_info(model_description, var_name):
    for variable in model_description.modelVariables:
        if variable.name == var_name:
            return variable
    normalized_target = var_name.replace('.', '_').replace(' ', '')
    for variable in model_description.modelVariables:
        normalized_current = variable.name.replace('.', '_').replace(' ', '')
        if normalized_current == normalized_target:
            return variable
            
    return None

# --- 4. 核心验证逻辑 ---
def verify_all(fmu_path, json_control, json_config):
    control_data, config_data = load_json_config(json_control, json_config)
    if not control_data: return
    param_map = map_all_parameters(control_data, config_data)
    
    print(f"正在读取 FMU: {fmu_path} ...")
    unzip_dir = extract(fmu_path)
    
    try:

        model_description = read_model_description(unzip_dir, validate=False)
        
        fmu = FMU2Slave(guid=model_description.guid,
                        unzipDirectory=unzip_dir,
                        modelIdentifier=model_description.coSimulation.modelIdentifier,
                        instanceName='EAF_Verifier')
        
        fmu.instantiate()
        fmu.setupExperiment(startTime=0.0)
        fmu.enterInitializationMode()
        
        # --- 打印报告头 ---
        print("\n" + "="*120)
        print(f"{'全量参数验证与诊断报告':^120}")
        print("="*120)
        # 表头格式
        row_fmt = "{:<40} | {:<12} | {:<12} | {:<10} | {:<10} | {}"
        print(row_fmt.format("变量名 (JSON Key)", "设定值", "实际回读值", "匹配结果", "属性", "诊断信息"))
        print("-" * 120)

        match_count = 0
        fail_count = 0
        
        sorted_names = sorted(param_map.keys())

        for name in sorted_names:
            expected_val = param_map[name]
            var_info = get_vr_info(model_description, name)
            
            # 1. 变量未找到
            if var_info is None:
                print(row_fmt.format(name, str(expected_val), "---", "⚠️ 未找到", "---", "检查 FMU 变量名"))
                fail_count += 1
                continue
            
            # 获取属性
            vr = var_info.valueReference
            v_type = var_info.type
            variability = var_info.variability if var_info.variability else "continuous"
            
            try:
                if v_type == 'Real': fmu.setReal([vr], [float(expected_val)])
                elif v_type == 'Integer': fmu.setInteger([vr], [int(expected_val)])
                elif v_type == 'Boolean': fmu.setBoolean([vr], [bool(expected_val)])
            except Exception:
                pass

            actual_val = None
            try:
                if v_type == 'Real': actual_val = fmu.getReal([vr])[0]
                elif v_type == 'Integer': actual_val = fmu.getInteger([vr])[0]
                elif v_type == 'Boolean': actual_val = fmu.getBoolean([vr])[0]
            except Exception:
                actual_val = "Error"

            is_match = False
            diag_msg = ""
            
            if isinstance(actual_val, (int, float, bool)):
                if v_type == 'Real':
                    is_match = abs(actual_val - float(expected_val)) < 1e-4
                else:
                    is_match = (actual_val == expected_val)
            
            # 状态判定
            if is_match:
                status = "✅ 成功"
                match_count += 1
            else:
                status = "❌ 失败"
                fail_count += 1
                if variability == 'fixed':
                    diag_msg = "变量属性为 fixed，运行时不可修改"
                elif variability == 'constant':
                    diag_msg = "变量属性为 constant，完全硬编码"
                else:
                    diag_msg = "写入无效，可能被内部逻辑覆盖"

            # 格式化输出
            s_expect = f"{expected_val:.5g}" if isinstance(expected_val, float) else str(expected_val)
            s_actual = f"{actual_val:.5g}" if isinstance(actual_val, float) else str(actual_val)
            
            print(row_fmt.format(name, s_expect, s_actual, status, variability, diag_msg))

        fmu.exitInitializationMode()
        
        print("-" * 120)
        print(f"验证统计: 总计 {len(sorted_names)} | 成功: {match_count} | 失败/未找到: {fail_count}")
        print("="*120 + "\n")
        
        # --- 最终建议 ---
        if fail_count > 0:
            print("【诊断建议】")
            print("1. 如果 '未找到'：请使用 inspect_fmu.py 查看真实的变量名格式 (如 . vs _)。")
            print("2. 如果 '失败' 且属性为 'fixed'/'tunable'：")
            print("   说明 Simulink 导出时勾选了 'Inline Parameters'。")
            print("   -> 请在 Simulink 配置中取消勾选 'Inline parameters' 并重新生成 FMU。")
        else:
            print("🎉 所有参数验证通过！FMU 已正确接收 JSON 配置。")

        fmu.terminate()
        fmu.freeInstance()

    except Exception as e:
        print(f"运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'unzip_dir' in locals():
            shutil.rmtree(unzip_dir)

if __name__ == "__main__":
    # 路径配置
    FMU_FILE = r'D:\钢铁电力负荷预测\eaf_sim_v3.0\simulink_EAF\setup_EAF_text.fmu'
    JSON_CONTROL = r'D:\钢铁电力负荷预测\eaf_sim_v3.0\python\control_params.json'
    JSON_CONFIG = r'D:\钢铁电力负荷预测\eaf_sim_v3.0\python\config_params.json'
    
    verify_all(FMU_FILE, JSON_CONTROL, JSON_CONFIG)