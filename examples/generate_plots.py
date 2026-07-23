"""生成验证图片：真实数据的关键频率高亮对比图。"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from scipy.signal import butter, sosfiltfilt, hilbert
from scipy.fft import rfft, rfftfreq

plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# 数据加载
# ============================================================
base = "test/data/real"
normal_x = np.loadtxt(f"{base}/normal/8MPa_N-X.txt").reshape(-1)
normal_y = np.loadtxt(f"{base}/normal/8MPa_N-Y.txt").reshape(-1)
normal_z = np.loadtxt(f"{base}/normal/8MPa_N-Z.txt").reshape(-1)
fault_x = np.loadtxt(f"{base}/fault/8MPA-X.txt").reshape(-1)
fault_y = np.loadtxt(f"{base}/fault/8MPA-Y.txt").reshape(-1)
fault_z = np.loadtxt(f"{base}/fault/8MPA-Z.txt").reshape(-1)

fs = 20000.0
f_rot = 1480.0 / 60.0  # 24.67 Hz
f_piston = 7 * f_rot     # 172.67 Hz

out_dir = "docs/images"
import os
os.makedirs(out_dir, exist_ok=True)


def fft_mag(sig, fs):
    n = len(sig)
    mag = np.abs(rfft(sig)) / n * 2
    freq = rfftfreq(n, 1.0 / fs)
    return freq, mag


# ============================================================
# 图1：FFT 频谱对比（X轴）— 关键频率高亮
# ============================================================
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

freq_n, mag_n = fft_mag(normal_x, fs)
freq_f, mag_f = fft_mag(fault_x, fs)

# 正常信号
axes[0].plot(freq_n, mag_n, color='#2196F3', linewidth=0.5, alpha=0.8)
axes[0].set_title('Normal Signal (X-axis)', fontsize=14, fontweight='bold')
axes[0].set_ylabel('Amplitude', fontsize=12)
axes[0].set_xlim(0, 500)
axes[0].set_ylim(0, max(np.max(mag_n[:int(500/fs*len(mag_n))])*1.2, 0.001))

# 标注关键频率
for f, label, color in [(f_rot, 'f_r=24.67Hz', '#4CAF50'),
                         (f_piston, 'f_p=172.67Hz', '#FF9800'),
                         (2*f_piston, '2f_p=345.33Hz', '#F44336')]:
    axes[0].axvline(f, color=color, linestyle='--', linewidth=1.5, alpha=0.8)
    axes[0].annotate(label, xy=(f, axes[0].get_ylim()[1]*0.9),
                     fontsize=9, color=color, fontweight='bold',
                     ha='center', va='top',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9))

# 故障信号
axes[1].plot(freq_f, mag_f, color='#F44336', linewidth=0.5, alpha=0.8)
axes[1].set_title('Fault Signal (X-axis)', fontsize=14, fontweight='bold')
axes[1].set_ylabel('Amplitude', fontsize=12)
axes[1].set_xlabel('Frequency (Hz)', fontsize=12)

for f, label, color in [(f_rot, 'f_r=24.67Hz', '#4CAF50'),
                         (f_piston, 'f_p=172.67Hz', '#FF9800'),
                         (2*f_piston, '2f_p=345.33Hz', '#F44336')]:
    axes[1].axvline(f, color=color, linestyle='--', linewidth=1.5, alpha=0.8)
    axes[1].annotate(label, xy=(f, axes[1].get_ylim()[1]*0.9),
                     fontsize=9, color=color, fontweight='bold',
                     ha='center', va='top',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9))

plt.tight_layout()
plt.savefig(f'{out_dir}/01_fft_comparison_x.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ 图1: FFT频谱对比 (X轴)")


# ============================================================
# 图2：三轴峭度对比 — 松靴的核心特征
# ============================================================
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

axes_data = [
    ('X-axis', normal_x, fault_x),
    ('Y-axis', normal_y, fault_y),
    ('Z-axis', normal_z, fault_z),
]

for ax, (label, sig_n, sig_f) in zip(axes, axes_data):
    kurt_n = []
    kurt_f = []
    # 滑动窗口峭度
    win = 2000
    for i in range(0, min(len(sig_n), len(sig_f)) - win, win // 2):
        seg_n = sig_n[i:i+win]
        seg_f = sig_f[i:i+win]
        kurt_n.append(float(np.mean(((seg_n - np.mean(seg_n))/np.std(seg_n))**4) - 3) if np.std(seg_n) > 0 else 0)
        kurt_f.append(float(np.mean(((seg_f - np.mean(seg_f))/np.std(seg_f))**4) - 3) if np.std(seg_f) > 0 else 0)

    t = np.arange(len(kurt_n)) * (win / 2) / fs
    ax.plot(t, kurt_n, color='#2196F3', linewidth=1.5, label='Normal', alpha=0.8)
    ax.plot(t, kurt_f, color='#F44336', linewidth=1.5, label='Fault', alpha=0.8)
    ax.set_title(label, fontsize=14, fontweight='bold')
    ax.set_xlabel('Time (s)', fontsize=11)
    ax.set_ylabel('Kurtosis', fontsize=11)
    ax.legend(fontsize=10)
    ax.axhline(3, color='gray', linestyle=':', alpha=0.5, label='Gaussian (kurt=3)')

    # 高亮 Z 轴的峭度差异
    if label == 'Z-axis':
        ax.annotate(f'Fault kurtosis\nup to {max(kurt_f):.1f}',
                     xy=(t[np.argmax(kurt_f)], max(kurt_f)),
                     xytext=(t[np.argmax(kurt_f)]+1, max(kurt_f)*0.7),
                     fontsize=10, color='#F44336', fontweight='bold',
                     arrowprops=dict(arrowstyle='->', color='#F44336', lw=2))

plt.suptitle('Kurtosis Comparison (Normal vs Fault) — Z-axis is Key for Loose Slipper',
             fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(f'{out_dir}/02_kurtosis_3axis.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ 图2: 三轴峭度对比")


# ============================================================
# 图3：阶次谱对比（TOT，X轴）— 关键阶次高亮
# ============================================================
from order_tracking_extractor import tot_order_analysis

tacho_n = np.full(len(normal_x), f_rot)
tacho_f = np.full(len(fault_x), f_rot)
tot_n = tot_order_analysis(normal_x, fs, tachometer_signal=tacho_n, max_order=15)
tot_f = tot_order_analysis(fault_x, fs, tachometer_signal=tacho_f, max_order=15)

fig, ax = plt.subplots(figsize=(12, 5))

orders = np.arange(1, 16)
width = 0.35
bars_n = ax.bar(orders - width/2, tot_n['order_amplitudes'][:15], width,
                label='Normal', color='#2196F3', alpha=0.7)
bars_f = ax.bar(orders + width/2, tot_f['order_amplitudes'][:15], width,
                label='Fault', color='#F44336', alpha=0.7)

# 高亮关键阶次
highlight_orders = {1: '#4CAF50', 7: '#FF9800', 14: '#F44336'}
for order, color in highlight_orders.items():
    idx = order - 1
    ax.bar(order - width/2, tot_n['order_amplitudes'][idx], width,
           color=color, edgecolor='black', linewidth=2, alpha=0.9)
    ax.bar(order + width/2, tot_f['order_amplitudes'][idx], width,
           color=color, edgecolor='black', linewidth=2, alpha=0.9)
    ratio = tot_f['order_amplitudes'][idx] / max(tot_n['order_amplitudes'][idx], 1e-10)
    ax.annotate(f'{ratio:.1f}x',
                xy=(order, max(tot_n['order_amplitudes'][idx], tot_f['order_amplitudes'][idx])),
                xytext=(order, max(tot_n['order_amplitudes'][idx], tot_f['order_amplitudes'][idx]) * 1.3),
                fontsize=11, fontweight='bold', color=color, ha='center',
                arrowprops=dict(arrowstyle='->', color=color, lw=1.5))

ax.set_xlabel('Order', fontsize=12)
ax.set_ylabel('Amplitude', fontsize=12)
ax.set_title('Order Spectrum (TOT, X-axis) — Key Orders Highlighted', fontsize=14, fontweight='bold')
ax.set_xticks(orders)
ax.legend(fontsize=11)

# 添加阶次标签
labels = {1: '1X\n(f_r)', 7: '7X\n(f_p)', 14: '14X\n(2f_p)'}
for order, label in labels.items():
    ax.annotate(label, xy=(order, 0), xytext=(order, -ax.get_ylim()[1]*0.08),
                fontsize=9, ha='center', color='gray')

plt.tight_layout()
plt.savefig(f'{out_dir}/03_order_spectrum_tot.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ 图3: 阶次谱对比 (TOT)")


# ============================================================
# 图4：包络谱（高频带 6~7.5kHz）— f_p 高亮
# ============================================================
nyq = fs / 2
sos = butter(4, [6000/nyq, min(7500, nyq*0.95)/nyq], btype='band', output='sos')

env_n = np.abs(hilbert(sosfiltfilt(sos, normal_x)))
env_f = np.abs(hilbert(sosfiltfilt(sos, fault_x)))
env_n = env_n - np.mean(env_n)
env_f = env_f - np.mean(env_f)

freq_env_n, mag_env_n = fft_mag(env_n, fs)
freq_env_f, mag_env_f = fft_mag(env_f, fs)

fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

mask = freq_env_n <= 500
axes[0].plot(freq_env_n[mask], mag_env_n[mask], color='#2196F3', linewidth=0.8)
axes[0].set_title('Envelope Spectrum — Normal (X-axis, 6~7.5kHz band)', fontsize=13, fontweight='bold')
axes[0].set_ylabel('Amplitude', fontsize=11)

axes[1].plot(freq_env_f[mask], mag_env_f[mask], color='#F44336', linewidth=0.8)
axes[1].set_title('Envelope Spectrum — Fault (X-axis, 6~7.5kHz band)', fontsize=13, fontweight='bold')
axes[1].set_ylabel('Amplitude', fontsize=11)
axes[1].set_xlabel('Frequency (Hz)', fontsize=11)

# 高亮 f_p 和谐波
for ax in axes:
    for f, label, color in [(f_piston, 'f_p=172.67Hz', '#FF9800'),
                             (2*f_piston, '2f_p=345.33Hz', '#F44336')]:
        ax.axvline(f, color=color, linestyle='--', linewidth=1.5, alpha=0.8)
        ax.annotate(label, xy=(f, ax.get_ylim()[1]*0.85),
                    fontsize=9, color=color, fontweight='bold', ha='center',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.9))

# 标注 f_p 处幅值比
fp_idx_n = np.argmin(np.abs(freq_env_n - f_piston))
fp_idx_f = np.argmin(np.abs(freq_env_f - f_piston))
amp_n = np.max(mag_env_n[max(0,fp_idx_n-2):fp_idx_n+3])
amp_f = np.max(mag_env_f[max(0,fp_idx_f-2):fp_idx_f+3])
ratio = amp_f / amp_n if amp_n > 0 else 0

axes[1].annotate(f'f_p amplitude ratio: {ratio:.1f}x',
                 xy=(f_piston, amp_f), xytext=(f_piston+50, amp_f*0.8),
                 fontsize=11, color='#F44336', fontweight='bold',
                 arrowprops=dict(arrowstyle='->', color='#F44336', lw=2),
                 bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFF3E0', edgecolor='#FF9800'))

plt.tight_layout()
plt.savefig(f'{out_dir}/04_envelope_spectrum.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ 图4: 包络谱对比")


# ============================================================
# 图5：诊断结果汇总图
# ============================================================
fig, ax = plt.subplots(figsize=(12, 6))

# 三轴特征对比
categories = ['RMS Ratio', 'Kurtosis\nRatio', 'Crest Factor\nRatio', 'Peak\nRatio']
x = np.arange(len(categories))
width = 0.2

# 计算各轴比值
ratios_x = [
    np.sqrt(np.mean(fault_x**2)) / np.sqrt(np.mean(normal_x**2)),
    (np.mean(((fault_x - np.mean(fault_x))/np.std(fault_x))**4) - 3) / max(abs(np.mean(((normal_x - np.mean(normal_x))/np.std(normal_x))**4) - 3), 0.01),
    (np.max(np.abs(fault_x)) / np.sqrt(np.mean(fault_x**2))) / (np.max(np.abs(normal_x)) / np.sqrt(np.mean(normal_x**2))),
    np.max(np.abs(fault_x)) / np.max(np.abs(normal_x)),
]
ratios_y = [
    np.sqrt(np.mean(fault_y**2)) / np.sqrt(np.mean(normal_y**2)),
    (np.mean(((fault_y - np.mean(fault_y))/np.std(fault_y))**4) - 3) / max(abs(np.mean(((normal_y - np.mean(normal_y))/np.std(normal_y))**4) - 3), 0.01),
    (np.max(np.abs(fault_y)) / np.sqrt(np.mean(fault_y**2))) / (np.max(np.abs(normal_y)) / np.sqrt(np.mean(normal_y**2))),
    np.max(np.abs(fault_y)) / np.max(np.abs(normal_y)),
]
ratios_z = [
    np.sqrt(np.mean(fault_z**2)) / np.sqrt(np.mean(normal_z**2)),
    (np.mean(((fault_z - np.mean(fault_z))/np.std(fault_z))**4) - 3) / max(abs(np.mean(((normal_z - np.mean(normal_z))/np.std(normal_z))**4) - 3), 0.01),
    (np.max(np.abs(fault_z)) / np.sqrt(np.mean(fault_z**2))) / (np.max(np.abs(normal_z)) / np.sqrt(np.mean(normal_z**2))),
    np.max(np.abs(fault_z)) / np.max(np.abs(normal_z)),
]

bars_x = ax.bar(x - width, ratios_x, width, label='X-axis', color='#2196F3', alpha=0.8)
bars_y = ax.bar(x, ratios_y, width, label='Y-axis', color='#4CAF50', alpha=0.8)
bars_z = ax.bar(x + width, ratios_z, width, label='Z-axis', color='#F44336', alpha=0.8)

# 高亮 Z 轴峭度
ax.annotate('Z-axis kurtosis\n3.45x — KEY!',
            xy=(1 + width, ratios_z[1]),
            xytext=(1 + width + 0.8, ratios_z[1] * 0.8),
            fontsize=11, fontweight='bold', color='#F44336',
            arrowprops=dict(arrowstyle='->', color='#F44336', lw=2),
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFEBEE', edgecolor='#F44336'))

ax.axhline(1.0, color='gray', linestyle=':', alpha=0.5, label='No change')
ax.set_ylabel('Fault / Normal Ratio', fontsize=12)
ax.set_title('Three-Axis Feature Comparison (Real Data)', fontsize=14, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(categories, fontsize=11)
ax.legend(fontsize=11)
ax.set_ylim(0, max(max(ratios_x), max(ratios_y), max(ratios_z)) * 1.3)

plt.tight_layout()
plt.savefig(f'{out_dir}/05_three_axis_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
print("✅ 图5: 三轴特征对比")

print(f"\n所有图片已保存到 {out_dir}/")
