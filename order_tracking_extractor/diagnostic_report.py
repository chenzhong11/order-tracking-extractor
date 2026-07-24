"""诊断报告可视化模块 v5。

1. 除公式外全部中文标注
2. f_r 做统一单位，f_p = 7×f_r 做备注
3. 非均匀横轴：低频精细展开，高频压缩
4. 包络谱区分度：半透明填充 + 峰值数字标注
5. 诊断依据独立面板，不与其他图重叠
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy.signal import butter, sosfiltfilt, hilbert
from .core import compute_fft_spectrum

# 颜色
C_N = "#1565C0"; C_F = "#C62828"; C_FR = "#2E7D32"
C_FP = "#E65100"; C_HARM = "#6A1B9A"; C_GRAY = "#9E9E9E"; C_DIAG = "#00838F"


def _setup_style():
    cjk = None
    for p in ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(p):
            cjk = fm.FontProperties(fname=p).get_name(); break
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [cjk or "DejaVu Sans", "DejaVu Sans"],
        "axes.unicode_minus": False, "axes.facecolor": "#FAFAFA",
        "figure.facecolor": "white", "axes.grid": True,
        "grid.color": "#E0E0E0", "grid.linewidth": 0.4, "grid.alpha": 0.5,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    })


class SegmentedAxis:
    def __init__(self, segments, weights):
        self.segments = segments
        total = sum(weights)
        self.weights = [w / total for w in weights]
        self.bounds = []
        pos = 0.0
        for w in self.weights:
            self.bounds.append((pos, pos + w)); pos += w

    def transform(self, freqs):
        result = np.zeros_like(freqs, dtype=float)
        for (f0, f1), (c0, c1) in zip(self.segments, self.bounds):
            mask = (freqs >= f0) & (freqs <= f1)
            if np.any(mask):
                result[mask] = c0 + (freqs[mask] - f0) / (f1 - f0) * (c1 - c0)
        return result

    def setup_axis(self, ax, step_per_segment=None, xlabel="频率 (Hz)"):
        ticks_c, labels = [], []
        for i, (f0, f1) in enumerate(self.segments):
            step = step_per_segment[i] if step_per_segment else (f1 - f0) / 8
            f = f0
            while f <= f1 + 0.01:
                c = self.transform(np.array([f]))[0]
                if 0.01 < c < 0.99:
                    ticks_c.append(c)
                    labels.append(f"{f:.0f}" if f < 1000 else f"{f/1000:.1f}k")
                f += step
        ax.set_xticks(ticks_c); ax.set_xticklabels(labels, fontsize=9)
        ax.set_xlim(0, 1); ax.set_xlabel(xlabel, fontsize=11)
        for c0, c1 in self.bounds[1:]:
            ax.axvline(c0, color=C_GRAY, linestyle=":", lw=0.8, alpha=0.5)


def _amp_at(freqs, mags, target, bw=3):
    idx = np.argmin(np.abs(freqs - target))
    lo, hi = max(0, idx - bw), min(len(mags), idx + bw + 1)
    return float(np.max(mags[lo:hi]))

def _freq_at_peak(freqs, mags, target, bw=5):
    idx = np.argmin(np.abs(freqs - target))
    lo, hi = max(0, idx - bw), min(len(mags), idx + bw + 1)
    li = np.argmax(mags[lo:hi])
    return float(freqs[lo + li]), float(mags[lo + li])


def _char_freq_items(f_r, n_pistons=7):
    f_p = f_r * n_pistons
    return [
        {"freq": f_r,   "label": f"$f_r$",              "color": C_FR},
        {"freq": 2*f_r, "label": f"$2f_r$",             "color": C_FR},
        {"freq": 3*f_r, "label": f"$3f_r$",             "color": C_FR},
        {"freq": f_p,   "label": f"$7f_r$\n(=$f_p$)",  "color": C_FP},
        {"freq": 2*f_p, "label": f"$14f_r$\n(=$2f_p$)","color": C_HARM},
        {"freq": 3*f_p, "label": f"$21f_r$\n(=$3f_p$)","color": C_HARM},
    ]


def _annotate_freqs(ax, seg_axis, freq_items, y_top,
                    freqs_n=None, mags_n=None, freqs_f=None, mags_f=None):
    for item in freq_items:
        c = seg_axis.transform(np.array([item["freq"]]))[0]
        if c < 0 or c > 1: continue
        ax.axvline(c, color=item["color"], linestyle="--", lw=1.2, alpha=0.5)
        ax.annotate(item["label"], xy=(c, y_top * 0.93), fontsize=8,
                    color=item["color"], fontweight="bold", ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                              edgecolor=item["color"], alpha=0.9, lw=0.6))
        if freqs_n is not None and freqs_f is not None:
            _, vn = _freq_at_peak(freqs_n, mags_n, item["freq"])
            _, vf = _freq_at_peak(freqs_f, mags_f, item["freq"])
            yn = y_top * 0.93 - y_top * 0.06
            yf = y_top * 0.93 - y_top * 0.12
            fn = f"n={vn:.4f}" if vn < 0.01 else f"n={vn:.3f}"
            ff = f"f={vf:.4f}" if vf < 0.01 else f"f={vf:.3f}"
            ax.text(c, yn, fn, fontsize=7, color=C_N, fontweight="bold", ha="center", va="top")
            ax.text(c, yf, ff, fontsize=7, color=C_F, fontweight="bold", ha="center", va="top")


def _extract_diagnosis_basis(diagnosis_results, f_r, n_pistons=7):
    from .core import FAULT_DIAGNOSTICS
    f_p = f_r * n_pistons
    triggered_faults, all_features = [], []
    for r in diagnosis_results:
        if not r.get("is_fault"): continue
        triggered_faults.append(r.get("fault_type", ""))
        for feat in r.get("primary_features", []):
            if feat.get("triggered"):
                all_features.append({
                    "fault": r.get("fault_type", ""), "feature": feat.get("feature", ""),
                    "ratio": feat.get("ratio", 0), "threshold": feat.get("threshold", 0),
                })
    key_freqs = set()
    for feat in all_features:
        p = feat["feature"]
        if "7x_fp" in p or "tot_key_orders.7" in p: key_freqs.add((f_p, "$7f_r$", C_FP))
        if "14x_2fp" in p or "tot_key_orders.14" in p: key_freqs.add((2*f_p, "$14f_r$", C_HARM))
        if "21x_3fp" in p or "tot_key_orders.21" in p: key_freqs.add((3*f_p, "$21f_r$", C_HARM))
        if "band_0_100" in p:
            key_freqs.add((f_r, "$f_r$", C_FR)); key_freqs.add((2*f_r, "$2f_r$", C_FR))
    if not key_freqs: key_freqs.add((f_p, "$7f_r$", C_FP))
    return {"triggered_faults": triggered_faults, "triggered_features": all_features,
            "key_frequencies": list(key_freqs)}


def _plot_ranking(ax, results):
    sr = sorted(results, key=lambda x: x.get("confidence", 0), reverse=True)
    names = [r.get("fault_type", "?") for r in sr]
    confs = [r.get("confidence", 0) for r in sr]
    flags = [r.get("is_fault", False) for r in sr]
    names, confs, flags = names[::-1], confs[::-1], flags[::-1]
    y = np.arange(len(names))
    colors = [C_F if f else C_GRAY for f in flags]
    bars = ax.barh(y, confs, color=colors, height=0.5, alpha=0.85, edgecolor="white", lw=0.5)
    for bar, conf, flag in zip(bars, confs, flags):
        txt = f"{conf:.2f}" + ("  \u2713" if flag else "")
        ax.text(bar.get_width() + 0.04, bar.get_y() + bar.get_height() / 2,
                txt, va="center", ha="left", fontsize=10,
                fontweight="bold" if flag else "normal", color=C_F if flag else "black")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=10)
    ax.set_xlabel("置信度", fontsize=11)
    ax.set_title("故障概率排序", fontsize=13, fontweight="bold", pad=10)
    ax.set_xlim(0, max(max(confs) * 1.3, 1.05))
    ax.axvline(1.0, color="#E0E0E0", linestyle=":", alpha=0.5)
    ax.grid(axis="x", visible=True); ax.grid(axis="y", visible=False)


def _plot_diagnosis_basis(ax, basis):
    """诊断依据面板（独立区域）。"""
    ax.axis("off")
    lines = ["诊断依据", ""]
    lines.append(f"触发故障: {', '.join(basis['triggered_faults']) or '无'}")
    lines.append("")
    freq_strs = []
    for freq, label, _ in basis["key_frequencies"]:
        freq_strs.append(f"{label}={freq:.0f}Hz" if freq < 1000 else f"{label}={freq/1000:.1f}kHz")
    lines.append("关键频率: " + ", ".join(freq_strs))
    lines.append("")
    lines.append("触发特征:")
    for feat in basis["triggered_features"][:5]:
        parts = feat["feature"].split(".")
        short = ".".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
        lines.append(f"  {short}")
        lines.append(f"    比值={feat['ratio']:.2f}x (阈值={feat['threshold']:.1f}x)")
    text = "\n".join(lines)
    ax.text(0.05, 0.95, text, transform=ax.transAxes, fontsize=9.5, va="top",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#E0F7FA", edgecolor=C_DIAG, alpha=0.9))


def _plot_conclusion(ax, summary, device_info=None):
    ax.axis("off")
    lines = []
    if device_info:
        np_ = device_info.get("n_pistons", 7)
        rpm = device_info.get("speed_rpm", 1480)
        fs = device_info.get("sampling_rate", 20000)
        f_r = rpm / 60
        lines.append(f"设备: {np_}柱塞, {rpm}RPM, 采样率{fs/1000:.0f}kHz")
        lines.append(f"转频 $f_r$={f_r:.2f}Hz, 柱塞通过频率 $f_p$={np_}$f_r$={f_r*np_:.2f}Hz")
        lines.append("")
    conclusion = summary.get("conclusion", "未检测到已知故障模式")
    detected = summary.get("detected_faults", [])
    lines.append(f"诊断结论: {conclusion}")
    if detected: lines.append(f"检测到: {', '.join(detected)}")
    ax.text(0.03, 0.9, "\n".join(lines), transform=ax.transAxes, fontsize=11, va="top",
            bbox=dict(boxstyle="round,pad=0.6", facecolor="#E3F2FD", edgecolor="#1565C0", alpha=0.9))


def generate_diagnostic_report(
    normal_signal, fault_signal, diagnosis_results,
    sampling_rate=20000.0, rotational_freq=24.67, n_pistons=7,
    device_info=None, diagnosis_summary=None,
    output_path="diagnostic_report.png",
    envelope_band=(6000.0, 7500.0),
    title="柱塞泵故障诊断报告",
    y_mode="amplitude",
) -> str:
    _setup_style()
    sig_n = np.asarray(normal_signal, dtype=float).reshape(-1)
    sig_f = np.asarray(fault_signal, dtype=float).reshape(-1)
    fs, f_r = sampling_rate, rotational_freq
    f_p = f_r * n_pistons

    fft_axis = SegmentedAxis([(0, 600), (600, 8000)], [0.70, 0.30])
    env_axis = SegmentedAxis([(0, 600), (600, 3000)], [0.70, 0.30])
    char_items = _char_freq_items(f_r, n_pistons)
    basis = _extract_diagnosis_basis(diagnosis_results, f_r, n_pistons)

    # 布局: 上排(时域+排序), 中排(FFT全宽), 下排(包络谱+诊断依据), 底排(结论)
    fig = plt.figure(figsize=(20, 16))
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1.3, 1.1, 0.5],
                          width_ratios=[2, 1], hspace=0.35, wspace=0.25)
    ax_time  = fig.add_subplot(gs[0, 0])
    ax_rank  = fig.add_subplot(gs[0, 1])
    ax_fft   = fig.add_subplot(gs[1, :])
    ax_env   = fig.add_subplot(gs[2, 0])
    ax_basis = fig.add_subplot(gs[2, 1])
    ax_sum   = fig.add_subplot(gs[3, :])

    # === 1. 时域波形 ===
    n_show = min(len(sig_n), len(sig_f), int(0.08 * fs))
    t_ms = np.arange(n_show) / fs * 1000
    ax_time.plot(t_ms, sig_n[:n_show], color=C_N, lw=0.3, alpha=0.7, label="正常")
    ax_time.plot(t_ms, sig_f[:n_show], color=C_F, lw=0.3, alpha=0.7, label="故障")
    ax_time.set_xlabel("时间 (ms)", fontsize=11); ax_time.set_ylabel("幅值", fontsize=11)
    ax_time.set_title("时域波形对比", fontsize=13, fontweight="bold")
    ax_time.legend(fontsize=10, loc="upper right")
    for sig, color, lbl in [(sig_n, C_N, "正常"), (sig_f, C_F, "故障")]:
        k = float(np.mean(((sig - np.mean(sig)) / np.std(sig)) ** 4) - 3) if np.std(sig) > 0 else 0
        rms = float(np.sqrt(np.mean(sig ** 2)))
        yp = 0.95 if lbl == "正常" else 0.80
        ax_time.text(0.02, yp, f"{lbl}: 峭度={k:.2f}, RMS={rms:.4f}",
                     transform=ax_time.transAxes, fontsize=9, color=color, va="top",
                     bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color, alpha=0.85))

    # === 2. FFT 频谱 ===
    freqs_n, mags_n = compute_fft_spectrum(sig_n, fs)
    freqs_f, mags_f = compute_fft_spectrum(sig_f, fs)
    use_energy = (y_mode == "energy")
    pn = mags_n ** 2 if use_energy else mags_n
    pf = mags_f ** 2 if use_energy else mags_f
    y_label = "能量 (幅值²)" if use_energy else "幅值"

    for freqs, mags, color, lbl in [(freqs_n, pn, C_N, "正常"), (freqs_f, pf, C_F, "故障")]:
        mask = freqs <= 8000
        ax_fft.plot(fft_axis.transform(freqs[mask]), mags[mask], color=color, lw=0.5, alpha=0.7, label=lbl)

    y_top = 0
    for freqs, mags in [(freqs_n, pn), (freqs_f, pf)]:
        mask = freqs <= 600
        if np.any(mask): y_top = max(y_top, np.max(mags[mask]))
    y_top *= 1.35; ax_fft.set_ylim(0, y_top)

    fft_axis.setup_axis(ax_fft, step_per_segment=[50, 1000], xlabel="频率 (Hz)")
    ax_fft.set_ylabel(y_label, fontsize=11)
    ax_fft.set_title(f"FFT 频谱对比（非均匀横轴）", fontsize=13, fontweight="bold")
    ax_fft.legend(fontsize=9, loc="upper right")
    _annotate_freqs(ax_fft, fft_axis, char_items, y_top, freqs_n=freqs_n, mags_n=pn, freqs_f=freqs_f, mags_f=pf)

    for freq, label, color in basis["key_frequencies"]:
        c = fft_axis.transform(np.array([freq]))[0]
        if 0 < c < 1: ax_fft.axvspan(c - 0.015, c + 0.015, alpha=0.12, color=C_DIAG)

    # === 3. 包络谱 ===
    nyq = fs / 2
    lo, hi = max(envelope_band[0], 1.0) / nyq, min(envelope_band[1], nyq * 0.99) / nyq
    if lo < hi:
        sos = butter(4, [lo, hi], btype="band", output="sos")
        def _env_spec(sig):
            f = sosfiltfilt(sos, sig)
            e = np.abs(hilbert(f)) - np.mean(np.abs(hilbert(f)))
            return compute_fft_spectrum(e, fs)
        ef_n, em_n = _env_spec(sig_n); ef_f, em_f = _env_spec(sig_f)

        mask_f = ef_f <= 3000
        ax_env.fill_between(env_axis.transform(ef_f[mask_f]), 0, em_f[mask_f],
                            color=C_F, alpha=0.15, label="故障 (填充)")
        ax_env.plot(env_axis.transform(ef_f[mask_f]), em_f[mask_f], color=C_F, lw=1.0, alpha=0.85)
        mask_n = ef_n <= 3000
        ax_env.plot(env_axis.transform(ef_n[mask_n]), em_n[mask_n], color=C_N, lw=1.2, alpha=0.9, label="正常", zorder=5)

        ye = max(np.max(em_f[mask_f]) if np.any(mask_f) else 0,
                 np.max(em_n[mask_n]) if np.any(mask_n) else 0) * 1.4
        ax_env.set_ylim(0, ye)
        env_axis.setup_axis(ax_env, step_per_segment=[50, 500], xlabel="频率 (Hz)")
        ax_env.set_ylabel("幅值", fontsize=11)
        band_str = f"{envelope_band[0]/1000:.0f}~{envelope_band[1]/1000:.1f}kHz"
        ax_env.set_title(f"包络谱（{band_str} 共振解调）", fontsize=13, fontweight="bold")
        ax_env.legend(fontsize=9, loc="upper right")

        env_items = [
            {"freq": f_p,   "label": f"$7f_r$ (=$f_p$)",   "color": C_FP},
            {"freq": 2*f_p, "label": f"$14f_r$ (=$2f_p$)", "color": C_HARM},
            {"freq": 3*f_p, "label": f"$21f_r$ (=$3f_p$)", "color": C_HARM},
        ]
        _annotate_freqs(ax_env, env_axis, env_items, ye, freqs_n=ef_n, mags_n=em_n, freqs_f=ef_f, mags_f=em_f)

        a_n, a_f = _amp_at(ef_n, em_n, f_p), _amp_at(ef_f, em_f, f_p)
        if a_n > 0:
            c_fp = env_axis.transform(np.array([f_p]))[0]
            ax_env.annotate(f"$7f_r$ 幅值比: {a_f/a_n:.1f}x", xy=(c_fp, a_f),
                            xytext=(c_fp + 0.12, a_f * 0.75), fontsize=11, fontweight="bold", color=C_FP,
                            arrowprops=dict(arrowstyle="->", color=C_FP, lw=2),
                            bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFF3E0", edgecolor=C_FP, alpha=0.9))

    # === 4. 排序 + 诊断依据 + 结论 ===
    _plot_ranking(ax_rank, diagnosis_results)
    _plot_diagnosis_basis(ax_basis, basis)

    if diagnosis_summary is None:
        triggered = [r for r in diagnosis_results if r.get("is_fault")]
        if not triggered: conclusion, detected = "未检测到已知故障模式", []
        elif len(triggered) == 1: conclusion = f"检测到: {triggered[0].get('fault_type', '')}"; detected = [triggered[0].get("fault_type", "")]
        else:
            triggered.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            conclusion = f"最可能: {triggered[0].get('fault_type', '')}"; detected = [t.get("fault_type", "") for t in triggered]
        diagnosis_summary = {"conclusion": conclusion, "detected_faults": detected}
    _plot_conclusion(ax_sum, diagnosis_summary, device_info)

    fig.suptitle(title, fontsize=16, fontweight="bold", y=0.99)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def generate_report_from_signals(
    normal_signals, fault_signals, sampling_rate=20000.0,
    rotational_freq=24.67, n_pistons=7,
    output_path="diagnostic_report.png", title="柱塞泵故障诊断报告",
) -> Tuple[str, Dict[str, Any]]:
    from .core import extract_multi_axis_features, diagnose_by_fault_pattern
    normal_feat = extract_multi_axis_features(normal_signals, sampling_rate)
    fault_feat = extract_multi_axis_features(fault_signals, sampling_rate)
    summary = diagnose_by_fault_pattern(fault_feat, normal_feat)
    device_info = {"n_pistons": n_pistons, "speed_rpm": rotational_freq * 60, "sampling_rate": sampling_rate}
    best_axis = max(fault_signals.keys(), key=lambda a: np.sqrt(np.mean(fault_signals[a] ** 2)))
    path = generate_diagnostic_report(
        normal_signals[best_axis], fault_signals[best_axis], summary["all_results"],
        sampling_rate=sampling_rate, rotational_freq=rotational_freq, n_pistons=n_pistons,
        device_info=device_info, diagnosis_summary=summary, output_path=output_path, title=title,
    )
    return path, summary
