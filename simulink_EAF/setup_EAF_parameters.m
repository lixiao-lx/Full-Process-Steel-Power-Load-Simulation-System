clear; clc;

%% 1. 全局结构体初始化
EAF = struct();

%% 2. 固定参数  - 物理常数与设备几何
% -----------------------------------------------------------
% 电气系统参数
EAF.Fixed.R_sys = 0.3e-3;      % [Ohm] 短网等效电阻
EAF.Fixed.X_sys = 3.0e-3;      % [Ohm] 短网等效电抗
% 变压器特性 
EAF.Fixed.Tap_Lookup_V = [400, 500, 600, 700, 800]; % [V] 次级空载线电压表

% 几何尺寸
EAF.Fixed.R_fur = 3.0;         % [m] 炉膛半径
EAF.Fixed.R_ele = 0.3;         % [m] 电极半径
EAF.Fixed.A_furnace = pi * EAF.Fixed.R_fur^2; % [m^2] 炉膛截面积

% 物料物理属性
EAF.Fixed.rho_solid = 1200;    % [kg/m^3] 废钢堆积密度
EAF.Fixed.rho_liq = 7000;    % [kg/m^3] 钢水密度
EAF.Fixed.Cp_solid = 600;     % [J/(kg*K)] 固态钢比热容
EAF.Fixed.Cp_liq = 800;     % [J/(kg*K)] 液态钢比热容
EAF.Fixed.T_f = 1538 + 273.15; % [K] 钢熔点 (1538 C)
EAF.Fixed.dH_fusion = 270000;  % [J/kg] 熔化潜热

% 渣系物性 (用于泡沫指数 Sigma 计算)
EAF.Fixed.mu_slag = 0.5;    % [Pa*s] 炉渣粘度
EAF.Fixed.sigma_slag = 1.2;    % [N/m] 表面张力
EAF.Fixed.rho_slag = 3000;   % [kg/m^3] 炉渣密度
EAF.Fixed.D_B = 0.01;   % [m] 气泡平均直径

% 化学反应热焓 (示例值)
EAF.Fixed.dH_C_O = 9.0e6;  % [J/kg_C] C+O->CO 反应热
EAF.Fixed.dH_Fe_O = 4.5e6;  % [J/kg_Fe] Fe+O->FeO 反应热

% 环境与烟气
EAF.Fixed.Cp_gas = 1400;   % [J/(kg*K)] 烟气比热
EAF.Fixed.T_amb = 25 + 273.15; % [K] 环境温度

% 设定出钢温度
EAF.Fixed.T_out_steel = 1650 + 273.15; % [K] 出钢温度设定

%% 3. 控制输入  - 初始设定
% -----------------------------------------------------------
% --- Stage 1: Boredown (穿井期) ---
EAF.Control.Stage1.k_tap = 3;       % [-] 变压器档位 (中压)
EAF.Control.Stage1.Z_set = 3.5;     % [mOhm] 设定阻抗 (高阻/长弧)
EAF.Control.Stage1.O2 = 0.0;     % [kg/s] 氧气流量
EAF.Control.Stage1.C = 0.0;     % [kg/s] 碳粉流量

% --- Stage 2: Melting (主熔化期) ---
EAF.Control.Stage2.k_tap = 5;       % [-] 变压器档位 (最高压)
EAF.Control.Stage2.Z_set = 3.0;     % [mOhm] 设定阻抗 (低阻/短弧)
EAF.Control.Stage2.O2 = 0.2;     % [kg/s] 助熔氧气
EAF.Control.Stage2.C = 0;     % [kg/s] 少量碳粉

% --- Stage 3: Foaming (泡沫渣期) ---
EAF.Control.Stage3.k_tap = 5;       % [-] 变压器档位 (保持高压)
EAF.Control.Stage3.Z_set = 3.5;     % [mOhm] 设定阻抗 (适当拉长，配合泡沫)
EAF.Control.Stage3.O2 = 1.0;     % [kg/s] 高氧流量 (造渣)
EAF.Control.Stage3.C = 0.8;     % [kg/s] 高碳流量 (造渣)

% --- Stage 4: Refining (精炼期) ---
EAF.Control.Stage4.k_tap = 2;       % [-] 变压器档位 (低压)
EAF.Control.Stage4.Z_set = 1.5;     % [mOhm] 设定阻抗 (短弧稳弧)
EAF.Control.Stage4.O2 = 0.0;     % [kg/s] 关闭氧枪
EAF.Control.Stage4.C = 0.0;     % [kg/s] 关闭碳枪

%% 4. 拟合参数  - 模型拟合系数
% -----------------------------------------------------------
% 电弧长度模型系数 (Hernández 模型)
EAF.Tunable.m_V = 0.037;       % [cm/V] 电压对弧长的线性系数
EAF.Tunable.m_Z = 2.112;       % [cm/mOhm] 阻抗对弧长的线性系数

% 电弧电压波形系数 (Bowman 模型)
EAF.Tunable.V_an_cat = 38.7;   % [V] 阴极+阳极压降
EAF.Tunable.E_field = 14.9;   % [V/cm] 电弧电场梯度

% 几何演变系数
EAF.Tunable.k_geo = 1;       % [-] 内径扩张修正系数
EAF.Tunable.k_bottom = 0.1;    % [-] 炉底吸收辐射的分配系数

% 热力学与传热系数

EAF.Tunable.k_sm =1500;       % [W/(m*K)] 固体金属导热系数
EAF.Tunable.k_melt = 2;      % [-] 熔化速率修正因子

% 化学能系数
EAF.Tunable.eta_pc = 0.4;      % [-] 后燃烧效率 (CO -> CO2)
EAF.Tunable.xi_noise_var = 0.1;% [cm] 随机扰动方差 


%% 5. 初始状态变量  - t=0 时刻
% -----------------------------------------------------------
% 物料质量
EAF.State.m_solid_0 = 100000;  % [kg] 初始废钢装料量 
EAF.State.m_solid = EAF.State.m_solid_0; 
EAF.State.m_liq = 5000;       % [kg] 初始熔池量

% 温度
EAF.State.T_solid = 25 + 273.15; % [K] 废钢初始温度
EAF.State.T_liq = 1550 + 273.15; % [K] 熔池初始温度 

% 几何与电弧
EAF.State.H_scrap = EAF.State.m_solid / (EAF.Fixed.rho_solid * ...
                      (pi*(EAF.Fixed.R_fur^2 - EAF.Fixed.R_ele^2))); % [m] 初始废钢高度
EAF.State.R_eff = EAF.Fixed.R_ele; % [m] 初始内孔半径
EAF.State.H_slag = 0;       % [m] 初始泡沫渣高度
EAF.State.L_arc = 0;       % [cm] 初始电弧长度 



%% 6. 显示信息
disp('EAF 机理模型参数已加载。');