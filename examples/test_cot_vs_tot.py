"""COT vs TOT 对比验证 + STFT 参数敏感性分析。

测试内容：
1. COT（无转速信号）vs TOT（有转速信号）的阶次分析精度对比
2. STFT 窗长对 COT 转频估计精度的影响
3. 不同 STFT 参数下故障检出能力的变化

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
    OrderTrackingConfig,
    OrderTrackingAnalyzer,
    FAULT_BAND_PRESETS,
    extract_fault_band_energy,
    diagnose_by_fault_type,
    cot_order_analysis,
    tot_order_analysis,
)


TEST_DATA_DIR = Path(__file__).resolve().parents[1] / "test" / "data"


def load_signal(filepath: str) -> np.ndarray:
    return np.loadtxt(filepath).reshape(-1)


def print_separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main() -> None:
    fs = 20000.0
    f_rot_true = 1480.0 / 60.0  # 真实转频 = 24.67 Hz
    n_pistons = 7

    # 加载信号
    normal = load_signal(TEST_DATA_DIR / "normal" / "normal.txt")
    loose_slipper = load_signal(TEST_DATA_DIR / "fault" / "loose_slipper.txt")
    valve_wear = load_signal(TEST_DATA_DIR / "fault" / "valve_plate_wear.txt")
    piston_wear = load_signal(TEST_DATA_DIR / "fault" / "piston_wear.txt")

    # ============================================================
    # 生成转速信号（TOT 需要）
    # 对于合成信号，转速是恒定的 1480 RPM
    # ============================================================
    n = len(normal)
    tacho = np.full(n, f_rot_true)  # 恒定转频信号

    # ============================================================
    # Part 1: COT vs TOT 转频估计精度对比
    # ============================================================
    print_separator("Part 1: COT vs TOT 转频估计精度对比")

    print(f"\n真实转频: {f_rot_true:.4f} Hz")
    print(f"柱塞通过频率: {n_pistons * f_rot_true:.4f} Hz")

    # COT 分析
    cot_result = cot_order_analysis(normal, fs, max_order=15)
    cot_freq = cot_result["rotational_freq"]
    cot_error = abs(cot_freq - f_rot_true) / f_rot_true * 100

    # TOT 分析
    tot_result = tot_order_analysis(normal, fs, tachometer_signal=tacho, max_order=15)
    tot_freq = tot_result["rotational_freq"]
    tot_error = abs(tot_freq - f_rot_true) / f_rot_true * 100

    print(f"\n{'方法':>6} | {'估计转频':>12} | {'误差':>8} | {'角域采样点':>12}")
    print(f"{'-'*50}")
    print(f"{'COT':>6} | {cot_freq:>12.4f} Hz | {cot_error:>7.2f}% | {len(cot_result.get('angle_axis', [])):>12}")
    print(f"{'TOT':>6} | {tot_freq:>12.4f} Hz | {tot_error:>7.2f}% | {len(tot_result.get('angle_axis', [])):>12}")

    # ============================================================
    # Part 2: COT vs TOT 阶次幅值对比（正常信号）
    # ============================================================
    print_separator("Part 2: COT vs TOT 阶次幅值对比（正常信号）")

    print(f"\n{'阶次':>6} | {'COT幅值':>12} | {'TOT幅值':>12} | {'差异%':>8}")
    print(f"{'-'*48}")

    for i in range(min(15, len(cot_result["order_amplitudes"]))):
        c = cot_result["order_amplitudes"][i]
        t = tot_result["order_amplitudes"][i]
        diff = abs(c - t) / max(t, 1e-10) * 100
        print(f"  {i+1:>4} | {c:>12.6f} | {t:>12.6f} | {diff:>7.1f}%")

    # ============================================================
    # Part 3: COT vs TOT 故障检出能力对比
    # ============================================================
    print_separator("Part 3: COT vs TOT 故障检出能力对比")

    for fault_name, fault_signal in [("松靴", loose_slipper), ("配流盘磨损", valve_wear), ("柱塞磨损", piston_wear)]:
        print(f"\n--- {fault_name} ---")

        # COT 阶次分析
        cot_f = cot_order_analysis(fault_signal, fs, max_order=15)
        # TOT 阶次分析
        tot_f = tot_order_analysis(fault_signal, fs, tachometer_signal=tacho, max_order=15)

        # 基线
        cot_n = cot_order_analysis(normal, fs, max_order=15)
        tot_n = tot_order_analysis(normal, fs, tachometer_signal=tacho, max_order=15)

        print(f"  {'阶次':>4} | {'COT正常':>10} | {'COT故障':>10} | {'COT比值':>8} | {'TOT正常':>10} | {'TOT故障':>10} | {'TOT比值':>8}")
        print(f"  {'-'*75}")

        for i in range(min(15, len(cot_f["order_amplitudes"]))):
            cn = cot_n["order_amplitudes"][i]
            cf = cot_f["order_amplitudes"][i]
            tn = tot_n["order_amplitudes"][i]
            tf = tot_f["order_amplitudes"][i]
            cr = cf / cn if cn > 0 else float("inf")
            tr = tf / tn if tn > 0 else float("inf")
            print(f"  {i+1:>4} | {cn:>10.6f} | {cf:>10.6f} | {cr:>7.2f}x | {tn:>10.6f} | {tf:>10.6f} | {tr:>7.2f}x")

    # ============================================================
    # Part 4: STFT 参数敏感性分析（COT 路径）
    # ============================================================
    print_separator("Part 4: STFT 参数对 COT 转频估计的影响")

    stft_configs = [
        ("窗长=512",  512,  0.5, 2048),
        ("窗长=1024", 1024, 0.5, 4096),  # 当前默认
        ("窗长=2048", 2048, 0.5, 8192),
        ("窗长=4096", 4096, 0.5, 16384),
        ("nfft=2048", 1024, 0.5, 2048),
        ("nfft=8192", 1024, 0.5, 8192),
        ("overlap=0.25", 1024, 0.25, 4096),
        ("overlap=0.75", 1024, 0.75, 4096),
    ]

    print(f"\n真实转频: {f_rot_true:.4f} Hz")
    print(f"\n{'配置':>16} | {'窗长':>6} | {'重叠率':>6} | {'nfft':>6} | {'频率分辨率':>10} | {'估计转频':>10} | {'误差%':>6}")
    print(f"{'-'*80}")

    for name, win, overlap, nfft in stft_configs:
        freq_res = fs / win
        try:
            result = cot_order_analysis(normal, fs, max_order=15,
                                         window_size=win, overlap_ratio=overlap, nfft=nfft)
            est_freq = result["rotational_freq"]
            error = abs(est_freq - f_rot_true) / f_rot_true * 100
            print(f"  {name:>14} | {win:>6} | {overlap:>6.2f} | {nfft:>6} | {freq_res:>9.2f} Hz | {est_freq:>9.4f} Hz | {error:>5.2f}%")
        except Exception as e:
            print(f"  {name:>14} | {win:>6} | {overlap:>6.2f} | {nfft:>6} | {freq_res:>9.2f} Hz | ERROR: {e}")

    # ============================================================
    # Part 5: STFT 参数对故障检出的影响
    # ============================================================
    print_separator("Part 5: STFT 窗长对松靴故障检出的影响")

    print(f"\n松靴故障：不同 STFT 窗长下的 COT 阶次幅值比（故障/正常）")
    print(f"\n{'窗长':>6} | {'1阶':>6} | {'7阶':>6} | {'14阶':>6} | {'转频误差':>8}")
    print(f"{'-'*48}")

    for win in [256, 512, 1024, 2048, 4096]:
        try:
            cot_n = cot_order_analysis(normal, fs, max_order=15, window_size=win)
            cot_f = cot_order_analysis(loose_slipper, fs, max_order=15, window_size=win)
            freq_err = abs(cot_n["rotational_freq"] - f_rot_true) / f_rot_true * 100

            ratios = []
            for i in [0, 6, 13]:  # 1阶, 7阶, 14阶
                cn = cot_n["order_amplitudes"][i]
                cf = cot_f["order_amplitudes"][i]
                r = cf / cn if cn > 0 else float("inf")
                ratios.append(r)

            print(f"  {win:>6} | {ratios[0]:>5.2f}x | {ratios[1]:>5.2f}x | {ratios[2]:>5.2f}x | {freq_err:>7.2f}%")
        except Exception as e:
            print(f"  {win:>6} | ERROR: {e}")

    # ============================================================
    # 总结
    # ============================================================
    print_separator("总结")

    print(f"""
1. COT vs TOT 路径差异：
   - COT 靠 STFT 脊线估计转频，TOT 用真实转速信号直接重采样
   - TOT 精度更高，COT 受 STFT 参数影响大
   - 对于故障检出，TOT 应该比 COT 更稳定

2. STFT 参数影响：
   - 窗长越长 → 频率分辨率越高 → 转频估计越准
   - 但窗长越长 → 时间分辨率越差 → 变速工况下不利
   - 对于恒速工况（如本设备 1480 RPM），可以用较长窗长（2048~4096）
   - 当前默认窗长 1024 → 频率分辨率 19.5 Hz → 对 24.67 Hz 转频估计精度有限

3. 建议：
   - 如果有转速信号，优先用 TOT
   - 如果只有振动信号（COT），建议将窗长调到 2048 或 4096
   - nfft 至少是窗长的 2~4 倍
""")


if __name__ == "__main__":
    main()
