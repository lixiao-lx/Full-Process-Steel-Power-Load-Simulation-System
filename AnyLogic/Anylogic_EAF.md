
### 架构总览

1.  **AnyLogic (主控 Master):**
    *   负责模拟钢包的生成、排队和在工位间的流转。
    *   为每个钢包Agent定义独特的属性（如废钢质量、目标温度）。
    *   在钢包进入EAF工位时，通过Java代码启动并初始化一个后台的MATLAB会话。
    *   通过一个循环事件（Event），以固定的时间步长（例如10秒）命令Simulink向前运行一步。
    *   在每一步之间，从Simulink读取关键状态，并检查任务是否完成。
    *   任务完成后，命令Simulink停止，并释放钢包Agent到下一个流程。

2.  **MATLAB/Simulink (从属计算引擎 Slave):**
    *   包含高精度的EAF设备机理模型。
    *   模型的关键工艺参数（如物料质量 `m`）被设置为输入端口（Inport），以便从AnyLogic接收。
    *   模型的关键状态（如当前温度、Stateflow状态）被设置为输出端口（Outport），以便被AnyLogic读取。
    *   被动地等待AnyLogic的命令（初始化、步进、停止）。

---

### 阶段一：MATLAB & Simulink 模型准备

此阶段确保您的Simulink模型是一个可以被外部精确控制的“黑盒模块”。

#### 步骤 1: 最终确认Simulink模型顶层接口

1.  **打开您的EAF Simulink主模型。**
2.  **检查输入端口 (`Inport`):**
    *   确保以下参数由 `Inport` 模块提供，而不是 `Constant` 模块：
        *   `start_cmd`: 用于启动Stateflow状态机。
        *   `T_setpoint`: 精炼期的目标温度。
        *   **`m`**: **物料质量 (kg)。这是控制进料质量的关键输入。**
    *   删除为这些输入供值的 `Constant` 模块，用 `Inport` 模块替换，并确保命名完全一致。

3.  **检查输出端口 (`Outport`):**
    *   确保您想从AnyLogic监控的每一个信号都连接到了一个 `Outport` 模块。
    *   必需的输出：
        *   `current_state_out`: 连接到 `Chart` 模块的 `current_state` 输出。
        *   `current_temperature`: 连接到 `Thermal_Model` 子系统的 `T_current` 输出。
    *   可选但建议的输出：
        *   `instantaneous_power`: 连接到 `Multiport Switch` 的输出。

#### 步骤 2: 确认MATLAB参数脚本

您的 `setup_EAF_parameters.m` 脚本依然非常重要，它负责定义所有Simulink模型内部使用的参数。

*   打开 `setup_EAF_parameters.m`。
*   脚本中的 `m = 100 * 1000;` 现在扮演的是**默认值**的角色。在实际运行中，AnyLogic会在仿真开始前通过Java代码**覆盖**这个值。

**此阶段完成后，您的Simulink模型已准备好被外部控制。**

---

### 阶段二：AnyLogic 环境配置

此阶段负责在AnyLogic和MATLAB之间建立通信的桥梁。

#### 步骤 1: 添加MATLAB引擎依赖

1.  **定位 `engine.jar` 文件**: 在您的MATLAB安装目录中找到它。典型路径为：
    `D:\matlab\Matlab 2020b 64bit\extern\engines\java\jar`
    （请根据您的MATLAB版本和安装路径进行调整）。

2.  **在AnyLogic中添加JAR包**:
    *   打开您的AnyLogic模型。
    *   在左侧的项目面板中，右键点击您的模型名称，选择 **属性 (Properties)**。
    *   切换到 **依赖 (Dependencies)** 标签页。
    *   在 **JAR文件和类文件夹 (JAR files and class folders)** 部分，点击 **浏览 (Browse)** 按钮，添加您找到的 `engine.jar` 文件。
    *   点击 **应用 (Apply)** 和 **OK**。

#### 步骤 2: 在模型启动时初始化MATLAB引擎

1.  在 `Main` 画布上（或您模型的主Agent中），从 **Agent** 面板拖入一个 **变量 (Variable)**。
    *   **名称**: `matlabEngine`
    *   **类型**: 选择 `Other`
    *   **Other type**: `com.mathworks.engine.MatlabEngine`

2.  在 `Main` 的属性面板中，找到 **Agent actions** > **启动时 (On startup)** 代码区，输入以下代码：

    ```java
    try {
        // 启动一个可共享的后台MATLAB会话
        matlabEngine = com.mathworks.engine.MatlabEngine.startMatlab();
        traceln("MATLAB Engine started successfully.");
    } catch (Exception e) {
        e.printStackTrace();
        traceln("FATAL: Failed to start MATLAB Engine. Simulation cannot proceed.");
    }
    ```

3.  在 **销毁时 (On destroy)** 代码区，输入以下代码以确保MATLAB进程能被安全关闭：

    ```java
    if (matlabEngine != null) {
        try {
            matlabEngine.close();
            traceln("MATLAB Engine closed.");
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
    ```

---

### 阶段三：AnyLogic 生产流程与控制逻辑实现

这是将所有部分串联起来的核心步骤。

#### 步骤 1: 定义Agent属性和生产流程

1.  **定义Agent**: 为代表钢包的Agent（例如，在 `Source` 模块中新建一个名为 `Ladle` 的Agent类型）添加参数：
    *   `scrapMass` (类型: `double`, 默认值: `100000`)
    *   `targetTemperature` (类型: `double`, 默认值: `1650`)

2.  **设置 `Source` 模块**: 在 `Source` 模块的 **离开时 (On exit)** 动作中，为每个出炉的钢包设置独特的质量：
    `agent.scrapMass = 95000 + uniform() * 10000; // 随机生成95到105吨的废钢质量`

3.  **搭建流程**: 使用 **Process Modeling Library** 搭建流程：`Source` -> `Queue` (eafQueue) -> `Service` (stationEAF) -> ...
### **第一步：定义代表钢包的Agent (Ladle)**

这一步的目标是创建一个新的代理（Agent）类型，它将作为我们模型中流动的实体（这里是钢包），并为它定义自定义的属性（参数）。

1.  **打开Projects视图**：在AnyLogic界面的左侧，找到并点击 **Projects** 视图。

2.  **新建Agent类型**：
    *   在 **Projects** 视图中，右键点击你的模型名称（通常是 "Main" 所在的顶级项目）。
    *   在弹出的菜单中，选择 **New** -> **Agent type**。
    *   在 **New Agent type** 对话框中：
        *   **Agent type name**: 输入 `Ladle`。
        *   选择 **Use in flowcharts as**：“Agent”。
        *   点击 **Finish**。

    现在，一个新的名为 `Ladle` 的编辑器标签页会打开。

3.  **为Ladle添加参数**：
    *   确保你当前正在编辑 `Ladle`（查看顶部标签页）。
    *   从左侧的 **Agent** 面板中，找到 **Parameter** 元素。
    *   将 **Parameter** 元素拖拽到 `Ladle` 的图形编辑器中。
    *   **添加 `scrapMass` 参数**:
        *   选中刚刚添加的参数，在右侧的 **Properties** 视图中进行设置：
        *   **Name**: 输入 `scrapMass`。
        *   **Type**: 选择 `double`。
        *   **Default value**: 输入 `100000`。
    *   **添加 `targetTemperature` 参数**:
        *   再次从 **Agent** 面板中拖拽一个 **Parameter** 元素到编辑器中。
        *   选中这个新参数，在 **Properties** 视图中设置：
        *   **Name**: 输入 `targetTemperature`。
        *   **Type**: 选择 `double`。
        *   **Default value**: 输入 `1650`。

至此，你已经成功创建了一个名为 `Ladle` 的Agent类型，并为它定义了两个核心属性：废钢质量 (`scrapMass`) 和目标温度 (`targetTemperature`)。

### **第二步：设置 `Source` 模块**

这一步我们将在主流程（通常是 `Main`）中创建一个钢包的来源，并为每个生成的钢包赋予一个随机的废钢质量。

1.  **返回Main编辑区**：点击名为 `Main` 的标签页，回到主流程的画布。

2.  **添加Source模块**：
    *   从左侧的 **Process Modeling Library** 面板中，找到 **Source** 模块。
    *   将其拖拽到 `Main` 的画布上。

3.  **配置Source模块**：
    *   选中 `Source` 模块，在右侧的 **Properties** 视图中进行详细设置。
    *   **New agent**: 在这里，我们需要告诉Source模块生成我们刚刚创建的 `Ladle` 类型的Agent。点击下拉菜单，选择 `Ladle`。
    *   展开 **Actions** 部分。
    *   找到 **On exit** 动作。这是一个代码框，你可以在这里编写Java代码，这些代码会在每个Agent离开Source模块时执行。
    *   在 **On exit** 的代码框中，输入以下代码：
        ```java
        agent.scrapMass = 95000 + uniform() * 10000;
        ```
        *   **代码解释**:
            *   `agent` 是一个关键字，代表当前正离开此模块的那个Agent（即那个 `Ladle`）。
            *   `agent.scrapMass` 表示我们要访问这个 `Ladle` Agent的 `scrapMass` 参数。
            *   `uniform()` 是AnyLogic内置的函数，会返回一个0到1之间的随机小数。
            *   `uniform() * 10000` 会生成一个0到10000之间的随机数。
            *   所以，`95000 + uniform() * 10000` 的结果就是一个介于95,000和105,000之间的随机浮点数，这对应了95到105吨的废钢质量。

### **第三步：搭建流程**

现在我们将按照指定的顺序，用 **Process Modeling Library** 的模块搭建起基本的炼钢流程。

1.  **确保Source模块已在画布上**。

2.  **添加Queue模块**：
    *   从 **Process Modeling Library** 面板中，找到 **Queue** 模块。
    *   将其拖拽到 `Source` 模块的右侧。
    *   选中 **Queue** 模块，在 **Properties** 视图中，将 **Name** 修改为 `eafQueue`。
    *   将 `Source` 模块的输出端口（右侧的小圆点）拖拽连接到 `eafQueue` 模块的输入端口（左侧的小圆点）。当你看到一条绿色的连接线时，表示连接成功。

3.  **添加Service模块**：
    *   从 **Process Modeling Library** 面板中，找到 **Service** 模块。`Service` 模块内部封装了一个排队（Queue）和一个延迟（Delay），非常适合模拟服务站、设备处理等场景。
    *   将其拖拽到 `eafQueue` 模块的右侧。
    *   选中 **Service** 模块，在 **Properties** 视图中，将 **Name** 修改为 `stationEAF`。
    *   将 `eafQueue` 模块的输出端口拖拽连接到 `stationEAF` 模块的输入端口。

4.  **继续搭建后续流程 (示例)**:
    *   你可以继续从 **Process Modeling Library** 中拖拽其他模块，例如另一个 `Service` 或一个 `Delay` 模块，来代表后续的精炼或连铸过程。
    *   将 `stationEAF` 的输出端口连接到下一个模块的输入端口，以此类推，构建完整的工艺流程。
    *   最后，通常会使用一个 **Sink** 模块来终结流程，它会销毁到达的Agent。将最后一个流程模块的输出连接到 **Sink** 模块的输入。

完成以上所有步骤后，你的模型 `Main` 画布上应该会有一条清晰的流程线：`Source` -> `eafQueue` -> `stationEAF` -> ... -> `Sink`。当你运行模型时，`Source` 模块会不断生成 `Ladle` Agent，每个 `Ladle` 在离开时都会被赋予一个95到105吨之间的随机废钢质量，然后进入 `eafQueue` 排队，等待 `stationEAF` 的处理。



#### 步骤 2: 创建全局变量和辅助函数

为了让监控事件能访问到当前正在处理的Agent和工位，我们需要一些全局变量。

1.  在 `Main` 中创建以下变量：
    *   `eafStation` (类型: `Service`)
    *   `eafAgent` (类型: `Ladle`)

2.  在 `Main` 中创建一个函数，用于启动监控事件：
    *   **函数名**: `create_EAF_MonitorEvent`
    *   **参数**:
        *   `station` (类型: `Service`)
        *   `agent` (类型: `Ladle`)
    *   **函数体**:
        ```java
        // 将当前处理的工位和agent保存到Main的全局变量中
        this.eafStation = station;
        this.eafAgent = agent;

        // 立即启动监控事件，并按设定的周期循环
        this.eafMonitorEvent.restart();
        ```

#### 步骤 3: 配置 `Service` (stationEAF) - 仿真启动器

`Service` 模块现在只负责初始化仿真，并移交控制权给监控事件。

1.  点击 `stationEAF` 模块，将其 **延迟时间 (Delay time)** 的类型设置为 **(超时) (timeout)**。
2.  在其 **动作 (Actions)** > **进入时 (On enter)** 代码区，输入以下代码：

    ```java
    if (main.matlabEngine == null) { traceln("Error: MATLAB Engine not ready."); return; }

    try {
        traceln("Initializing EAF simulation for agent with mass: " + agent.scrapMass + " kg.");
        String modelName = "your_eaf_model_name"; // ***在此处替换成你的Simulink文件名(不含.slx)***

        // --- 步骤 A: 发送此Agent的独特参数到MATLAB ---
        main.matlabEngine.putVariable("m", agent.scrapMass);
        main.matlabEngine.putVariable("T_setpoint", agent.targetTemperature);
        main.matlabEngine.putVariable("start_cmd", 1.0); // 发送启动命令

        // --- 步骤 B: 在MATLAB中准备Simulink模型 ---
        main.matlabEngine.eval("load_system('" + modelName + "')");
        main.matlabEngine.eval("setup_EAF_parameters"); // 运行参数设置脚本

        // --- 步骤 C: 启动Simulink并立即暂停，等待步进命令 ---
        main.matlabEngine.eval("set_param('" + modelName + "','SimulationCommand','start')");
        main.matlabEngine.eval("set_param('" + modelName + "','SimulationCommand','pause')");

        // --- 步骤 D: 启动监控事件来驱动仿真 ---
        main.create_EAF_MonitorEvent(stationEAF, agent);

    } catch (Exception e) {
        e.printStackTrace();
        traceln("Error during MATLAB/Simulink initialization.");
    }
    ```

#### 步骤 4: 创建 `Event` (eafMonitorEvent) - 协同仿真引擎

1.  在 `Main` 画布上，从 **Agent** 面板拖入一个 **事件 (Event)**，命名为 `eafMonitorEvent`。
2.  **属性设置**:
    *   **触发器类型 (Trigger type)**: `Timeout`
    *   **模式 (Mode)**: `Cyclic`
    *   **循环时间 (Recurrence time)**: `10` **`Seconds`** (这是仿真步长，可根据精度和速度要求调整)
3.  在 `eafMonitorEvent` 的 **动作 (Action)** 代码区，输入以下代码：

    ```java
    if (eafStation.size() == 0) { eafMonitorEvent.restart(); return; }

    try {
        String modelName = "your_eaf_model_name"; // ***再次替换成你的Simulink文件名***

        // --- 步骤 A: 命令Simulink向前运行一个步长 ---
        main.matlabEngine.eval("set_param('" + modelName + "','SimulationCommand','step')");

        // --- 步骤 B: 实时从Simulink输出端口读取状态数据 ---
        String getStateCmd = "get_param('" + modelName + "/current_state_out','RuntimeObject').Outport(1).Data";
        String getTempCmd = "get_param('" + modelName + "/current_temperature','RuntimeObject').Outport(1).Data";

        double currentState = main.matlabEngine.getVariable(getStateCmd);
        double currentTemp = main.matlabEngine.getVariable(getTempCmd);

        traceln("EAF Status: Time=" + time() + "s, State=" + currentState + ", Temp=" + String.format("%.2f", currentTemp) + "°C");

        // --- 步骤 C: 检查完成条件 (Stateflow状态为4) ---
        if (currentState == 4) {
            traceln("EAF process finished for agent: " + eafAgent + " at time " + time());

            // 1. 停止Simulink仿真
            main.matlabEngine.eval("set_param('" + modelName + "','SimulationCommand','stop')");
            // 2. 将Simulink的启动命令重置为0，为下次做准备
            main.matlabEngine.putVariable("start_cmd", 0.0);
            // 3. 停止这个监控事件的循环
            eafMonitorEvent.restart();
            // 4. 从Service模块中释放Agent，使其进入下一流程
            eafStation.free(eafAgent);
        }

    } catch(Exception e) {
        e.printStackTrace();
        traceln("Error during Simulink step execution. Stopping monitor.");
        eafMonitorEvent.restart();
    }
    ```

---

### 阶段四：运行与扩展

1.  **运行AnyLogic模型**: 点击运行按钮。
2.  **观察控制台**: 您将看到：
    *   "MATLAB Engine started successfully."
    *   "Initializing EAF simulation for agent with mass: XXXXX.XX kg."
    *   随后，每隔10秒（仿真时间）打印一行 "EAF Status: ..."，实时显示Simulink的内部状态。
    *   最后，打印 "EAF process finished..."，同时您会看到钢包Agent在流程图上离开`stationEAF`。
3.  **扩展到LF炉**:
    *   **复制模式**: 对LF炉重复上述所有步骤。创建一个`LF_Model.slx`，`setup_LF_parameters.m`，以及在AnyLogic中创建`stationLF`，`lfMonitorEvent`，`create_LF_MonitorEvent`等。
    *   **串联流程**: 将`stationEAF`的输出连接到`stationLF`的输入（可能中间有队列）。当Agent从EAF被`free()`后，它会自动进入LF的流程，触发LF的协同仿真。

您现在已经成功搭建了一个功能完备的、可交互的、高精度协同仿真系统。





好的，遵照您的要求，这是一份从零开始、整合了所有关键点的最终完整版仿真流程搭建指南。

本指南将引导您完成**AnyLogic + Python桥梁 + Simulink FMU**这一最稳定、最可靠的协同仿真方案。

---

### **最终方案架构：三位一体**

1.  **AnyLogic (流程主控)**: 负责宏观的工厂物流、钢包排队和天车调度。它决定**“何时”**和**“哪个钢包”**需要进行冶炼。
2.  **Simulink FMU (精细化计算引擎)**: 您已搭建好的EAF模型。它负责具体的冶炼过程计算，包括温度变化和状态判断。它回答**“冶炼过程如何进行”**以及**“何时完成”**。
3.  **Python 脚本 (通信桥梁)**: 作为一个独立的中间人，负责在AnyLogic和FMU之间传递数据和命令。它是整个协同仿真的**“翻译官”**和**“执行者”**。

---

### **第一阶段：准备计算引擎 (Simulink FMU)**

这一阶段的目标是得到一个封装了您所有EAF逻辑的、可被外部程序调用的`.fmu`文件。

1.  **最终确定模型接口**:
    *   在您的Simulink模型中，确保所有需要从AnyLogic传入的参数都已换成**`Inport`**模块。关键输入包括：
        *   `start_cmd` (启动/重置命令, double)
        *   `m` (钢水质量, 单位kg, double)
        *   `T_setpoint` (目标温度, 单位°C, double)
    *   确保所有需要传回给AnyLogic的结果都连接到**`Outport`**模块。关键输出包括：
        *   `current_temperature` (最终温度, double)
        *   `current_state_out` (状态码, double)
        *   **(可选)** `total_energy` (总耗电量, double)

2.  **导出为FMU**:
    *   在Simulink中，进入 **Apps** 标签页，打开 **Simulink Compiler**。
    *   点击工具栏的 **Export to FMU**。
    *   在配置窗口中，进行以下设置：
        *   **Save as**: 选择一个简单、无中文、无空格的路径，例如 `C:/MySteelSim/EAF_Furnace.fmu`。**请务必记住这个路径**。
        *   **FMU version**: `2.0`
        *   **Kind**: `Co-Simulation`
    *   点击 **Package** 按钮。稍等片刻，您将在指定路径下找到 `EAF_Furnace.fmu` 文件。
    *   **至此，Simulink部分的工作已全部完成。**

---

### **第二阶段：搭建通信桥梁 (Python 脚本)**

这一阶段的目标是创建一个Python脚本，该脚本能够加载您的FMU，运行一次完整的冶炼仿真，并返回最终结果。

1.  **安装Python环境和依赖库**:
    *   确保您的电脑上已安装Python (推荐版本 3.8 或更高)。
    *   打开您电脑的命令行工具 (CMD或PowerShell)，输入并执行以下命令来安装FMPy库：
        ```bash
        pip install fmpy
        ```

2.  **创建Python脚本**:
    *   在您存放FMU的文件夹内 (例如 `C:/MySteelSim/`)，创建一个新的文本文件，将其命名为 `run_eaf_fmu.py`。
    *   将以下代码**完整地**复制并粘贴到该文件中：

    ```python
    # run_eaf_fmu.py

    import sys
    from fmpy import simulate_fmu

    # --- 步骤 1: 检查并从命令行获取AnyLogic传入的参数 ---
    if len(sys.argv) != 3:
        # 如果参数数量不对，打印错误信息并退出，这有助于调试
        print("Error: Usage is 'python run_eaf_fmu.py <mass_in_kg> <target_temperature>'")
        sys.exit(1)

    initial_mass_kg = float(sys.argv[1])
    target_temp = float(sys.argv[2])

    # --- 步骤 2: 定义FMU文件路径和输入/输出变量 ---
    # !重要提示! 请确保这里的路径与您实际存放FMU的路径完全一致
    fmu_filename = 'C:/MySteelSim/EAF_Furnace.fmu'

    # 'start_cmd', 'm', 'T_setpoint' 必须与Simulink Inport名称完全一致
    inputs = {
        'start_cmd': 1,
        'm': initial_mass_kg,
        'T_setpoint': target_temp,
    }

    # 'current_temperature', 'current_state_out' 必须与Simulink Outport名称完全一致
    output_vars = ['current_temperature', 'current_state_out']

    # --- 步骤 3: 调用FMPy运行一次完整的协同仿真 ---
    # stop_time设置一个足够大的值，确保仿真能靠Stateflow逻辑自己结束
    result = simulate_fmu(
        filename=fmu_filename,
        start_time=0,
        stop_time=7200,  # 넉넉하게 2시간 설정
        input=inputs,
        output=output_vars
    )

    # --- 步骤 4: 提取最终结果并以特定格式打印给AnyLogic ---
    # FMPy返回的是一个时间序列，[-1]代表取序列的最后一个值
    final_temp = result['current_temperature'][-1]
    final_state = result['current_state_out'][-1]
    
    # 打印最终温度。这是AnyLogic唯一会读取的信息。
    # 您也可以根据需要打印更多信息，用逗号隔开，例如 f"{final_temp},{total_energy}"
    print(f"{final_temp}")
    
    ```

---

### **第三阶段：搭建流程主控 (AnyLogic)**

这一阶段，我们将在AnyLogic中搭建宏观流程，并通过调用Python脚本来驱动精细化计算。

1.  **定义`Ladle`智能体**:
    *   在AnyLogic项目中，新建一个名为`Ladle`的智能体类型。
    *   从“面板”的`Agent`选项卡中，拖入两个“参数”到`Ladle`的编辑区：
        *   `mass`: 类型 `double`，代表钢水质量 (单位: **吨**)。
        *   `temperature`: 类型 `double`，代表钢水温度 (单位: **°C**)。

2.  **搭建可视化流程图**:
    *   在`Main`的画布上，使用`流程建模库 (Process Modeling Library)`搭建以下流程：
        *   `Source`: 用于生成`Ladle`智能体。在`New agent`处选择`Ladle`。可在`On startup`代码中设置初始值，如 `agent.mass = 100; agent.temperature = 1450;`。
        *   `Queue`: 炉前等待区。
        *   `(可选) MoveTo`或`MoveByCrane`: 模拟物理运输。
        *   `Delay`: **这是代表整个EAF冶炼工位的核心模块**。将其命名为 `delayEAF`。
        *   `(可选) MoveTo`或`MoveByCrane`: 模拟出炉运输。
        *   `Sink`: 流程终点。

3.  **编写核心Java调用代码**:
    *   点击选中`delayEAF`模块。
    *   在右侧的“属性”面板中：
        *   设置**延迟时间 (Delay time)**: 这个时间现在是一个**估算值**，因为它真正的结束时间取决于外部脚本何时运行完毕。可以设为一个符合实际的分布，例如 `uniform(50, 60)` 分钟。
        *   找到 **Actions** 部分，在 **On at exit** 的代码框中，粘贴以下Java代码：

    ```java
    // On at exit of delayEAF

    // 1. 获取当前要离开此工位的钢包智能体
    Ladle currentLadle = (Ladle) agent;

    // 2. 构建将要在电脑命令行中执行的命令
    // 格式为: "python 脚本的绝对路径 参数1 参数2"
    // 注意单位转换：AnyLogic中质量是吨(t)，脚本需要公斤(kg)
    String command = "python C:/MySteelSim/run_eaf_fmu.py " + 
                     (currentLadle.mass * 1000) + " " + 
                     1650; // 目标温度，也可以是一个变量

    // 在AnyLogic控制台打印命令，这是非常重要的调试手段
    traceln("Executing command for Ladle: " + command);

    try {
        // 3. 执行外部Python脚本，并启动一个新进程
        Process process = Runtime.getRuntime().exec(command);

        // 4. 创建一个读取器，用来捕获Python脚本的print()输出
        java.io.BufferedReader reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(process.getInputStream())
        );
        
        // 5. 等待外部进程完全执行结束。AnyLogic的仿真时间会在此暂停，直到计算完成。
        process.waitFor();
        
        // 6. 读取Python脚本打印到控制台的那一行输出
        String output = reader.readLine();

        // 7. 解析输出结果并更新钢包的属性
        if (output != null && !output.isEmpty()) {
            traceln("Result received from FMU: " + output); // 打印收到的结果，用于调试
            double finalTemperature = Double.parseDouble(output);
            currentLadle.temperature = finalTemperature; // 更新钢包温度
        } else {
            // 如果脚本没有返回任何东西，打印警告
            traceln("Warning: No output was received from the FMU script.");
        }

    } catch (Exception e) {
        // 如果执行过程中出现任何错误 (如找不到Python, 脚本路径错误等)，打印详细错误信息
        e.printStackTrace();
    }
    ```

---

### **第四阶段：运行与验证**

1.  **保存所有文件** (Python脚本和AnyLogic项目)。
2.  **点击AnyLogic的运行按钮**启动仿真。
3.  **观察仿真过程**:
    *   您将看到`Ladle`智能体按照您设计的流程移动。
    *   当一个`Ladle`进入`delayEAF`模块后，它会停留您设置的“延迟时间”。
    *   **关键时刻**: 当`Ladle`准备离开`delayEAF`时，仿真会**短暂地停顿**。此时，您的电脑正在后台运行Python脚本来执行FMU仿真。对于复杂的FMU，这个停顿可能会持续几秒钟。
4.  **检查AnyLogic控制台**:
    *   您应该能看到用`traceln()`打印出的调试信息，包括“Executing command...”和“Result received...”。如果这里出现红色的Java错误信息，请根据错误提示检查您的代码或文件路径。
5.  **验证数据**:
    *   在仿真运行时，当一个`Ladle`已经通过了`delayEAF`模块后，点击这个`Ladle`智能体。
    *   在弹出的检查窗口中，查看其`temperature`参数。它的值应该已经被更新为由您的Simulink模型计算出的那个精确的最终温度。

至此，您已成功搭建了一个宏观物流与微观工艺计算相结合的、高度精细化且稳定可靠的钢铁生产仿真模型。


—————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
这一阶段的目标是得到一个封装了您所有EAF逻辑的、可被外部程序调用的`.fmu`文件。

1.  **最终确定模型接口**:
    *   在您的Simulink模型中，确保所有需要从AnyLogic传入的参数都已换成**`Inport`**模块。关键输入包括：
        *   `start_cmd` (启动/重置命令, double)
        *   `m` (钢水质量, 单位kg, double)
        *   `T_setpoint` (目标温度, 单位°C, double)
    *   确保所有需要传回给AnyLogic的结果都连接到**`Outport`**模块。关键输出包括：
        *   `current_temperature` (最终温度, double)
        *   `current_state_out` (状态码, double)
        *   **(可选)** `total_energy` (总耗电量, double)

2.  **导出为FMU**:
    *   在Simulink中，进入 **Apps** 标签页，打开 **Simulink Compiler**。
    *   点击工具栏的 **Export to FMU**。
    *   在配置窗口中，进行以下设置：
        *   **Save as**: 选择一个简单、无中文、无空格的路径，例如 `C:/MySteelSim/EAF_Furnace.fmu`。**请务必记住这个路径**。
        *   **FMU version**: `2.0`
        *   **Kind**: `Co-Simulation`
    *   点击 **Package** 按钮。稍等片刻，您将在指定路径下找到 `EAF_Furnace.fmu` 文件。
    *   **至此，Simulink部分的工作已全部完成。**

---

### **第二阶段：搭建通信桥梁 (Python 脚本)**

这一阶段的目标是创建一个Python脚本，该脚本能够加载您的FMU，运行一次完整的冶炼仿真，并返回最终结果。

1.  **安装Python环境和依赖库**:
    *   确保您的电脑上已安装Python (推荐版本 3.8 或更高)。
    *   打开您电脑的命令行工具 (CMD或PowerShell)，输入并执行以下命令来安装FMPy库：
        ```bash
        pip install fmpy
        ```

2.  **创建Python脚本**:
    *   在您存放FMU的文件夹内 (例如 `C:/MySteelSim/`)，创建一个新的文本文件，将其命名为 `run_eaf_fmu.py`。
    *   将以下代码**完整地**复制并粘贴到该文件中：

    ```python
    # run_eaf_fmu.py

    import sys
    from fmpy import simulate_fmu

    # --- 步骤 1: 检查并从命令行获取AnyLogic传入的参数 ---
    if len(sys.argv) != 3:
        # 如果参数数量不对，打印错误信息并退出，这有助于调试
        print("Error: Usage is 'python run_eaf_fmu.py <mass_in_kg> <target_temperature>'")
        sys.exit(1)

    initial_mass_kg = float(sys.argv[1])
    target_temp = float(sys.argv[2])

    # --- 步骤 2: 定义FMU文件路径和输入/输出变量 ---
    # !重要提示! 请确保这里的路径与您实际存放FMU的路径完全一致
    fmu_filename = 'C:/MySteelSim/EAF_Furnace.fmu'

    # 'start_cmd', 'm', 'T_setpoint' 必须与Simulink Inport名称完全一致
    inputs = {
        'start_cmd': 1,
        'm': initial_mass_kg,
        'T_setpoint': target_temp,
    }

    # 'current_temperature', 'current_state_out' 必须与Simulink Outport名称完全一致
    output_vars = ['current_temperature', 'current_state_out']

    # --- 步骤 3: 调用FMPy运行一次完整的协同仿真 ---
    # stop_time设置一个足够大的值，确保仿真能靠Stateflow逻辑自己结束
    result = simulate_fmu(
        filename=fmu_filename,
        start_time=0,
        stop_time=7200,  
        input=inputs,
        output=output_vars
    )

    # --- 步骤 4: 提取最终结果并以特定格式打印给AnyLogic ---
    # FMPy返回的是一个时间序列，[-1]代表取序列的最后一个值
    final_temp = result['current_temperature'][-1]
    final_state = result['current_state_out'][-1]
    
    # 打印最终温度。这是AnyLogic唯一会读取的信息。
    # 您也可以根据需要打印更多信息，用逗号隔开，例如 f"{final_temp},{total_energy}"
    print(f"{final_temp}")
    
    ```

--- 

### **第三阶段：搭建流程主控 (AnyLogic)**

这一阶段，我们将在AnyLogic中搭建宏观流程，并通过调用Python脚本来驱动精细化计算。

1.  **定义`Ladle`智能体**:
    *   在AnyLogic项目中，新建一个名为`Ladle`的智能体类型。
    *   从“面板”的`Agent`选项卡中，拖入两个“参数”到`Ladle`的编辑区：
        *   `mass`: 类型 `double`，代表钢水质量 (单位: **吨**)。
        *   `temperature`: 类型 `double`，代表钢水温度 (单位: **°C**)。

2.  **搭建可视化流程图**:
    *   在`Main`的画布上，使用`流程建模库 (Process Modeling Library)`搭建以下流程：
        *   `Source`: 用于生成`Ladle`智能体。在`New agent`处选择`Ladle`。可在`On startup`代码中设置初始值，如 `agent.mass = 100; agent.temperature = 1450;`。
        *   `Queue`: 炉前等待区。
        *   `(可选) MoveTo`或`MoveByCrane`: 模拟物理运输。
        *   `Delay`: **这是代表整个EAF冶炼工位的核心模块**。将其命名为 `delayEAF`。
        *   `(可选) MoveTo`或`MoveByCrane`: 模拟出炉运输。
        *   `Sink`: 流程终点。

3.  **编写核心Java调用代码**:
    *   点击选中`delayEAF`模块。
    *   在右侧的“属性”面板中：
        *   设置**延迟时间 (Delay time)**: 这个时间现在是一个**估算值**，因为它真正的结束时间取决于外部脚本何时运行完毕。可以设为一个符合实际的分布，例如 `uniform(50, 60)` 分钟。
        *   找到 **Actions** 部分，在 **On at exit** 的代码框中，粘贴以下Java代码：

    ```java
    // On at exit of delayEAF

    // 1. 获取当前要离开此工位的钢包智能体
    Ladle currentLadle = (Ladle) agent;

    // 2. 构建将要在电脑命令行中执行的命令
    // 格式为: "python 脚本的绝对路径 参数1 参数2"
    // 注意单位转换：AnyLogic中质量是吨(t)，脚本需要公斤(kg)
    String command = "python C:/MySteelSim/run_eaf_fmu.py " + 
                     (currentLadle.mass * 1000) + " " + 
                     1650; // 目标温度，也可以是一个变量

    // 在AnyLogic控制台打印命令，这是非常重要的调试手段
    traceln("Executing command for Ladle: " + command);

    try {
        // 3. 执行外部Python脚本，并启动一个新进程
        Process process = Runtime.getRuntime().exec(command);

        // 4. 创建一个读取器，用来捕获Python脚本的print()输出
        java.io.BufferedReader reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(process.getInputStream())
        );
        
        // 5. 等待外部进程完全执行结束。AnyLogic的仿真时间会在此暂停，直到计算完成。
        process.waitFor();
        
        // 6. 读取Python脚本打印到控制台的那一行输出
        String output = reader.readLine();

        // 7. 解析输出结果并更新钢包的属性
        if (output != null && !output.isEmpty()) {
            traceln("Result received from FMU: " + output); // 打印收到的结果，用于调试
            double finalTemperature = Double.parseDouble(output);
            currentLadle.temperature = finalTemperature; // 更新钢包温度
        } else {
            // 如果脚本没有返回任何东西，打印警告
            traceln("Warning: No output was received from the FMU script.");
        }

    } catch (Exception e) {
        // 如果执行过程中出现任何错误 (如找不到Python, 脚本路径错误等)，打印详细错误信息
        e.printStackTrace();
    }
    ```

---

### **第四阶段：运行与验证**

1.  **保存所有文件** (Python脚本和AnyLogic项目)。
2.  **点击AnyLogic的运行按钮**启动仿真。
3.  **观察仿真过程**:
    *   您将看到`Ladle`智能体按照您设计的流程移动。
    *   当一个`Ladle`进入`delayEAF`模块后，它会停留您设置的“延迟时间”。
    *   **关键时刻**: 当`Ladle`准备离开`delayEAF`时，仿真会**短暂地停顿**。此时，您的电脑正在后台运行Python脚本来执行FMU仿真。对于复杂的FMU，这个停顿可能会持续几秒钟。
4.  **检查AnyLogic控制台**:
    *   您应该能看到用`traceln()`打印出的调试信息，包括“Executing command...”和“Result received...”。如果这里出现红色的Java错误信息，请根据错误提示检查您的代码或文件路径。
5.  **验证数据**:
    *   在仿真运行时，当一个`Ladle`已经通过了`delayEAF`模块后，点击这个`Ladle`智能体。
    *   在弹出的检查窗口中，查看其`temperature`参数。它的值应该已经被更新为由您的Simulink模型计算出的那个精确的最终温度。

______
好的，这是一个非常棒的改进需求，让模型从静态配置变为动态交互是提升其可用性的关键一步。

遵照您的要求，我们将重新设计 `Ladle` 智能体的生成方式，并在主模型界面上添加可调节的控件来设置钢水初始参数和 EAF 的目标温度。

以下是完整的、从头开始的搭建流程。

---

### **AnyLogic 交互式模型搭建指南**

本指南将引导您搭建一个带有界面控件的 AnyLogic 模型。您将能够**在仿真运行时，手动输入每个钢包的初始质量和温度，并设定 EAF 炉的目标冶炼温度**，然后将这些参数传递给外部的 FMU 进行计算。

#### **第一阶段：(回顾) 定义 Ladle 智能体**

这一阶段保持不变。我们的 `Ladle` 智能体依然是数据的载体，其结构是正确的。

1.  **确保 `Ladle` 智能体存在**：
    *   在您的 AnyLogic 项目中，应有一个名为 `Ladle` 的智能体类型。
    *   该智能体必须包含两个 **参数 (Parameter)**：
        *   `mass` (类型: `double`, 代表质量，单位: 吨)
        *   `temperature` (类型: `double`, 代表温度，单位: °C)

    *如果您之前的项目中已经创建，则无需任何操作。*

#### **第二阶段：在 Main 界面上构建交互式控制面板**

这是本次修改的核心。我们不再将参数硬编码，而是在 `Main` 画布上创建变量，并用界面控件来控制这些变量。

1.  **在 Main 上创建参数以存储设定值**：
    *   打开 `Main` 的画布。
    *   从“面板”的 `Agent` 选项卡中，拖拽 **三个** `Parameter` 到 `Main` 画布的空白处。这些参数将作为我们界面控件的目标变量。
    *   **配置第一个参数 (用于初始质量)**：
        *   名称: `p_initialMass_ton`
        *   类型: `double`
        *   默认值: `100.0`
    *   **配置第二个参数 (用于初始温度)**：
        *   名称: `p_initialTemp_C`
        *   类型: `double`
        *   默认值: `1450.0`
    *   **配置第三个参数 (用于EAF目标温度)**：
        *   名称: `p_targetTemp_C`
        *   类型: `double`
        *   默认值: `1650.0`

2.  **添加用户界面 (UI) 控件**：
    *   从“面板”的 **控件 (Controls)** 选项卡中，我们将添加输入框和标签。
    *   **为“初始质量”添加控件**：
        1.  拖拽一个 **文本 (Text)** 控件到画布上。在属性中，设置 **文本** 为 `初始质量 (t):`。
        2.  拖拽一个 **编辑框 (Edit Box)** 控件，并将其放在标签旁边。
        3.  选中该编辑框，在“属性”面板中进行如下设置：
            *   **关联到**: 选择 `p_initialMass_ton (double)`。
            *   **类型 (Type)**: `Number (double)`。
            *   在 **操作 (Action)** 部分的代码框中输入: `p_initialMass_ton = value;`
    *   **为“初始温度”添加控件**：
        1.  拖拽一个 **文本 (Text)**，设置文本为 `初始温度 (°C):`。
        2.  拖拽一个 **编辑框 (Edit Box)** 到旁边。
        3.  选中编辑框，设置：
            *   **关联到**: `p_initialTemp_C (double)`
            *   **类型 (Type)**: `Number (double)`
            *   **操作 (Action)**: `p_initialTemp_C = value;`
    *   **为“EAF目标温度”添加控件**：
        1.  拖拽一个 **文本 (Text)**，设置文本为 `EAF目标温度 (°C):`。
        2.  拖拽一个 **编辑框 (Edit Box)** 到旁边。
        3.  选中编辑框，设置：
            *   **关联到**: `p_targetTemp_C (double)`
            *   **类型 (Type)**: `Number (double)`
            *   **操作 (Action)**: `p_targetTemp_C = value;`

    完成此步骤后，您的 `Main` 画布上应该有一个清晰的控制面板。

![image](https://storage.googleapis.com/agent-tools-storage/project-id/user-id/generated_image_2024-05-16-09:23:46.png)

#### **第三阶段：更新流程逻辑以使用界面控件**

现在，我们需要让流程模型（Source 模块和 Delay 模块）读取这些新的、可调节的参数值。

1.  **修改 `Source` 模块**：
    *   在 `Main` 的流程图中，选中 `Source` 模块。
    *   在“属性”面板中，找到 **操作 (Actions)** -> **启动时 (On startup)**。
    *   **替换** 原有的硬编码，使用我们刚刚在 `Main` 上创建的参数来初始化每一个新的 `Ladle` 智能体。修改后代码如下：
        ```java
        // agent 代表新创建的 Ladle 智能体
        // 从 Main 的参数中获取初始值并赋给它
        agent.mass = p_initialMass_ton;
        agent.temperature = p_initialTemp_C;
        ```

2.  **修改 `delayEAF` 模块的核心调用代码**：
    *   选中代表 EAF 工位的 `delayEAF` 模块。
    *   在“属性”面板中，找到 **操作 (Actions)** -> **On at exit**。
    *   我们需要修改构建 `command` 字符串的那一行，将原来硬编码的目标温度 `1650` 替换为我们创建的界面参数 `p_targetTemp_C`。

    **修改前**:
    ```java
    String command = "python D:/钢铁电力负荷预测/python/run_eaf_fmu.py " + 
                     (currentLadle.mass * 1000) + " " + 
                     1650; // <-- 这里是硬编码
    ```

    **修改后**:
    ```java
    String command = "python D:/钢铁电力负荷预测/python/run_eaf_fmu.py " + 
                     (currentLadle.mass * 1000) + " " + 
                     p_targetTemp_C; // <-- 改为从界面参数读取
    ```

    为了方便您操作，这里提供 **`On at exit`** 代码框的 **最终完整版本**：

    ```java
    // --- On at exit action for delayEAF block (Interactive Version) ---
    
    // 1. 获取当前钢包智能体
    Ladle currentLadle = (Ladle) agent;
    
    // 2. 构建命令字符串，从 Main 的参数 p_targetTemp_C 获取目标温度
    String command = "python D:/钢铁电力负荷预测/python/run_eaf_fmu.py " + 
                     (currentLadle.mass * 1000) + " " + 
                     p_targetTemp_C;
    
    // 3. (调试) 打印将要执行的命令
    traceln("Executing command for Ladle: " + command);
    
    try {
        // 4. 执行外部Python脚本
        Process process = Runtime.getRuntime().exec(command);
    
        // 5. 创建读取器，捕获Python脚本的输出（包括正常输出和错误输出）
        java.io.BufferedReader reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(process.getInputStream())
        );
        java.io.BufferedReader errorReader = new java.io.BufferedReader(
            new java.io.InputStreamReader(process.getErrorStream())
        );
        
        // 6. 等待外部进程执行结束
        process.waitFor();
        
        // 7. 读取并处理错误信息（如果有）
        StringBuilder errorOutput = new StringBuilder();
        String errorLine;
        while ((errorLine = errorReader.readLine()) != null) {
            errorOutput.append(errorLine).append("\n");
        }
        
        // 8. 读取并处理正常输出
        String output = reader.readLine();
        
        // 9. 根据结果更新模型
        if (errorOutput.length() > 0) {
            traceln("ERROR received from Python script:\n" + errorOutput.toString());
        } else if (output != null && !output.isEmpty()) {
            traceln("Result received from FMU: " + output);
            double finalTemperature = Double.parseDouble(output);
            currentLadle.temperature = finalTemperature; // 更新钢包温度
        } else {
            traceln("Warning: No output was received from the FMU script.");
        }
    
    } catch (Exception e) {
        e.printStackTrace();
    }
    ```

---

#### **第四阶段：运行与验证**

1.  **点击 AnyLogic 的运行按钮**启动仿真。
2.  **与界面交互**：
    *   在弹出的仿真窗口中，您会看到您设计的三个输入框和标签。
    *   **在第一个钢包被 `Source` 模块创建之前**，您可以修改输入框中的数值。例如，将初始质量改为 `110`，初始温度改为 `1430`，EAF 目标温度改为 `1680`。
3.  **观察和验证**：
    *   **验证初始值**：当一个新的 `Ladle` 智能体出现在流程图上时，立即点击它。在弹出的检查窗口中，确认它的 `mass` 和 `temperature` 参数是否与您在界面上输入的值一致。
    *   **验证调用参数**：当这个 `Ladle` 准备离开 `delayEAF` 时，观察下方的控制台。您应该看到 `Executing command...` 信息，并且命令中的第三个参数正是您在界面上设定的 EAF 目标温度（例如 `1680.0`）。
    *   **验证最终结果**：当 `Ladle` 离开 `delayEAF` 后，再次点击它，检查其 `temperature` 属性。这个值应该是您的 FMU 基于新的输入参数计算出的结果。

通过以上步骤，您就成功地将一个静态的仿真模型改造成了一个可以由用户在运行时动态调整关键参数的交互式模型。



# run_eaf_fmu.py (Updated Version)

import sys
from fmpy import simulate_fmu

# --- 步骤 1: 检查并从命令行获取AnyLogic传入的三个参数 ---
# 修改: 现在需要检查4个参数 (脚本名 + 3个输入值)
if len(sys.argv) != 4:
    # 修改: 更新错误提示信息
    print("Error: Usage is 'python run_eaf_fmu.py <mass_in_kg> <target_temperature> <initial_temperature>'")
    sys.exit(1)

initial_mass_kg = float(sys.argv[1])
target_temp = float(sys.argv[2])
initial_temp = float(sys.argv[3]) # 新增: 获取第三个参数，即初始温度

# --- 步骤 2: 定义FMU文件路径和输入/输出变量 ---
# !重要提示! 请确保这里的路径与您实际存放FMU的路径完全一致
# 您在之前例子中使用的路径是 "D:/钢铁电力负荷预测/python/EAF_Furnace.fmu"，请按需修改
fmu_filename = 'C:/MySteelSim/EAF_Furnace.fmu'

# 'start_cmd', 'm', 'T_setpoint', 'T' 必须与Simulink Inport名称完全一致
# 修改: 在inputs字典中添加新的初始温度输入'T'
inputs = {
    'start_cmd': 1,
    'm': initial_mass_kg,
    'T_setpoint': target_temp,
    'T': initial_temp,  # 新增: 将获取到的初始温度传给名为'T'的Inport
}

# 'current_temperature', 'current_state_out' 必须与Simulink Outport名称完全一致
output_vars = ['current_temperature', 'current_state_out']

# --- 步骤 3: 调用FMPy运行一次完整的协同仿真 ---
# stop_time设置一个足够大的值，确保仿真能靠Stateflow逻辑自己结束
result = simulate_fmu(
    filename=fmu_filename,
    start_time=0,
    stop_time=7200,
    input=inputs,
    output=output_vars
)

# --- 步骤 4: 提取最终结果并以特定格式打印给AnyLogic ---
# FMPy返回的是一个时间序列，[-1]代表取序列的最后一个值
final_temp = result['current_temperature'][-1]
final_state = result['current_state_out'][-1]

# 打印最终温度。这是AnyLogic唯一会读取的信息。
print(f"{final_temp}")



————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
### **诊断步骤**

#### **第 0 步：基础验证 - 在 Anylogic 之外手动运行**

这是最重要的一步，它将问题完全与 Anylogic 分离，以确认 Python 环境本身没有问题。

**Action:**
1.  打开 Windows 的 **命令提示符 (cmd.exe)**。
2.  **完整地** 复制 Anylogic 控制台输出的那条命令。
3.  在命令提示符窗口中，**右键点击** 粘贴该命令。它应该看起来完全一样：
    ```cmd
    python D:/钢铁电力负荷预测/python/run_eaf_fmu.py 100000.0 1650.0 25.0
    ```
4.  按下 **Enter** 键执行。

**What to Look For:**
*   您是否在命令行窗口中看到了 **两行** 输出？
    1.  `Successfully saved detailed log to D:/...`
    2.  `1864.6981057223184`
*   或者程序是否报错？

**Analysis:**
*   **如果这两行都正常显示**：这100%确认了您的 Python 脚本和环境是好的。问题 kesinlikle（绝对）出在 Anylogic/Java 如何调用它上面。请继续执行第 1 步。
*   **如果报错或没有显示数字**：问题出在您的 Python 环境或脚本本身。Anylogic 无法调用一个不能在命令行中独立运行的脚本。请先解决这里的错误。

---

#### **第 1 步：简化 - 用一个“哑巴”Python 脚本进行测试**

我们将用一个极其简单的 Python 脚本替换您复杂的 FMU 脚本。如果这个简单脚本能成功，就说明问题出在您原脚本的某个库（如 `fmpy` 或 `numpy`）与 I/O 流的交互方式上。

**Action:**
1.  在 `D:/钢铁电力负荷预测/python/` 文件夹中，创建一个新的文本文件，命名为 `test_script.py`。
2.  将以下代码粘贴到 `test_script.py` 中并保存：
    ```python
    import sys
    import time

    print("This is a message on standard output (stdout).")
    print("Another line on stdout.", file=sys.stdout)

    # 将一条消息打印到标准错误流
    print("This is a critical message on standard error (stderr).", file=sys.stderr)

    time.sleep(1) # 模拟一些工作

    # 打印最终结果，这是我们希望捕获的
    print("123.45")

    sys.stdout.flush()
    sys.stderr.flush()
    ```
3.  现在，修改您的 Anylogic Java 代码，让它调用这个新的、简单的脚本。**只需修改脚本名称**：
    ```java
    // 只需修改这一行中的脚本名
    String[] command = {
        "python", 
        "D:/钢铁电力负荷预测/python/test_script.py", // <--- 修改这里
        "arg1", "arg2", "arg3" // 参数现在不重要，只是占位符
    };
    
    // ... 后续的 ProcessBuilder 代码保持不变 ...
    ```
4.  运行 Anylogic 模型。

**What to Look For:**
*   查看 Anylogic 的控制台。您是否看到了从 `test_script.py` 打印出来的所有信息？
    *   `Line from script: This is a message on standard output (stdout).`
    *   `Line from script: Another line on stdout.`
    *   `Line from script: This is a critical message on standard error (stderr).`
    *   `Line from script: 123.45`
*   最终，模型是否成功将某个属性更新为了 `123.45`？

**Analysis:**
*   **如果这个简单脚本成功了**：恭喜！这证明您的 Anylogic/Java 代码是**正确**的。问题在于您原始的 `run_eaf_fmu.py` 脚本中的某个部分（很可能是 `simulate_fmu` 函数）正在以一种不寻常的方式处理输出流，导致它与 Java 的 `Process` 不兼容。在这种情况下，请直接跳到下面的 **“针对第1步成功的解决方案”**。
*   **如果连这个简单脚本都失败了（仍然没有输出）**：问题就在于 Anylogic 的执行环境本身。请继续执行第 2 步。

---

#### **第 2 步：消除歧义 - 使用 Python 的绝对路径**

Anylogic 运行时的 `PATH` 环境变量可能与您系统的 `PATH` 不同。它可能根本不知道 `python` 是什么。

**Action:**
1.  找到您 `python.exe` 的完整路径。
    *   在命令提示符 (cmd) 中，输入 `where python`。它会显示路径，例如 `C:\Users\YourUser\AppData\Local\Programs\Python\Python39\python.exe`。
2.  复制这个完整路径。
3.  修改您的 Anylogic Java 代码，用完整路径替换 `python`。
    ```java
    // 使用 python.exe 的绝对路径
    String[] command = {
        "C:\\Users\\YourUser\\AppData\\Local\\Programs\\Python\\Python39\\python.exe", // <-- 修改这里！注意使用双反斜杠\\
        "D:/钢铁电力负荷预测/python/run_eaf_fmu.py",
        String.valueOf(currentLadle.mass * 1000),
        String.valueOf(targetTemp_C),
        String.valueOf(currentLadle.temperature)
    };
    
    // ... ProcessBuilder 代码不变 ...
    ```
4.  再次运行 Anylogic 模型。

**Analysis:**
*   **如果这次成功了**：问题就是 Anylogic 找不到 `python`。使用绝对路径是稳定可靠的解决方案。
*   **如果仍然失败**：这是一个非常罕见但严重的环境问题，可能与权限或 Anylogic 的 JVM 配置有关。

---

### **针对第1步成功的解决方案**

如果您的 `test_script.py` 成功了，但 `run_eaf_fmu.py` 失败了，这意味着 `fmpy` 库可能“吞掉”了输出。解决方案是将 Python 的输出重定向到一个临时文件，然后让 Java 读取这个文件。这绕过了不稳定的 I/O 流。

**1. 修改 Python 脚本 (`run_eaf_fmu.py`)**

让它将最终结果写入一个固定的临时文件中。

```python
# ... (您的所有代码保持不变，直到最后) ...

# --- 步骤 4: 提取最终温度并保存到文件 ---
final_temp = result['current_temperature'][-1]

# 定义一个固定的输出文件路径
output_file_path = "D:/钢铁电力负荷预测/python/fmu_output.txt"

try:
    with open(output_file_path, 'w') as f:
        f.write(str(final_temp))
except Exception as e:
    # 如果写入失败，打印到stderr，帮助调试
    print(f"Error writing to output file: {e}", file=sys.stderr)

# (可选) 您仍然可以保留 print 语句用于手动调试
print(f"Final temp {final_temp} written to file.", file=sys.stderr)
```

**2. 修改 Anylogic Java 代码**

让它运行脚本，然后去读取那个文件的内容。

```java
// ... (构建 command 字符串/数组的代码不变) ...

try {
    ProcessBuilder pb = new ProcessBuilder(command);
    // 仍然建议合并流，以捕获Python的任何错误打印
    pb.redirectErrorStream(true);
    Process process = pb.start();

    // ---- 捕获并打印脚本的调试输出 ----
    java.io.BufferedReader processReader = new java.io.BufferedReader(
        new java.io.InputStreamReader(process.getInputStream())
    );
    String line;
    while ((line = processReader.readLine()) != null) {
        traceln("Script debug output: " + line); // 打印脚本的所有输出
    }
    // ---- 结束捕获 ----

    // 等待进程结束
    int exitCode = process.waitFor();
    traceln("Python script finished with exit code: " + exitCode);

    // ---- 从文件读取结果 ----
    String outputFilePath = "D:/钢铁电力负荷预测/python/fmu_output.txt";
    java.io.BufferedReader fileReader = new java.io.BufferedReader(
        new java.io.FileReader(outputFilePath)
    );
    String output = fileReader.readLine();
    fileReader.close(); // 及时关闭文件读取器

    if (output != null && !output.isEmpty()) {
        traceln("Result read from file: " + output);
        double finalTemperature = Double.parseDouble(output);
        currentLadle.temperature = finalTemperature;
        traceln("Update successful: Temp=" + finalTemperature);
    } else {
        traceln("Warning: Output file was empty or could not be read.");
    }

} catch (Exception e) {
    e.printStackTrace();
}
```





```java
// --- On at exit action for delayEAF block (PRODUCTION VERSION) ---
// This version calls the real FMU script with all required parameters.

// 1. 获取当前正在处理的钢包智能体
Ladle currentLadle = (Ladle) agent;

// 2. 定义Python解释器和脚本的路径
//    我们使用在测试中被验证为成功的 Anaconda Python 解释器绝对路径
String pythonPath = "D:/anaconda/python.exe"; 
String scriptPath = "D:/钢铁电力负荷预测/python/run_eaf_fmu.py"; // <--- 已切换为您的正式脚本

// 3. 构建将要执行的外部命令字符串
//    根据您的Python脚本要求，我们需要传递三个参数:
//    1. 质量 (kg): currentLadle.mass * 1000
//    2. EAF目标温度 (°C): p_targetTemp_C (从界面控件读取)
//    3. 初始温度 (°C): currentLadle.temperature (钢包进入EAF时的当前温度)
String command = "\"" + pythonPath + "\" \"" + scriptPath + "\" " + 
                 (currentLadle.mass * 1000) + " " + 
                 p_targetTemp_C + " " +
                 currentLadle.temperature; // <--- 新增了第3个参数：初始温度

// 4. (调试) 在 AnyLogic 控制台打印将要执行的命令
traceln("Executing command for Ladle: " + command);

try {
    // 5. 执行外部 Python 脚本
    Process process = Runtime.getRuntime().exec(command);

    // 6. 创建读取器，用于捕获 Python 脚本的输出（包括正常输出和错误输出）
    java.io.BufferedReader reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(process.getInputStream())
    );
    java.io.BufferedReader errorReader = new java.io.BufferedReader(
        new java.io.InputStreamReader(process.getErrorStream())
    );
    
    // 7. 等待外部进程执行完成
    process.waitFor();
    
    // 8. 读取并处理错误流中的信息
    StringBuilder errorOutput = new StringBuilder();
    String errorLine;
    while ((errorLine = errorReader.readLine()) != null) {
        errorOutput.append(errorLine).append("\n");
    }
    
    // 9. 读取主输出流中的结果
    String output = reader.readLine();
    
    // 10. 根据脚本的执行结果更新模型 (使用您原始代码的逻辑)
    if (errorOutput.length() > 0) {
        // 如果Python脚本打印了任何错误信息，则在控制台显示
        traceln("ERROR received from Python script:\n" + errorOutput.toString());
    } else if (output != null && !output.isEmpty()) {
        // 如果没有错误，并且成功接收到输出
        traceln("Result received from FMU: " + output);
        // 将返回的字符串结果转换为 double 类型
        double finalTemperature = Double.parseDouble(output);
        // 更新当前钢包智能体的温度属性
        currentLadle.temperature = finalTemperature;
    } else {
        // 如果既没有错误也没有输出，则打印警告
        traceln("Warning: No output was received from the FMU script.");
    }

} catch (Exception e) {
    // 如果在Java执行过程中发生任何异常，打印堆栈跟踪信息
    e.printStackTrace();
}
```
啊，这是一个非常重要的错误信息！看到这个错误，请您**立刻忘记**我们之前讨论的所有关于 Python 或 `delayEAF` 的事情。

这个错误：
`Unresolved compilation problem: The constructor Main(Engine, null, null) is undefined`

...和您的 `On at exit` 代码的**内部逻辑**完全无关。

这是一个**更高层级的、结构性的 Java 语法错误**。

**诊断结论：**

这个错误是典型的“连锁反应”错误。它的根本原因是，您在 `Main` 智能体的某个代码区域（几乎可以肯定是 `delayEAF` 的 `On at exit` 代码框）中，**引入了一个严重的语法错误，这个错误破坏了整个 `Main` 类的结构**。

最可能的“罪魁祸首”就是我们上一份代码中定义的这个东西：

```java
class StreamGobbler implements Runnable {
    // ...
}
```

在 AnyLogic 的属性代码框中直接定义一个**局部内部类 (Local Inner Class)**，虽然在技术上是合法的 Java 语法，但它非常容易因为一个括号的错位或粘贴错误而“破坏”整个 `Main` 类的编译。

当 Java 编译器因为这个内部类的语法错误而感到困惑时，它就无法正确地解析 `Main` 类的其余部分，包括 AnyLogic 为您自动生成的、至关重要的**构造函数 (Constructor)**。因此，当 AnyLogic 尝试启动仿真并创建 `Main` 实例时，它抱怨说：“我找不到你这个 `Main` 类的构造函数！”——尽管真正的错误是在别处。

---

### **解决方案：更干净、更稳定的方法**

我们将采用一种更健壮、更不容易出错的方法。我们不再将 `StreamGobbler` 类定义在 `On at exit` 代码里，而是将它定义为 `Main` 智能体的一个**正式的内部类**。

请严格按照以下两个步骤操作，这会彻底解决这个编译问题。

#### **第一步：在 Main 中定义 StreamGobbler 内部类**

1.  在 AnyLogic 的“项目”视图中，点击选中您的 `Main` 智能体。
2.  打开“属性”面板，并滚动到最下方，找到 **“高级 (Advanced)”** 部分，展开它。
3.  在 **“导入 (Imports)”** 下方，您会看到一个名为 **“附加类代码 (Additional class code)”** 的大文本框。
4.  将下面这个 `StreamGobbler` 类的完整定义，**复制并粘贴**到这个“附加类代码”文本框中。

```java
// This StreamGobbler class is now a proper inner class of Main.
// It helps to read output from the external Python process asynchronously to prevent deadlocks.
class StreamGobbler implements Runnable {
    private java.io.InputStream inputStream;
    private java.util.function.Consumer<String> consumer;

    public StreamGobbler(java.io.InputStream inputStream, java.util.function.Consumer<String> consumer) {
        this.inputStream = inputStream;
        this.consumer = consumer;
    }

    @Override
    public void run() {
        try (java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.InputStreamReader(inputStream))) {
            reader.lines().forEach(consumer);
        } catch (java.io.IOException e) {
            // Handle exceptions if necessary, e.g., log them.
            e.printStackTrace();
        }
    }
}
```

 *(这是一个示例截图，告诉您大概在什么位置)*

#### **第二步：使用简化的代码更新 `delayEAF` 的 `On at exit`**

现在 `StreamGobbler` 类已经是 `Main` 的一部分了，我们在 `On at exit` 中就不需要再定义它，只需要**使用**它即可。

1.  回到 `delayEAF` 模块的“属性”面板。
2.  **清空** `On at exit` 代码框中的所有内容。
3.  将下面这份**新的、更简洁的**代码复制并粘贴进去。

```java
// --- On at exit action for delayEAF block (DEADLOCK-PROOF - CLEAN VERSION) ---

// 1. 获取当前钢包智能体
Ladle currentLadle = (Ladle) agent;

// 2. 定义路径和构建命令
String pythonPath = "D:/anaconda/python.exe";
String scriptPath = "D:/钢铁电力负荷预测/python/run_eaf_fmu.py";
String command = "\"" + pythonPath + "\" \"" + scriptPath + "\" " + 
                 (currentLadle.mass * 1000) + " " + 
                 p_targetTemp_C + " " +
                 currentLadle.temperature;

traceln("Executing command for Ladle: " + command);

try {
    Process process = Runtime.getRuntime().exec(command);

    // 3. (关键) 使用我们在 Main 中定义的 StreamGobbler 类
    StringBuilder output = new StringBuilder();
    StringBuilder errorOutput = new StringBuilder();

    Thread outputThread = new Thread(new StreamGobbler(process.getInputStream(), s -> output.append(s).append("\n")));
    Thread errorThread = new Thread(new StreamGobbler(process.getErrorStream(), s -> errorOutput.append(s).append("\n")));
    
    outputThread.start();
    errorThread.start();

    // 4. 等待进程安全结束
    int exitCode = process.waitFor();
    outputThread.join(); 
    errorThread.join();

    // 5. 根据结果更新模型
    if (exitCode == 0) { // 进程正常退出
        if (errorOutput.length() > 0) {
            traceln("DEBUG info from Python script:\n" + errorOutput.toString());
        }
        String resultOutput = output.toString().trim();
        if (!resultOutput.isEmpty()) {
            String[] lines = resultOutput.split("\n");
            String lastLine = lines[lines.length - 1];
            traceln("Result received from FMU: " + lastLine);
            double finalTemperature = Double.parseDouble(lastLine);
            currentLadle.temperature = finalTemperature;
        } else {
            traceln("Warning: Python script finished but produced no standard output.");
        }
    } else { // 进程异常退出
        traceln("ERROR: Python script exited with a non-zero code: " + exitCode);
        if (errorOutput.length() > 0) {
            traceln("ERROR details from Python script:\n" + errorOutput.toString());
        }
    }

} catch (Exception e) {
    e.printStackTrace();
}
```

**总结一下我们做了什么：**
1.  我们将 `StreamGobbler` 的**定义**从 `delayEAF` 的代码中“搬家”到了 `Main` 的“附加类代码”区域，让它成为了一个结构更清晰的内部类。
2.  我们**简化**了 `delayEAF` 中的代码，让它只负责**使用** `StreamGobbler`，不再负责定义。

这个方法将彻底解决您遇到的编译错误，并且代码结构也更加清晰和健壮。请完成这两个步骤，您的模型就可以成功编译并运行了。





// 1. 获取当前钢包智能体
Ladle currentLadle = (Ladle) agent;

// 2. 定义路径和构建命令
String pythonPath = "D:/anaconda/python.exe";
String scriptPath = "D:/钢铁电力负荷预测/python/run_eaf_fmu.py";
String command = "\"" + pythonPath + "\" \"" + scriptPath + "\" " + 
                 (currentLadle.mass * 1000) + " " + 
                 targetTemp_EAF_C + " " +
                 currentLadle.temperature;

traceln("Executing command for Ladle: " + command);

try {
    Process process = Runtime.getRuntime().exec(command);

    // 3. (关键) 使用我们在 Main 中定义的 StreamGobbler 类
    StringBuilder output = new StringBuilder();
    StringBuilder errorOutput = new StringBuilder();

    Thread outputThread = new Thread(new StreamGobbler(process.getInputStream(), s -> output.append(s).append("\n")));
    Thread errorThread = new Thread(new StreamGobbler(process.getErrorStream(), s -> errorOutput.append(s).append("\n")));
    
    outputThread.start();
    errorThread.start();

    // 4. 等待进程安全结束
    int exitCode = process.waitFor();
    outputThread.join(); 
    errorThread.join();

    // 5. 根据结果更新模型
    if (exitCode == 0) { // 进程正常退出
        if (errorOutput.length() > 0) {
            traceln("DEBUG info from Python script:\n" + errorOutput.toString());
        }
        String resultOutput = output.toString().trim();
        if (!resultOutput.isEmpty()) {
            String[] lines = resultOutput.split("\n");
            String lastLine = lines[lines.length - 1];
            traceln("Result received from FMU: " + lastLine);
            double finalTemperature = Double.parseDouble(lastLine);
            currentLadle.temperature = finalTemperature;
        } else {
            traceln("Warning: Python script finished but produced no standard output.");
        }
    } else { // 进程异常退出
        traceln("ERROR: Python script exited with a non-zero code: " + exitCode);
        if (errorOutput.length() > 0) {
            traceln("ERROR details from Python script:\n" + errorOutput.toString());
        }
    }

} catch (Exception e) {
    e.printStackTrace();
}