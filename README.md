# Full-Process-Steel-Power-Load-Simulation-System
<img width="150" height="60" alt="logo" src="https://github.com/user-attachments/assets/6573d6d2-9881-4d6a-9a91-9dccbaffbddc" />
  <br/>
  
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![AnyLogic](https://img.shields.io/badge/Simulation-AnyLogic-green)](https://www.anylogic.com/)
[![MATLAB](https://img.shields.io/badge/Model-MATLAB%2FSimulink%20FMU-orange)](https://www.mathworks.com/)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)



**Full-Process-Steel-Power-Load-Simulation-System** is a multi-layer hybrid simulation platform designed to simulate and analyze power load characteristics during the steel production process.

This project innovatively adopts a three-layer architecture consisting of **LLM (Large Language Model) + AnyLogic (Discrete Event Simulation) + MATLAB FMU (Physical Mechanism Model)**. It achieves end-to-end generation from vague operational descriptions to precise power load waveforms.

## 📖 Introduction

The steel industry is a major consumer of electricity, characterized by loads with strong impacts, large fluctuations, and non-linearity. This system aims to assist:

🏭 **Factories**: Optimize production schedules, reduce demand charges, and perform virtual commissioning.

⚡ **Power Grids**: Analyze power quality and evaluate microgrid stability.

🔬 **Research**: Provide high-quality synthetic data for load prediction algorithms.

### Core Advantages
1.  **Intelligent Configuration**: Utilizes an LLM with a built-in metallurgical expert knowledge base to automatically convert natural language descriptions into professional simulation parameters.
2.  **Fusion of Mechanism & Process**: AnyLogic handles macro-logistics and process constraints, while MATLAB FMU handles micro-electrical physical responses.
3.  **High Fidelity**: Encapsulates physical models based on the FMU (Functional Mock-up Unit) standard to ensure the physical authenticity of energy consumption calculations.

## 🏗️ System Architecture

This system uses Python as the data flow layer, connecting the LLM, AnyLogic, and MATLAB FMU modules to form a closed-loop data stream.

### Three-Layer Architecture Details
1.  **LLM Parameter Configuration Layer**:
*   Contains built-in metallurgical expert knowledge base Prompts.
*   Parses user requirements (e.g., "Produce a heat of high-strength steel using 100t of sheared scrap..."), generating two standard JSON configuration files: `control_params.json` (Control Profile) and `config_params.json` (System Configuration Profile).
2.  **AnyLogic Process Simulation Layer**:
*   Acts as the main simulation engine, reading JSON files to set constraints.
*   Simulates discrete events such as crane scheduling, ladle turnover, and process waiting times.
*   Responsible for triggering the start and end of each process.
3.  **MATLAB/Simulink Physical Mechanism Layer**:
*   Individual energy-consuming devices (EAF, LF, CC) are encapsulated as FMU modules.
*   Called by AnyLogic to input state variables and output real-time power, voltage, and current.


## ✨ Key Features

**LLM-Driven Parameter Generation**:
*   Automatically generates reasonable parameters such as smelting duration, transformer tap positions, and carbon/oxygen injection rates.
*   Supports scenario switching like "different furnace types," "scrap varieties," and "full-load modes."
    
**FMU Modular Co-simulation**:
*   Supports the FMI 2.0 standard, integrating electrical models compiled by MATLAB/Simulink.
    
**Full-Process Coverage**:
*   Covers the entire process: Electric Arc Furnace (EAF) -> Ladle Furnace (LF) -> Continuous Casting (CC) -> Rolling Mill.
    
**Data Standardization**:
*   Python scripts automatically clean raw output data to generate standard CSV data files ranging from second-level to hour-level resolution based on production schedules.

## 📂 Directory Structure

```text
steel-load-simulation/
├── LLM_config/            # [Layer 1] LLM Config Generation Module
│   ├── prompt_templates/  # Metallurgical Expert Prompt Templates
│   ├── llm_client.py      # LLM API Interface
│   └── output_json/       # Generated JSON Config Files
├── AnyLogic_simulation/   # [Layer 2] AnyLogic Simulation Project
│   ├── models/            # .alp Simulation Model Files
│   └── database/          # Database files required for simulation
├── matlab_fmu_library/    # [Layer 3] FMU Physical Model Library
│   ├── eaf_model.fmu      # Electric Arc Furnace FMU
│   ├── lf_model.fmu       # Ladle Furnace FMU
│   └── cc_model.fmu       # Rolling Mill FMU
├── python/                # Python Scripts & Tools
│   ├── run_eaf_fmu.py     # Script to run EAF FMU
│   ├── run_lf_fmu.py      # Script to run LF FMU
│   ├── run_cc_fmu.py      # Script to run CC FMU
│   └── data_processing.py # AnyLogic Output Data Processing
├── data/
│   ├── PV/Wind/ESS/       # PV, Wind, ESS Data
│   └── office_schedule/   # Office Lighting Load Data
├── results/               # Simulation Results Output
│   ├── visualization.py
│   ├── data_loader.py
│   └── .csv.plot          # Result Visualization Charts
├── main.py                # System Entry Point
├── requirements.txt       # Environment Dependencies
└── README.md              # Documentation
```

## 🚀 Quick Start

### Prerequisites
*   Python 3.8+
*   AnyLogic Professional / University
*   MATLAB/Simulink R2020b or higher

### Step 1: Generate Configuration
Run the Python script to generate the necessary JSON parameter files for simulation using the LLM.

```bash
python main.py --mode config --steel_grade "SWRH82B" --scenario "high_throughput"
```
*Output: Generates `control_params.json` and `config_params.json` in the `LLM_config/output_json/` directory.*

### Step 2: Run Simulation
Start AnyLogic (bridged via Python) and load the JSON files generated in the previous step for inference.

```bash
python main.py --mode simulation --config_dir ./LLM_config/output_json/
```

### Step 3: Analyze Results

```bash
python main.py --mode analyze --input ./results/simulation_output.csv
```

## 📊 Examples

### 1. Packaged EAF mechanism model
The packaged model is provided as an FMU file for AnyLogic.

<img width="595" height="262" alt="341b680b70b817b0876a9c9b4b5b7b3c" src="https://github.com/user-attachments/assets/9abc3f95-05f2-425b-adff-2fbcbde4bbed" />

### 2. EAF Current Waveform under Complex Conditions
Solveing by step based on the physical model.

<img width="350" height="248" alt="fe88eae5921477867d3c63257eaecb09" src="https://github.com/user-attachments/assets/488c1d58-fa96-4168-b124-3c1cc8646069" />

### 3. Steel Smelting Process Flow Chart
Short-process steelmaking process.

<img width="512" height="106" alt="91ce2f334d9a28d3ca56b455fafaa1f2" src="https://github.com/user-attachments/assets/9a7e4d13-5d20-45c4-9878-774eec2d9da8" />

### 4. Full-Process Power Superposition
Electricity consumption in steel smelting.

<img width="450" height="180" alt="modified_steel_plant_plot1" src="https://github.com/user-attachments/assets/13ae062f-3ae3-482b-85ab-8d66340ef401" />


## 🗓️ Roadmap

- [x] **v0.1**: Completed MATLAB Simulink models for EAF and LF and exported them as FMUs.
- [x] **v0.2**: Built the AnyLogic basic logistics framework and implemented static FMU calls.
- [ ] **v0.3**: Integrate the LLM module to enable text-to-config parameter generation.
- [ ] **v0.4**: Introduce Reinforcement Learning (RL) agents into AnyLogic to optimize scheduling strategies.

## 📜 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

## 🔗 Citation

If you use the architecture or code of this system in your research, please cite it as follows:

```bibtex
@software{steel_hybrid_sim_2026,
  author = {Zhengrui su},
  title = {Steel Power Load Simulation System},
  year = {2026},
  url = {https://github.com/yourusername/steel-load-simulation},
  note = {Integrates Continuous Modeling with Discrete Event Simulation}
}
```
