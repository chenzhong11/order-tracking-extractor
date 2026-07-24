# 更新记录

## v7.23 (2026-07-24) — 特征扩展 + 统计阈值 + 诊断报告

### 特征扩展

- **新增 `fault_band_domain`**：`extract_multi_axis_features()` 输出新增故障特定频带特征
  - 按 8 种故障类型（松靴/配流盘/柱塞/斜盘/轴承内外圈/气穴/均匀磨损）提取敏感频带能量
  - 冲击类：高频共振带包络 RMS + 包络谱特征频率幅值
  - 磨损类：低频带 FFT 能量 + 重点阶次幅值

### 统计阈值

- **新增 `calibrate_from_signal()`**：从单段正常信号中滑动窗口切分伪样本，计算 3σ/P95 统计阈值
- **新增 `diagnose_by_fault_pattern_statistical()`**：用统计阈值遍历所有故障类型
- **新增 `compare_threshold_modes()`**：对比固定比值 / 3σ / P95 三种阈值模式

### 诊断报告

- **新增 `diagnostic_report.py`**：诊断报告可视化模块
  - 非均匀横轴（低频精细展开 70%，高频压缩 30%）
  - 正常/故障叠加对比（共享坐标系）
  - 峰值数值标注（每个关键倍频标注具体幅值）
  - 故障概率排序 + 诊断依据面板
  - 支持 `y_mode="amplitude"/"energy"` 切换

### 文献引用

- 故障-信号映射表新增 12 篇硕博论文/期刊文献引用
- 覆盖松靴[R1][R10]、配流盘/柱塞[R2][R9]、轴承[R3][R7][R8][R12]、气穴[R5][R6]、斜盘[R4][R11]

### 清理

- 删除未使用函数：`compute_envelope_spectrum`, `tachometer_to_speed`, `vk_order_analysis`, `save_features`, `load_features`, `diagnose_and_report`, `compute_feature_changes`, `match_fault_pattern`, `diagnose_by_sensitivity`, `_is_meta_key`, `_resolve_max_axis_feature`
- 修复 `_flatten_features` 重复定义
- 修复 `FaultBandConfig` 缺少 `@dataclass` 装饰器
- 修复 `_MIN_FFT_LENGTH` 常量丢失
- 删除无用的 `json`/`Path` 导入

### 文档

- 新增 `docs/算法技术报告.md`：按验证阶段组织（白盒测试→算法验证→阈值对比→综合诊断）
- 新增 `docs/出图经验手册.md`：matplotlib 中文出图经验
- 更新 `docs/故障-信号映射表.md`：新增文献引用
- 更新 `docs/诊断结果解读指南.md`：新增统计阈值和诊断报告说明
- 更新 `README.md`：同步功能和目录结构

## v7.22 (2026-07-23) — 代码修复与验证

### Bug 修复

- **NaN bug**：0-100Hz 频带滤波器数值不稳定，全部改用 SOS 格式（`sosfiltfilt`）
- **单轴兼容**：`diagnose_by_fault_pattern` 原要求三轴数据，现在 `axes.Z./axes.Y.` 自动回退到存在的轴
- **负值峭度比值**：峭度为负值时直接比值无物理意义，改用变化比例计算（`_compute_ratio`）

### 验证

- **合成信号正确性验证**（`examples/validate_signals.py`）：16/16 通过
  - 转频/柱塞通过频率误差 <0.03Hz
  - 冲击间隔误差 <0.02ms
  - 配流盘谐波放大 3.00x、柱塞谐波放大 2.50x 精确匹配设计值
  - 高频/低频能量分布符合物理预期
- **算法有效性验证**（`examples/validate_algorithm.py`）：49/49 通过
  - 频带能量诊断：松靴/配流盘/柱塞全部检出，正常信号零误报
  - 物理机理诊断：配流盘/柱塞检出，松靴峭度比值 1.91x 接近阈值
  - 加噪鲁棒性：SNR=4.4 时仍能检出
  - 输出字段完整性：全部字段存在

### 文档

- 新增 `docs/合成信号正确性验证报告.md`
- 更新 `docs/算法有效性验证报告.md`：补充自动化验证结果
- 真实数据验证：下载三轴振动数据（test/data/real/），三轴联合诊断全部检出

### 数据

- 新增 `test/data/real/normal/`：正常三轴数据（8MPa_N-X/Y/Z.txt）
- 新增 `test/data/real/fault/`：故障三轴数据（8MPA-X/Y/Z.txt）
- 来源：https://github.com/chenzhong11/-cot/tree/main/数据准备包

## v7.22 (2026-07-23) — 清理与文档更新

### 清理冗余

- 删除 `version.py`（与 `core.py` 重复）
- 删除 v1 合成信号生成器和 v1 测试数据（保留更真实的 v2）
- 重命名 v2 文件：生成器去掉 `_v2` 后缀，测试数据去掉 `_v2` 后缀
- 删除 `egg-info` 和 `__pycache__` 构建产物
- 修复 examples 中的测试数据路径（`examples/synthetic_data/` → `test/data/`）

### 文档

- 新增 `docs/诊断结果解读指南.md`：对应 `diagnose_by_fault_pattern()` 输出的逐字段解读
  - 四种柱塞泵故障的特征路径、物理含义、阈值、ratio 解读
  - 置信度计算方法和经验判断
  - 多故障同时触发的综合判定逻辑
  - 特征路径速查表（时域/频域/阶次域/冲击域/轴间关系）
  - 常见误判场景和趋势分析建议
- 更新 `README.md`：同步目录结构、功能说明、故障诊断用法

## v7.22 (2026-07-22) — 算法发布

### 新增模块

- **feature_extractor.py**：多维度特征提取器
  - 时域统计特征（11个）：RMS、峰值、峭度、波峰因子等
  - 频域特征（9个频带 + 3个统计量）：按采样率等分，设备驱动
  - 阶次域特征（15+15+4个）：COT/TOT 各阶次幅值 + 重点阶次
  - 冲击域特征（4+5个）：多频段包络谱 + 角域冲击特征
  - 轴间关系（9个）：三轴 RMS 比、峭度差、峰值比
  - 设备驱动，全量输出，不预设故障场景

- **sensitivity_diagnostics.py**：基于特征变化率的数据驱动诊断
  - 正常数据 vs 故障数据全量特征对比
  - 自动排序敏感指标（变化最大的特征排前面）
  - 与已知故障模式匹配（基于物理机理的签名特征）
  - 支持任意轴数，不绑定具体轴号

- **fault_diagnostics.py**：基于故障物理机理的分类诊断
  - 松靴：聚焦峭度和冲击特征
  - 配流盘磨损：聚焦低频能量和阶次幅值
  - 柱塞磨损：聚焦柱塞频率谐波
  - 斜盘磨损：聚焦转频谐波

### 算法改进

- **故障频带重构**：按故障类型分组定义目标频带，取代逐阶次平铺
  - 冲击类（松靴）：低频 150~550Hz + 高频共振 6~7.5kHz
  - 周期力类（配流盘/柱塞）：转频谐波带 + 柱塞频率带
  - 均匀磨损：全频带 RMS

- **COT vs TOT 路径分析**：
  - TOT 对周期力类故障更精确（比值稳定）
  - COT 对冲击类故障更敏感（保留非同步特征）
  - STFT 窗长 1024 是松靴检测的"甜蜜点"

- **包络谱分析**：多频段共振解调（1~2kHz, 2~4kHz, 4~6kHz, 6~7.5kHz）

### 验证

- 合成信号验证：v1（理想）+ v2（模拟真实工况，转速波动±0.5%，冲击抖动±5%）
- 真实数据验证：三轴松靴数据（来自 GitHub 公开数据集）
- 三轴综合分析：X 轴 RMS 3.82x，Z 轴峭度 21.71，角域峭度 9.86x

### 文档

- 频带覆盖与采样率约束说明
- COT vs TOT 与 STFT 参数分析
- 柱塞泵故障类型与目标频带调研报告
- 特征提取架构说明
- 算法有效性验证报告
- 真实数据验证报告

## v1.0.0 (2026-06-29)

- 初始封装版本
- 合并多个模块为单个 order_tracking_core.py
- 新增 OrderTrackingConfig 配置类
- 新增 OrderTrackingAnalyzer 高级封装类
- 新增异常体系：OrderTrackingError、ConfigError、SignalInputError、ComputationError
- 输出结果增加版本信息
