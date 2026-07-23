"""合成信号正确性验证。

验证目标：
1. 频率成分是否与理论值一致（转频、柱塞通过频率、共振频率）
2. 冲击间隔是否等于柱塞通过周期
3. 故障信号与正常信号的差异是否符合物理预期
4. 信噪比是否合理

输出：每项验证的 PASS/FAIL 和详细数据
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks, hilbert
from scipy.fft import rfft, rfftfreq
from scipy.ndimage import maximum_filter1d

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from examples.generate_fault_signals import (
    generate_normal_v2,
    generate_loose_slipper_v2,
    generate_valve_plate_wear_v2,
    generate_piston_wear_v2,
    F_ROTATION,
    F_PISTON,
    SAMPLING_RATE,
    NUM_PISTONS,
)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL_COUNT += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def get_dominant_freq(signal, fs, freq_range, n_peaks=3):
    """获取指定频率范围内的主频。"""
    n = len(signal)
    fft_mag = np.abs(rfft(signal)) / n * 2
    freqs = rfftfreq(n, 1.0 / fs)
    mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
    if not np.any(mask):
        return [], []
    freqs_in = freqs[mask]
    mag_in = fft_mag[mask]
    peaks, props = find_peaks(mag_in, height=np.max(mag_in) * 0.1, distance=5)
    if len(peaks) == 0:
        return [], []
    sorted_idx = np.argsort(mag_in[peaks])[::-1][:n_peaks]
    return freqs_in[peaks[sorted_idx]], mag_in[peaks[sorted_idx]]


def main():
    global PASS_COUNT, FAIL_COUNT
    fs = SAMPLING_RATE
    f_rot = F_ROTATION
    f_piston = F_PISTON

    print("=" * 70)
    print("  合成信号正确性验证")
    print("=" * 70)

    # 生成信号
    normal = generate_normal_v2()
    loose = generate_loose_slipper_v2()
    valve = generate_valve_plate_wear_v2()
    piston = generate_piston_wear_v2()

    sig_n = normal["signal"]
    sig_l = loose["signal"]
    sig_v = valve["signal"]
    sig_p = piston["signal"]

    # ================================================================
    # 验证1：正常信号的频率成分
    # ================================================================
    print("\n--- 验证1：正常信号频率成分 ---")

    # 转频应该在 24.67Hz 附近
    freqs, mags = get_dominant_freq(sig_n, fs, (10, 40), n_peaks=1)
    if len(freqs) > 0:
        detected_rot = freqs[0]
        check("转频检测", abs(detected_rot - f_rot) < 1.0,
              f"理论={f_rot:.2f}Hz, 检测={detected_rot:.2f}Hz, 误差={abs(detected_rot-f_rot):.2f}Hz")
    else:
        check("转频检测", False, "未检测到转频")

    # 柱塞通过频率应该在 172.67Hz 附近
    freqs, mags = get_dominant_freq(sig_n, fs, (150, 200), n_peaks=1)
    if len(freqs) > 0:
        detected_fp = freqs[0]
        check("柱塞通过频率检测", abs(detected_fp - f_piston) < 2.0,
              f"理论={f_piston:.2f}Hz, 检测={detected_fp:.2f}Hz, 误差={abs(detected_fp-f_piston):.2f}Hz")
    else:
        check("柱塞通过频率检测", False, "未检测到 f_p")

    # RMS 应该在合理范围内（0.2~0.5）
    rms_n = np.sqrt(np.mean(sig_n**2))
    check("正常信号 RMS 范围", 0.15 < rms_n < 0.6,
          f"RMS={rms_n:.4f}")

    # ================================================================
    # 验证2：松靴信号的冲击特征
    # ================================================================
    print("\n--- 验证2：松靴信号冲击特征 ---")

    # 高频共振带（6~7.5kHz）能量应该比正常信号高
    nyq = fs / 2
    sos = butter(4, [6000/nyq, min(7500, nyq*0.95)/nyq], btype='band', output='sos')
    env_n = np.abs(hilbert(sosfiltfilt(sos, sig_n)))
    env_l = np.abs(hilbert(sosfiltfilt(sos, sig_l)))
    rms_env_n = np.sqrt(np.mean(env_n**2))
    rms_env_l = np.sqrt(np.mean(env_l**2))
    ratio_hf = rms_env_l / rms_env_n if rms_env_n > 0 else 0
    check("高频带能量比（松靴/正常）", ratio_hf > 1.5,
          f"比值={ratio_hf:.2f}x")

    # 包络谱中 f_p 处应该有峰值
    env_l_full = np.abs(hilbert(sosfiltfilt(sos, sig_l)))
    env_l_full = env_l_full - np.mean(env_l_full)
    env_fft_mag = np.abs(rfft(env_l_full)) / len(env_l_full) * 2
    env_freqs = rfftfreq(len(env_l_full), 1.0 / fs)
    fp_mask = (env_freqs > f_piston - 5) & (env_freqs < f_piston + 5)
    if np.any(fp_mask):
        fp_amp = np.max(env_fft_mag[fp_mask])
        # f_p 处应该有明显峰值
        noise_mask = (env_freqs > 50) & (env_freqs < 100)
        noise_amp = np.median(env_fft_mag[noise_mask]) if np.any(noise_mask) else 1e-10
        snr_fp = fp_amp / noise_amp if noise_amp > 0 else 0
        check("包络谱 f_p 处峰值", snr_fp > 3.0,
              f"f_p 幅值={fp_amp:.6f}, 噪声中值={noise_amp:.6f}, SNR={snr_fp:.1f}")
    else:
        check("包络谱 f_p 处峰值", False, "f_p 范围内无数据")

    # 冲击间隔应该接近柱塞通过周期
    # 用局部最大值法精确定位冲击时刻
    from scipy.ndimage import maximum_filter1d
    window = int(fs/f_piston * 0.8)
    local_max = maximum_filter1d(env_l, size=window)
    is_peak = (env_l == local_max) & (env_l > np.mean(env_l) + 0.5*np.std(env_l))
    peaks = np.where(is_peak)[0]
    if len(peaks) > 10:
        intervals = np.diff(peaks) / fs * 1000  # ms
        expected_interval = 1000 / f_piston  # ms ≈ 5.79ms
        mean_interval = np.mean(intervals)
        check("冲击间隔", abs(mean_interval - expected_interval) < 0.3,
              f"理论={expected_interval:.2f}ms, 检测={mean_interval:.2f}ms, 误差={abs(mean_interval-expected_interval):.2f}ms")
    else:
        check("冲击间隔", False, f"只检测到 {len(peaks)} 个冲击峰值")

    # 松靴信号的峭度应该比正常信号高（更尖锐）
    kurt_n = float(np.mean(((sig_n - np.mean(sig_n))/np.std(sig_n))**4) - 3)
    kurt_l = float(np.mean(((sig_l - np.mean(sig_l))/np.std(sig_l))**4) - 3)
    check("松靴峭度 > 正常峭度", kurt_l > kurt_n,
          f"正常={kurt_n:.2f}, 松靴={kurt_l:.2f}")

    # ================================================================
    # 验证3：配流盘磨损信号的低频特征
    # ================================================================
    print("\n--- 验证3：配流盘磨损信号低频特征 ---")

    # 转频谐波应该放大 ~3 倍
    freqs_n, mags_n = get_dominant_freq(sig_n, fs, (20, 30), n_peaks=1)
    freqs_v, mags_v = get_dominant_freq(sig_v, fs, (20, 30), n_peaks=1)
    if len(mags_n) > 0 and len(mags_v) > 0:
        ratio_1x = mags_v[0] / mags_n[0] if mags_n[0] > 0 else 0
        check("1阶幅值比（配流盘/正常）", 2.0 < ratio_1x < 4.0,
              f"比值={ratio_1x:.2f}x, 理论≈3.0x")
    else:
        check("1阶幅值比", False, "未检测到转频")

    # 柱塞频率谐波也应该放大
    freqs_n, mags_n = get_dominant_freq(sig_n, fs, (160, 185), n_peaks=1)
    freqs_v, mags_v = get_dominant_freq(sig_v, fs, (160, 185), n_peaks=1)
    if len(mags_n) > 0 and len(mags_v) > 0:
        ratio_fp = mags_v[0] / mags_n[0] if mags_n[0] > 0 else 0
        check("7阶(f_p)幅值比（配流盘/正常）", 2.0 < ratio_fp < 4.0,
              f"比值={ratio_fp:.2f}x, 理论≈3.0x")
    else:
        check("7阶幅值比", False, "未检测到 f_p")

    # 低频带（0-250Hz）RMS 应该显著增大
    sos_low = butter(2, [1/nyq, 250/nyq], btype='band', output='sos')
    rms_low_n = np.sqrt(np.mean(sosfiltfilt(sos_low, sig_n)**2))
    rms_low_v = np.sqrt(np.mean(sosfiltfilt(sos_low, sig_v)**2))
    ratio_low = rms_low_v / rms_low_n if rms_low_n > 0 else 0
    check("低频带 RMS 比（配流盘/正常）", ratio_low > 2.0,
          f"比值={ratio_low:.2f}x")

    # ================================================================
    # 验证4：柱塞磨损信号
    # ================================================================
    print("\n--- 验证4：柱塞磨损信号特征 ---")

    # 柱塞频率谐波应该放大 ~2.5 倍
    freqs_n, mags_n = get_dominant_freq(sig_n, fs, (160, 185), n_peaks=1)
    freqs_p, mags_p = get_dominant_freq(sig_p, fs, (160, 185), n_peaks=1)
    if len(mags_n) > 0 and len(mags_p) > 0:
        ratio_fp_p = mags_p[0] / mags_n[0] if mags_n[0] > 0 else 0
        check("7阶(f_p)幅值比（柱塞/正常）", 1.5 < ratio_fp_p < 3.5,
              f"比值={ratio_fp_p:.2f}x, 理论≈2.5x")
    else:
        check("7阶幅值比", False, "未检测到 f_p")

    # 2 倍柱塞频率也应该放大
    freqs_n, mags_n = get_dominant_freq(sig_n, fs, (330, 360), n_peaks=1)
    freqs_p, mags_p = get_dominant_freq(sig_p, fs, (330, 360), n_peaks=1)
    if len(mags_n) > 0 and len(mags_p) > 0:
        ratio_2fp = mags_p[0] / mags_n[0] if mags_n[0] > 0 else 0
        check("14阶(2f_p)幅值比（柱塞/正常）", 1.5 < ratio_2fp < 3.5,
              f"比值={ratio_2fp:.2f}x, 理论≈2.5x")
    else:
        check("14阶幅值比", False, "未检测到 2f_p")

    # ================================================================
    # 验证5：信噪比评估
    # ================================================================
    print("\n--- 验证5：信噪比评估 ---")

    # 松靴冲击的 SNR：高频包络峰值 vs 噪声基底
    env_l_clean = np.abs(hilbert(sosfiltfilt(sos, sig_l)))
    peak_env = np.max(env_l_clean)
    median_env = np.median(env_l_clean)
    snr_impulse = peak_env / median_env if median_env > 0 else 0
    check("松靴冲击 SNR（峰值/中值）", snr_impulse > 5.0,
          f"SNR={snr_impulse:.1f}")

    # 配流盘信号的整体 SNR：RMS 比
    snr_valve = np.sqrt(np.mean(sig_v**2)) / np.sqrt(np.mean(sig_n**2))
    check("配流盘信号增强比", snr_valve > 1.5,
          f"RMS比={snr_valve:.2f}x")

    # ================================================================
    # 验证6：物理一致性检查
    # ================================================================
    print("\n--- 验证6：物理一致性 ---")

    # 松靴：高频能量增加，低频能量不应大幅变化
    sos_low2 = butter(2, [10/nyq, 100/nyq], btype='band', output='sos')
    rms_low_n2 = np.sqrt(np.mean(sosfiltfilt(sos_low2, sig_n)**2))
    rms_low_l2 = np.sqrt(np.mean(sosfiltfilt(sos_low2, sig_l)**2))
    ratio_low_l = rms_low_l2 / rms_low_n2 if rms_low_n2 > 0 else 0
    check("松靴低频带变化小", ratio_low_l < 1.5,
          f"低频比={ratio_low_l:.2f}x (松靴能量应在高频)")

    # 配流盘：低频能量增加，高频不应大幅变化
    rms_hf_n = np.sqrt(np.mean(sosfiltfilt(sos, sig_n)**2))
    rms_hf_v = np.sqrt(np.mean(sosfiltfilt(sos, sig_v)**2))
    ratio_hf_v = rms_hf_v / rms_hf_n if rms_hf_n > 0 else 0
    check("配流盘高频带变化小", ratio_hf_v < 2.0,
          f"高频比={ratio_hf_v:.2f}x (配流盘能量应在低频)")

    # ================================================================
    # 总结
    # ================================================================
    print("\n" + "=" * 70)
    total = PASS_COUNT + FAIL_COUNT
    print(f"  验证结果: {PASS_COUNT}/{total} 通过, {FAIL_COUNT}/{total} 失败")
    if FAIL_COUNT == 0:
        print("  ✅ 合成信号正确性验证全部通过")
    else:
        print(f"  ⚠️ 有 {FAIL_COUNT} 项未通过，需要检查信号生成器")
    print("=" * 70)


if __name__ == "__main__":
    main()
