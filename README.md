# 阶次分析特征提取封装包 v7.22

> 柱塞泵振动信号的阶次分析、特征提取与故障诊断

---

## 当前版本

| 项目 | 值 |
|------|-----|
| 包版本 | 7.22 |
| 算法编号 | order_tracking_v2 |
| 算法版本 | A-7.22 |
| 特征字段版本 | 2026.07 |

## 安装

```bash
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 功能模块（单文件集成）

所有算法在 `order_tracking_extractor/core.py` 中，通过 `__init__.py` 统一导出。

| 功能 | 说明 |
|------|------|
| 阶次分析 | COT / TOT / VK 三种方法 |
| 特征提取 | 时域 / 频域 / 阶次域 / 冲击域 / 轴间关系 |
| 阈值标定 | 3σ / 百分位数 / 滑动窗口 |
| 数据驱动诊断 | 基于特征变化率的敏感特征匹配 |
| 物理机理诊断 | 基于故障物理的分类诊断（松靴/配流盘/柱塞/斜盘） |
| 频带诊断 | 按故障类型的目标频带能量分析 |

## 快速使用

### 1. 阶次分析

```python
from order_tracking_extractor import OrderTrackingConfig, OrderTrackingAnalyzer
import numpy as np

signal = np.loadtxt("vibration_data.txt")

config = OrderTrackingConfig(sampling_rate=20000.0, max_order=15, method="cot")
analyzer = OrderTrackingAnalyzer(config)
result = analyzer.analyze_cot(signal)

print(result["order_amplitudes"])
print(result["order_energies"])
```

### 2. 特征提取

```python
from order_tracking_extractor import extract_multi_axis_features, save_features

signals = {
    "X": np.loadtxt("vibration_x.txt"),
    "Y": np.loadtxt("vibration_y.txt"),
    "Z": np.loadtxt("vibration_z.txt"),
}

features = extract_multi_axis_features(signals, sampling_rate=20000.0)
save_features(features, "features.json")
```

### 3. 故障诊断（物理机理）

```python
from order_tracking_extractor import load_features, diagnose_by_fault_pattern

normal_feat = load_features("features_normal.json")
fault_feat = load_features("features_fault.json")

result = diagnose_by_fault_pattern(fault_feat, normal_feat)
print(result["conclusion"])        # 一句话结论
print(result["detected_faults"])   # 触发的故障类型
# 详细结果在 result["all_results"] 中，每个故障含 primary_features / secondary_features
```

### 4. 阈值标定与诊断

```python
from order_tracking_extractor import OrderTrackingAnalyzer

config = OrderTrackingConfig(sampling_rate=20000.0, method="cot")
analyzer = OrderTrackingAnalyzer(config)

# 标定
cal_result = analyzer.calibrate_thresholds(healthy_signal)

# 诊断
diag = analyzer.diagnose(test_signal, cal_result)
print(diag["is_fault_3sigma"])
```

## 设备参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 柱塞数 | 7 | 轴向柱塞泵柱塞数 |
| 转速 | 1480 RPM | 额定转速 |
| 采样率 | 20000 Hz | 振动信号采样率 |
| 采样时长 | 10 s | 单次采集时长 |

## 输出字段

### 阶次分析结果

| 字段 | 说明 |
|------|------|
| `method` | 分析方法（COT/TOT） |
| `orders` | 阶次轴 [1, 2, ..., max_order] |
| `order_amplitudes` | 各阶次幅值 |
| `order_energies` | 各阶次能量 |
| `rotational_freq` | 平均转频 Hz |

### 特征字典

| 维度 | 特征数 | 内容 |
|------|--------|------|
| 时域 | 11 | RMS、峰值、峭度、波峰因子等 |
| 频域 | 9+3 | 频带能量、频谱质心、频谱熵 |
| 阶次域 | 15+15+4 | 各阶次幅值、重点阶次(f_p, 2f_p) |
| 冲击域 | 4+5 | 包络谱、角域峭度/波峰因子 |
| 轴间关系 | 9 | 三轴 RMS 比、峭度差、峰值比 |

### 故障诊断输出

| 字段 | 说明 |
|------|------|
| `conclusion` | 一句话结论 |
| `detected_faults` | 触发的故障类型列表 |
| `is_fault` | 是否触发该故障 |
| `confidence` | 置信度（0~2） |
| `primary_features` | 主判定特征（含 ratio/threshold/triggered） |
| `mechanism` | 物理机理描述 |

## 目录结构

```
order-tracking-extractor/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── order_tracking_extractor/
│   ├── __init__.py              # 统一导出
│   └── core.py                  # 全部算法（单文件集成）
├── examples/
│   ├── generate_fault_signals.py   # 合成信号生成器
│   ├── validate_signals.py         # 合成信号正确性验证（16项）
│   ├── validate_algorithm.py       # 算法有效性验证（49项）
│   ├── test_all_faults.py          # 多故障验证
│   ├── test_cot_vs_tot.py          # COT vs TOT 对比
│   └── test_full_validation.py     # 全面验证
├── test/
│   └── data/
│       ├── normal/                 # 正常信号
│       └── fault/                  # 故障信号（松靴/配流盘/柱塞）
└── docs/
    ├── 项目上手指南.html        # 学习路径（10阶段+4能力）
    ├── 算法技术报告.html        # 设备/架构/验证/五维自检/适用边界
    ├── 诊断结果解读指南.html    # 诊断报告怎么读（面向诊断工程师）
    ├── 诊断结果解读指南.md      # 同上的文本版
    ├── kami-v2.md               # Kami 排版规范
    └── images/                  # 验证图片（6张）
```

## 异常处理

```python
from order_tracking_extractor import (
    OrderTrackingError,
    ConfigError,
    SignalInputError,
    ComputationError,
)

try:
    result = analyzer.analyze_cot(signal)
except ConfigError as e:
    print("配置错误:", e)
except SignalInputError as e:
    print("输入信号错误:", e)
except ComputationError as e:
    print("计算过程错误:", e)
except OrderTrackingError as e:
    print("封装包错误:", e)
```
