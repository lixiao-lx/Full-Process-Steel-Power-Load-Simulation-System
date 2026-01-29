import shutil
import os
from fmpy import read_model_description, extract

def inspect_fmu_variables(fmu_path):
    if not os.path.exists(fmu_path):
        print(f"错误: 找不到文件: {fmu_path}")
        return

    print(f"正在读取 FMU: {fmu_path} ...")

    unzip_dir = extract(fmu_path)
    
    try:
        model_description = read_model_description(unzip_dir, validate=False)
        
        print("\n" + "="*80)
        print(f"模型名称 (Model Name): {model_description.modelName}")
        print(f"FMI 版本: {model_description.fmiVersion}")
        print(f"变量总数: {len(model_description.modelVariables)}")
        print("="*80 + "\n")

        header_fmt = "{:<50} | {:<10} | {:<10} | {:<10}"
        print(header_fmt.format("变量名 (Name)", "因果性", "类型", "VR (ID)"))
        print("-" * 90)
        
        inputs = []
        outputs = []
        others = []

        for var in model_description.modelVariables:

            name = var.name
            vr = var.valueReference
            type_name = var.type
            causality = var.causality if var.causality else "local"
            
            row = header_fmt.format(str(name), str(causality), str(type_name), str(vr))
            
            if causality == 'input' or causality == 'parameter':
                inputs.append(row)
            elif causality == 'output':
                outputs.append(row)
            else:
                others.append(row)
        
        print(f"--- [Output] 输出变量 (用于记录结果) ---")
        for row in outputs:
            print(row)
            
        print(f"\n--- [Input/Parameter] 输入与参数 (用于设置) ---")
        for row in inputs:
            print(row)

        print(f"\n--- [Local/Internal] 内部变量 ---")
        for i, row in enumerate(others):
            if i < 20: 
                print(row)
        if len(others) > 20:
            print(f"... (还有 {len(others)-20} 个内部变量未显示)")

        print("="*80)
        print("提示：请复制上面的 '变量名' 替换到你的仿真脚本中。")

    except Exception as e:
        print(f"读取失败: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if os.path.exists(unzip_dir):
            shutil.rmtree(unzip_dir)

if __name__ == "__main__":
    FMU_FILE = r'D:\钢铁电力负荷预测\eaf_sim_v3.0\simulink_EAF\setup_EAF_text.fmu'
    
    inspect_fmu_variables(FMU_FILE)