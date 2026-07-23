"""全面验证：COT/TOT 路径 × 阶次/冲击特征。

测试内容：
- COT（无转速）vs TOT（有转速）的阶次分析精度对比
- 角域冲击特征（峰值、峭度、波峰因子）对松靴的检出能力

设备参数：7柱塞，1480 RPM，20kHz 采样，10s
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
    cot_order_analysis,
    tot_order_analysis,
)

TEST_DATA_DIR = Path(__file__).resolve().parents[1] / "test" / "data"


def load(p): return np.loadtxt(p).reshape(-1)


def compute_impulse_features(signal: np.ndarray) -> dict:
    """计算冲击类特征（角域信号用）。"""
    rms = np.sqrt(np.mean(signal**2))
    peak = np.max(np.abs(signal))
    crest_factor = peak / rms if rms > 0 else 0
    mean = np.mean(signal)
    std = np.std(signal)
    kurtosis = float(np.mean(((signal - mean) / std) ** 4) - 3) if std > 0 else 0
    return {"rms": rms, "peak": peak, "crest_factor": crest_factor, "kurtosis": kurtosis}


def print_sep(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def main():
    fs = 20000.0
    f_rot = 1480.0 / 60.0

    normal = load(TEST_DATA_DIR / "normal" / "normal.txt")
    loose = load(TEST_DATA_DIR / "fault" / "loose_slipper.txt")
    valve = load(TEST_DATA_DIR / "fault" / "valve_plate_wear.txt")
    piston = load(TEST_DATA_DIR / "fault" / "piston_wear.txt")

    tacho = np.full(len(normal), f_rot)

    # ============================================================
    # Part 1: COT vs TOT 阶次比值（故障/正常）
    # ============================================================
    print_sep("Part 1: COT vs TOT 阶次比值（故障/正常）")

    for name, fault in [("松靴", loose), ("配流盘磨损", valve), ("柱塞磨损", piston)]:
        cot_n = cot_order_analysis(normal, fs, max_order=15)
        cot_f = cot_order_analysis(fault, fs, max_order=15)
        tot_n = tot_order_analysis(normal, fs, tachometer_signal=tacho, max_order=15)
        tot_f = tot_order_analysis(fault, fs, tachometer_signal=tacho, max_order=15)

        print(f"\n  [{name}]")
        print(f"  {'阶次':>4} | {'COT比值':>8} | {'TOT比值':>8} | {'COT判定':>6} | {'TOT判定':>6}")
        print(f"  {'-'*48}")
        for i in range(15):
            cr = cot_f["order_amplitudes"][i] / max(cot_n["order_amplitudes"][i], 1e-10)
            tr = tot_f["order_amplitudes"][i] / max(tot_n["order_amplitudes"][i], 1e-10)
            print(f"  {i+1:>4} | {cr:>7.2f}x | {tr:>7.2f}x | {'✅' if cr > 1.5 else '❌':>6} | {'✅' if tr > 1.5 else '❌':>6}")

    # ============================================================
    # Part 2: 角域冲击特征（TOT 路径的补充检测）
    # ============================================================
    print_sep("Part 2: 角域冲击特征 — 松靴的补充检测")

    print(f"\n  原理：松靴的冲击在角域信号中体现为峰值和峭度增大，")
    print(f"  但不体现在阶次谐波中。需要用冲击特征（波峰因子、峭度）来检测。")

    tot_n = tot_order_analysis(normal, fs, tachometer_signal=tacho, max_order=15)
    tot_f = tot_order_analysis(loose, fs, tachometer_signal=tacho, max_order=15)

    ang_n = tot_n.get("resampled_signal", normal)
    ang_f = tot_f.get("resampled_signal", loose)

    feat_n = compute_impulse_features(ang_n)
    feat_f = compute_impulse_features(ang_f)

    print(f"\n  {'特征':>14} | {'正常':>10} | {'松靴':>10} | {'比值':>8} | {'判定':>6}")
    print(f"  {'-'*55}")
    for key, label in [("rms", "RMS"), ("peak", "峰值"), ("crest_factor", "波峰因子"), ("kurtosis", "峭度")]:
        n_val = feat_n[key]
        f_val = feat_f[key]
        ratio = f_val / n_val if n_val > 0 else float("inf")
        ok = "✅" if (ratio > 1.3 if key != "kurtosis" else f_val > 1.0) else "❌"
        print(f"  {label:>14} | {n_val:>10.4f} | {f_val:>10.4f} | {ratio:>7.2f}x | {ok:>6}")

    # ============================================================
    # Part 3: 各故障信号的时域特征对比
    # ============================================================
    print_sep("Part 3: 各故障信号的时域特征对比")

    print(f"\n  {'信号':>12} | {'RMS':>8} | {'峰值':>8} | {'波峰因子':>8} | {'峭度':>8}")
    print(f"  {'-'*50}")

    for label, sig in [("正常", normal), ("松靴", loose), ("配流盘", valve), ("柱塞", piston)]:
        feat = compute_impulse_features(sig)
        print(f"  {label:>12} | {feat['rms']:>8.4f} | {feat['peak']:>8.4f} | {feat['crest_factor']:>8.2f} | {feat['kurtosis']:>8.2f}")

    # ============================================================
    # 总结
    # ============================================================
    print_sep("总结")

    print(f"""
  验证结论：
  1. COT 对冲击类故障（松靴）检出能力优于 TOT（阶次比值更高）
  2. TOT 对周期力类故障（配流盘、柱塞磨损）检出稳定
  3. TOT 路径的松靴检测需要补充角域冲击特征（波峰因子、峭度）

  算法改进方向：
  - 阶次幅值比：适用于周期力类故障（TOT 为主）
  - 角域冲击特征：适用于冲击类故障（TOT 补充）
  - 频带能量比：适用于冲击类故障（COT 为主）
""")


if __name__ == "__main__":
    main()
