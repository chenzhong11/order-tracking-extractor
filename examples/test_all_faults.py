"""全面验证：三种低频故障 + 松靴（共振解调补充）。

验证目标：
- 配流盘磨损、柱塞磨损：低频故障，在 20kHz 采样率下完全覆盖 → 主力验证
- 松靴：冲击类高频故障，用共振解调作为补充手段 → 附带验证

函数版本: F-1.0.0
创建人: AI
编辑日期: 2026-07-22
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from order_tracking_extractor import (
    FAULT_BAND_PRESETS,
    extract_fault_band_energy,
    diagnose_by_fault_type,
)


def load_signal(filepath: str) -> np.ndarray:
    return np.loadtxt(filepath).reshape(-1)


TEST_DATA_DIR = Path(__file__).resolve().parents[1] / "test" / "data"


def print_separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_fault(name, signal, fault_key, baseline, fs, f_rot, **kwargs):
    """测试单个故障的检出情况。"""
    config = FAULT_BAND_PRESETS[fault_key]
    result = extract_fault_band_energy(signal, fs, config, rotational_freq=f_rot)
    diag = diagnose_by_fault_type(
        signal, fs, config,
        baseline_result=baseline,
        rotational_freq=f_rot,
        **kwargs,
    )

    print(f"\n  [{name}] 故障类型: {config.name}")
    print(f"    检测方法: {config.detection_method}")
    print(f"    判定故障: {diag['is_fault']}")
    print(f"    置信度: {diag['confidence']:.2f}")

    # 打印关键指标
    if diag['details'].get('high_band_ratios'):
        for k, v in diag['details']['high_band_ratios'].items():
            print(f"    {k} 能量比: {v:.2f}x")
    if diag['details'].get('order_ratios'):
        for k, v in diag['details']['order_ratios'].items():
            print(f"    阶次 {k} 幅值比: {v:.2f}x")
    if diag['details'].get('max_ratio'):
        print(f"    最大比值: {diag['details']['max_ratio']:.2f}x")

    return diag


def main() -> None:
    fs = 20000.0
    f_rot = 1480.0 / 60.0

    # 加载信号
    normal = load_signal(TEST_DATA_DIR / "normal" / "normal.txt")
    valve_wear = load_signal(TEST_DATA_DIR / "fault" / "valve_plate_wear.txt")
    piston_wear = load_signal(TEST_DATA_DIR / "fault" / "piston_wear.txt")
    loose_slipper = load_signal(TEST_DATA_DIR / "fault" / "loose_slipper.txt")

    # ============================================================
    # 基线标定
    # ============================================================
    print_separator("Step 1: 健康基线标定")

    baseline_valve = extract_fault_band_energy(
        normal, fs, FAULT_BAND_PRESETS["valve_plate_wear"], rotational_freq=f_rot)
    baseline_piston = extract_fault_band_energy(
        normal, fs, FAULT_BAND_PRESETS["piston_wear"], rotational_freq=f_rot)
    baseline_slipper = extract_fault_band_energy(
        normal, fs, FAULT_BAND_PRESETS["loose_slipper"], rotational_freq=f_rot)

    print(f"  配流盘配置基线 - 阶次幅值: { {k: round(v, 4) for k, v in baseline_valve['order_amplitudes_of_interest'].items()} }")
    print(f"  柱塞配置基线 - 阶次幅值: { {k: round(v, 4) for k, v in baseline_piston['order_amplitudes_of_interest'].items()} }")
    print(f"  松靴配置基线 - 高频带: {baseline_slipper['high_band_energies']}")

    # ============================================================
    # 主力验证：低频故障（20kHz 采样率完全覆盖）
    # ============================================================
    print_separator("Step 2: 主力验证 — 低频故障")

    print("\n--- 配流盘磨损 ---")
    diag_valve = test_fault(
        "配流盘磨损", valve_wear, "valve_plate_wear",
        baseline_valve, fs, f_rot, order_amplitude_threshold=2.0)

    print("\n--- 柱塞磨损 ---")
    diag_piston = test_fault(
        "柱塞磨损", piston_wear, "piston_wear",
        baseline_piston, fs, f_rot, order_amplitude_threshold=2.0)

    # ============================================================
    # 补充验证：松靴（共振解调）
    # ============================================================
    print_separator("Step 3: 补充验证 — 松靴（共振解调）")

    diag_slipper = test_fault(
        "松靴故障", loose_slipper, "loose_slipper",
        baseline_slipper, fs, f_rot, energy_ratio_threshold=2.0)

    # 包络谱中 f_p 处幅值
    env_result = extract_fault_band_energy(loose_slipper, fs, FAULT_BAND_PRESETS["loose_slipper"], rotational_freq=f_rot)
    f_piston = 7 * f_rot
    for band_key, (env_freqs, env_mags) in env_result.get("envelope_spectra", {}).items():
        idx = np.argmin(np.abs(env_freqs - f_piston))
        env_amp_fault = np.max(env_mags[max(0,idx-2):idx+3])
        for band_key2, (env_freqs2, env_mags2) in baseline_slipper.get("envelope_spectra", {}).items():
            idx2 = np.argmin(np.abs(env_freqs2 - f_piston))
            env_amp_base = np.max(env_mags2[max(0,idx2-2):idx2+3])
            ratio = env_amp_fault / env_amp_base if env_amp_base > 0 else float("inf")
            print(f"    包络谱 f_p({f_piston:.1f}Hz) 幅值比: {ratio:.2f}x")

    # ============================================================
    # 交叉验证 & 误报测试
    # ============================================================
    print_separator("Step 4: 交叉验证 & 误报测试")

    # 正常信号不应报警
    for fault_key in ["valve_plate_wear", "piston_wear", "loose_slipper"]:
        config = FAULT_BAND_PRESETS[fault_key]
        baseline = {"valve_plate_wear": baseline_valve, "piston_wear": baseline_piston, "loose_slipper": baseline_slipper}[fault_key]
        threshold = {"valve_plate_wear": 2.0, "piston_wear": 2.0, "loose_slipper": 2.0}[fault_key]
        method = config.detection_method
        kwargs = {"energy_ratio_threshold": threshold} if method == "energy_ratio" else {"order_amplitude_threshold": threshold}
        diag = diagnose_by_fault_type(normal, fs, config, baseline_result=baseline, rotational_freq=f_rot, **kwargs)
        status = "✅" if not diag['is_fault'] else "❌"
        print(f"  {status} 正常信号 × {config.name}: 故障={diag['is_fault']}")

    # ============================================================
    # 总结
    # ============================================================
    print_separator("总结")

    print(f"""
  设备: 7柱塞, 1480 RPM, 采样率 20kHz
  转频 f_r = {f_rot:.2f} Hz, 柱塞频率 f_p = {f_piston:.2f} Hz

  ┌─────────────────────┬──────────┬──────────┬─────────────────────┐
  │ 故障类型            │ 检出     │ 置信度   │ 频率范围            │
  ├─────────────────────┼──────────┼──────────┼─────────────────────┤
  │ 配流盘磨损(低频)    │ {str(diag_valve['is_fault']):<8} │ {diag_valve['confidence']:.2f}     │ 10~700 Hz ✅全覆盖  │
  │ 柱塞磨损(低频)      │ {str(diag_piston['is_fault']):<8} │ {diag_piston['confidence']:.2f}     │ 50~900 Hz ✅全覆盖  │
  │ 松靴(冲击/高频)     │ {str(diag_slipper['is_fault']):<8} │ {diag_slipper['confidence']:.2f}     │ 6~7.5kHz ⚠️部分覆盖│
  └─────────────────────┴──────────┴──────────┴─────────────────────┘

  结论:
  - 低频故障（配流盘、柱塞磨损）在 20kHz 采样率下完全可检测
  - 松靴等冲击类故障受采样率限制，只能用共振解调做补充检测
  - 若需完整覆盖高频共振带，需将采样率提高到 50kHz+
""")


if __name__ == "__main__":
    main()
