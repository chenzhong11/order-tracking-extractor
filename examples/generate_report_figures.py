"""技术报告配图生成脚本。

按验证阶段分类生成图片：
  图1: 仿真信号有效性验证（合成信号白盒测试）
  图2: 阶次分析算法有效性（COT vs TOT 对比）
  图3: 故障诊断综合报告（真实数据黑盒测试）
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy.signal import butter, sosfiltfilt, hilbert
from scipy.fft import rfft, rfftfreq

from order_tracking_extractor import (
    OrderTrackingConfig, OrderTrackingAnalyzer,
    cot_order_analysis, tot_order_analysis,
    compute_fft_spectrum, FAULT_BAND_PRESETS, extract_fault_band_energy,
    extract_multi_axis_features, diagnose_by_fault_pattern,
    calibrate_from_signal, compare_threshold_modes,
)
from order_tracking_extractor.diagnostic_report import (
    generate_diagnostic_report, SegmentedAxis, _setup_style,
    C_N, C_F, C_FR, C_FP, C_HARM, C_GRAY, C_DIAG,
)

OUT = "docs/images"
os.makedirs(OUT, exist_ok=True)

fs = 20000.0
f_r = 1480.0 / 60  # 24.67 Hz
f_p = 7 * f_r       # 172.67 Hz

# 加载真实数据
normal_x = np.loadtxt("test/data/real/normal/8MPa_N-X.txt")
normal_y = np.loadtxt("test/data/real/normal/8MPa_N-Y.txt")
normal_z = np.loadtxt("test/data/real/normal/8MPa_N-Z.txt")
fault_x = np.loadtxt("test/data/real/fault/8MPA-X.txt")
fault_y = np.loadtxt("test/data/real/fault/8MPA-Y.txt")
fault_z = np.loadtxt("test/data/real/fault/8MPA-Z.txt")


# ============================================================
# 图1: 仿真信号有效性验证
# ============================================================

def generate_fig1():
    """合成信号白盒测试：已知参数的脉冲串 + 噪声，验证算法能否恢复特征频率。"""
    _setup_style()

    # 合成信号：正常 = 转频脉动 + 柱塞频率脉动 + 噪声
    t = np.arange(0, 1, 1/fs)
    np.random.seed(42)

    # 正常信号
    normal = (0.3 * np.sin(2*np.pi*f_r*t) +
              0.15 * np.sin(2*np.pi*f_p*t) +
              0.05 * np.random.randn(len(t)))

    # 故障信号：松靴 — 在 f_p 频率上叠加冲击脉冲
    impulse_train = np.zeros_like(t)
    period = int(fs / f_p)
    for i in range(0, len(t), period):
        if i < len(t):
            impulse_train[i] = 1.0
    # 指数衰减脉冲
    decay = np.exp(-np.arange(500) / 50)
    fault_impulse = np.convolve(impulse_train, decay, mode='same')[:len(t)]

    fault = normal + 0.8 * fault_impulse

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # (a) 时域波形
    n_show = int(0.05 * fs)
    t_ms = np.arange(n_show) / fs * 1000
    axes[0, 0].plot(t_ms, normal[:n_show], color=C_N, lw=0.3, alpha=0.7, label="正常")
    axes[0, 0].plot(t_ms, fault[:n_show], color=C_F, lw=0.3, alpha=0.7, label="故障（松靴冲击）")
    axes[0, 0].set_xlabel("时间 (ms)")
    axes[0, 0].set_ylabel("幅值")
    axes[0, 0].set_title("(a) 合成信号时域波形")
    axes[0, 0].legend(fontsize=9)

    # (b) FFT 频谱
    freqs_n, mags_n = compute_fft_spectrum(normal, fs)
    freqs_f, mags_f = compute_fft_spectrum(fault, fs)
    mask = freqs_n <= 500
    axes[0, 1].plot(freqs_n[mask], mags_n[mask], color=C_N, lw=0.5, alpha=0.7, label="正常")
    axes[0, 1].plot(freqs_f[mask], mags_f[mask], color=C_F, lw=0.5, alpha=0.7, label="故障")
    for f, lbl, c in [(f_r, "$f_r$", C_FR), (f_p, "$f_p$", C_FP), (2*f_p, "$2f_p$", C_HARM)]:
        axes[0, 1].axvline(f, color=c, ls="--", lw=1, alpha=0.6)
        axes[0, 1].annotate(lbl, xy=(f, axes[0, 1].get_ylim()[1]*0.9),
                            fontsize=8, color=c, fontweight="bold", ha="center")
    axes[0, 1].set_xlabel("频率 (Hz)")
    axes[0, 1].set_ylabel("幅值")
    axes[0, 1].set_title("(b) FFT 频谱（特征频率标注）")
    axes[0, 1].legend(fontsize=9)

    # (c) 包络谱
    nyq = fs / 2
    sos = butter(4, [6000/nyq, min(7500, nyq*0.95)/nyq], btype="band", output="sos")
    def env_spec(sig):
        f = sosfiltfilt(sos, sig)
        e = np.abs(hilbert(f)) - np.mean(np.abs(hilbert(f)))
        return compute_fft_spectrum(e, fs)

    ef_n, em_n = env_spec(normal)
    ef_f, em_f = env_spec(fault)
    mask = ef_n <= 500
    axes[1, 0].plot(ef_n[mask], em_n[mask], color=C_N, lw=0.8, alpha=0.7, label="正常")
    axes[1, 0].fill_between(ef_f[mask], 0, em_f[mask], color=C_F, alpha=0.15)
    axes[1, 0].plot(ef_f[mask], em_f[mask], color=C_F, lw=1.0, alpha=0.85, label="故障")
    for f, lbl, c in [(f_p, "$f_p$", C_FP), (2*f_p, "$2f_p$", C_HARM)]:
        axes[1, 0].axvline(f, color=c, ls="--", lw=1, alpha=0.6)
        axes[1, 0].annotate(lbl, xy=(f, axes[1, 0].get_ylim()[1]*0.9),
                            fontsize=8, color=c, fontweight="bold", ha="center")
    axes[1, 0].set_xlabel("频率 (Hz)")
    axes[1, 0].set_ylabel("幅值")
    axes[1, 0].set_title("(c) 包络谱（6~7.5kHz 共振解调）")
    axes[1, 0].legend(fontsize=9)

    # (d) 阶次谱（TOT）
    tacho = np.full(len(normal), f_r)
    tot_n = tot_order_analysis(normal, fs, tachometer_signal=tacho, max_order=15)
    tot_f = tot_order_analysis(fault, fs, tachometer_signal=tacho, max_order=15)
    orders = np.arange(1, 16)
    width = 0.35
    axes[1, 1].bar(orders - width/2, tot_n['order_amplitudes'][:15], width,
                   label="正常", color=C_N, alpha=0.7)
    axes[1, 1].bar(orders + width/2, tot_f['order_amplitudes'][:15], width,
                   label="故障", color=C_F, alpha=0.7)
    for order in [1, 7, 14]:
        axes[1, 1].axvline(order, color=C_FP if order == 7 else C_FR, ls=":", lw=0.8, alpha=0.5)
    axes[1, 1].set_xlabel("阶次")
    axes[1, 1].set_ylabel("幅值")
    axes[1, 1].set_title("(d) TOT 阶次谱对比")
    axes[1, 1].legend(fontsize=9)
    axes[1, 1].set_xticks(orders)

    fig.suptitle("图1: 仿真信号有效性验证（白盒测试）", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    fig.savefig(f"{OUT}/fig1_signal_validation.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("✅ 图1: 仿真信号有效性验证")


# ============================================================
# 图2: 阶次分析算法有效性（COT vs TOT）
# ============================================================

def generate_fig2():
    """COT vs TOT 对比：转频估计精度、阶次幅值一致性、故障检出能力。"""
    _setup_style()

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    # (a) COT vs TOT 转频估计
    tacho = np.full(len(normal_x), f_r)
    cot_result = cot_order_analysis(normal_x, fs, max_order=15)
    tot_result = tot_order_analysis(normal_x, fs, tachometer_signal=tacho, max_order=15)

    cot_freq = cot_result['rotational_freq']
    tot_freq = tot_result['rotational_freq']
    methods = ['COT', 'TOT', '真实值']
    freqs = [cot_freq, tot_freq, f_r]
    colors = [C_N, C_F, C_FR]
    bars = axes[0, 0].bar(methods, freqs, color=colors, alpha=0.8, width=0.5)
    for bar, val in zip(bars, freqs):
        axes[0, 0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                        f"{val:.2f}Hz", ha="center", fontsize=10, fontweight="bold")
    axes[0, 0].axhline(f_r, color=C_FR, ls=":", lw=0.8, alpha=0.5)
    axes[0, 0].set_ylabel("转频 (Hz)")
    axes[0, 0].set_title(f"(a) 转频估计精度（真实={f_r:.2f}Hz）")

    # (b) COT vs TOT 阶次幅值对比
    orders = np.arange(1, 16)
    width = 0.35
    axes[0, 1].bar(orders - width/2, cot_result['order_amplitudes'][:15], width,
                   label=f"COT", color=C_N, alpha=0.7)
    axes[0, 1].bar(orders + width/2, tot_result['order_amplitudes'][:15], width,
                   label=f"TOT", color=C_F, alpha=0.7)
    axes[0, 1].set_xlabel("阶次")
    axes[0, 1].set_ylabel("幅值")
    axes[0, 1].set_title("(b) COT vs TOT 阶次幅值（正常信号）")
    axes[0, 1].legend(fontsize=9)
    axes[0, 1].set_xticks(orders)

    # (c) 故障检出能力：COT
    cot_f = cot_order_analysis(fault_x, fs, max_order=15)
    cot_ratio = cot_f['order_amplitudes'][:15] / np.maximum(cot_result['order_amplitudes'][:15], 1e-10)
    axes[1, 0].bar(orders, cot_ratio, color=[C_FP if o in [7, 14] else C_N for o in orders], alpha=0.8)
    axes[1, 0].axhline(1.0, color=C_GRAY, ls=":", lw=0.8)
    axes[1, 0].set_xlabel("阶次")
    axes[1, 0].set_ylabel("故障/正常 比值")
    axes[1, 0].set_title("(c) COT 故障检出比值")
    axes[1, 0].set_xticks(orders)
    for o in [7, 14]:
        axes[1, 0].annotate(f"{cot_ratio[o-1]:.1f}x", xy=(o, cot_ratio[o-1]),
                            xytext=(o, cot_ratio[o-1]*1.1), fontsize=9,
                            fontweight="bold", color=C_FP, ha="center")

    # (d) 故障检出能力：TOT
    tot_f = tot_order_analysis(fault_x, fs, tachometer_signal=tacho, max_order=15)
    tot_ratio = tot_f['order_amplitudes'][:15] / np.maximum(tot_result['order_amplitudes'][:15], 1e-10)
    axes[1, 1].bar(orders, tot_ratio, color=[C_FP if o in [7, 14] else C_F for o in orders], alpha=0.8)
    axes[1, 1].axhline(1.0, color=C_GRAY, ls=":", lw=0.8)
    axes[1, 1].set_xlabel("阶次")
    axes[1, 1].set_ylabel("故障/正常 比值")
    axes[1, 1].set_title("(d) TOT 故障检出比值")
    axes[1, 1].set_xticks(orders)
    for o in [7, 14]:
        axes[1, 1].annotate(f"{tot_ratio[o-1]:.1f}x", xy=(o, tot_ratio[o-1]),
                            xytext=(o, tot_ratio[o-1]*1.1), fontsize=9,
                            fontweight="bold", color=C_FP, ha="center")

    fig.suptitle("图2: 阶次分析算法有效性验证（COT vs TOT 对比）", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    fig.savefig(f"{OUT}/fig2_order_tracking_validation.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("✅ 图2: 阶次分析算法有效性")


# ============================================================
# 图3: 统计阈值对比验证
# ============================================================

def generate_fig3():
    """三种阈值模式对比：固定比值 / 3σ / P95。"""
    _setup_style()

    normal_feat = extract_multi_axis_features({'X': normal_x, 'Z': normal_z}, fs)
    fault_feat = extract_multi_axis_features({'X': fault_x, 'Z': fault_z}, fs)
    result = compare_threshold_modes(normal_x, fault_feat, normal_feat, fs)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    modes = ['fixed', '3sigma', 'p95']
    titles = ['固定比值阈值', '3σ 统计阈值', 'P95 统计阈值']

    for idx, (mode, title) in enumerate(zip(modes, titles)):
        ax = axes[idx]
        r = result[mode]
        names = [dr['fault_type'] for dr in r['all_results']]
        confs = [dr['confidence'] for dr in r['all_results']]
        flags = [dr['is_fault'] for dr in r['all_results']]

        colors = [C_F if f else C_GRAY for f in flags]
        bars = ax.barh(range(len(names)), confs, color=colors, height=0.5, alpha=0.85)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=9)
        ax.set_xlabel("置信度")
        ax.set_title(f"({chr(97+idx)}) {title}", fontsize=12, fontweight="bold")
        ax.set_xlim(0, 2.2)

        for bar, conf, flag in zip(bars, confs, flags):
            txt = f"{conf:.2f}" + ("  ✓" if flag else "")
            ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
                    txt, va="center", fontsize=9,
                    fontweight="bold" if flag else "normal",
                    color=C_F if flag else "black")

    fig.suptitle("图3: 统计阈值对比验证（同一组故障数据）", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(f"{OUT}/fig3_threshold_comparison.png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("✅ 图3: 统计阈值对比")


# ============================================================
# 图4: 诊断报告（主图）
# ============================================================

def generate_fig4():
    """完整诊断报告。"""
    from order_tracking_extractor.diagnostic_report import generate_report_from_signals
    normal_signals = {'X': normal_x, 'Y': normal_y, 'Z': normal_z}
    fault_signals = {'X': fault_x, 'Y': fault_y, 'Z': fault_z}
    path, summary = generate_report_from_signals(
        normal_signals, fault_signals, fs, f_r, 7,
        output_path=f"{OUT}/fig4_diagnostic_report.png",
        title="图4: 柱塞泵故障诊断综合报告",
    )
    print(f"✅ 图4: 诊断报告 → {path}")


# ============================================================
# 主函数
# ============================================================

if __name__ == "__main__":
    generate_fig1()
    generate_fig2()
    generate_fig3()
    generate_fig4()
    print(f"\n所有图片已保存到 {OUT}/")
