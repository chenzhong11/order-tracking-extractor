# 阶次分析特征提取封装包 v7.23

> 柱塞泵振动信号的阶次分析、特征提取与故障诊断

---

## 当前版本

| 项目 | 值 |
|------|-----|
| 包版本 | 7.23 |
| 算法编号 | order_tracking_v2 |
| 算法版本 | A-7.23 |
| 特征字段版本 | 2026.07 |

## 安装

```bash
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 功能模块

| 功能 | 说明 |
|------|------|
| 阶次分析 | COT / TOT 两种方法 |
| 特征提取 | 时域 / 频域 / 阶次域 / 冲击域 / 故障频带域 / 轴间关系 |
| 物理机理诊断 | 7 种故障类型（松靴/配流盘/柱塞/斜盘/轴承内外圈/气穴） |
| 统计阈值校准 | 3σ / P95，基于滑动窗口伪样本 |
| 诊断报告 | 一键生成综合报告图（非均匀横轴 + 峰值标注 + 诊断依据） |

## 快速使用

### 1. 特征提取

```python
from order_tracking_extractor import extract_multi_axis_features

signals = {
    "X": np.loadtxt("vibration_x.txt"),
    "Y": np.loadtxt("vibration_y.txt"),
    "Z": np.loadtxt("vibration_z.txt"),
}

features = extract_multi_axis_features(signals, sampling_rate=20000.0)
# 输出: axes.{X,Y,Z}.{time_domain, freq_domain, order_domain, impulse_domain, fault_band_domain}
#       cross_axis.{rms_ratio, kurtosis_diff, ...}
```

### 2. 故障诊断（机理法）

```python
from order_tracking_extractor import diagnose_by_fault_pattern

result = diagnose_by_fault_pattern(fault_features, normal_features)
print(result["conclusion"])        # 一句话结论
print(result["detected_faults"])   # 触发的故障类型
# 详细结果在 result["all_results"]，每个故障含 primary_features / secondary_features
```

### 3. 统计阈值诊断

```python
from order_tracking_extractor import calibrate_from_signal, compare_threshold_modes

# 从正常信号计算统计阈值（滑动窗口切分伪样本）
thresh_config = calibrate_from_signal(normal_signal, sampling_rate=20000.0)

# 三种模式对比
result = compare_threshold_modes(normal_signal, fault_features, normal_features, 20000.0)
# result["fixed"]  — 固定比值阈值（原有方法）
# result["3sigma"] — 3σ 统计阈值
# result["p95"]    — P95 统计阈值
```

### 4. 诊断报告

```python
from order_tracking_extractor import generate_report_from_signals

normal_signals = {"X": nx, "Y": ny, "Z": nz}
fault_signals = {"X": fx, "Y": fy, "Z": fz}

path, summary = generate_report_from_signals(
    normal_signals, fault_signals,
    sampling_rate=20000.0, rotational_freq=24.67, n_pistons=7,
    output_path="diagnostic_report.png",
)
```

## 故障类型

| 故障 | 类别 | 核心特征 | 检测方法 |
|------|------|----------|----------|
| 松靴/滑靴脱落 | 冲击 | Z轴峭度 + 角域峭度 | 高频共振带包络 |
| 配流盘磨损 | 低频周期 | 低频带能量 + 7阶次幅值 | 阶次幅值比 |
| 柱塞-缸孔磨损 | 低频周期 | 7阶次 + 14阶次幅值 | 阶次幅值比 |
| 斜盘磨损 | 低频周期 | 转频谐波 | 阶次幅值比 |
| 轴承外圈故障 | 冲击 | 峭度 + 高频包络 RMS | 包络谱信噪比 |
| 轴承内圈故障 | 冲击 | 峭度 + 高频包络 RMS | 包络谱信噪比 |
| 气穴溃灭 | 冲击(随机) | 高频底噪 + 谱熵 | 宽频底噪抬升 |

## 设备参数（默认）

| 参数 | 值 |
|------|-----|
| 柱塞数 | 7 |
| 转速 | 1480 RPM |
| 转频 $f_r$ | 24.67 Hz |
| 柱塞通过频率 $f_p$ | 172.67 Hz ($7 \times f_r$) |
| 采样率 | 20 kHz |

## 目录结构

```
order-tracking-extractor/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── order_tracking_extractor/
│   ├── __init__.py
│   ├── core.py                  # 全部算法
│   └── diagnostic_report.py     # 诊断报告可视化
├── examples/
│   ├── generate_fault_signals.py
│   ├── validate_algorithm.py       # 算法验证（49项）
│   ├── test_all_faults.py          # 多故障验证
│   ├── test_cot_vs_tot.py          # COT vs TOT 对比
│   ├── test_full_validation.py     # 全面验证
│   └── generate_report_figures.py  # 技术报告配图
├── test/data/
│   ├── normal/                 # 正常三轴数据
│   └── fault/                  # 故障三轴数据
└── docs/
    ├── 算法技术报告.md          # 验证报告（4张图+分析）
    ├── 故障-信号映射表.md       # 12种故障的机理+特征+文献
    ├── 诊断结果解读指南.md      # 诊断报告怎么读
    ├── 出图经验手册.md          # matplotlib 中文出图经验
    └── images/                  # 验证图片（4张）
```

## 异常处理

```python
from order_tracking_extractor import (
    OrderTrackingError, ConfigError, SignalInputError, ComputationError,
)

try:
    result = analyzer.analyze_cot(signal)
except ConfigError as e:
    print("配置错误:", e)
except SignalInputError as e:
    print("输入信号错误:", e)
```
