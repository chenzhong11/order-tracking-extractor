"""改进版故障信号生成器 v2。

改进点：
1. 冲击信号加入时间抖动（模拟真实的非同步冲击）
2. 冲击幅度随机变化（模拟真实磨损的不均匀性）
3. 加入转速波动（模拟真实工况）
4. 高频共振用更宽的频带（不是单一频率）
5. 增加背景机械噪声（齿轮啮合等）

设备参数：7柱塞，1480 RPM，20kHz 采样，10s
函数版本: F-2.0.0
创建人: AI
编辑日期: 2026-07-22
"""

from __future__ import annotations

import numpy as np


# 设备参数
NUM_PISTONS = 7
SPEED_RPM = 1480.0
SAMPLING_RATE = 20000.0
DURATION = 10.0
F_ROTATION = SPEED_RPM / 60.0      # 24.67 Hz
F_PISTON = NUM_PISTONS * F_ROTATION  # 172.67 Hz


def generate_normal_v2(
    sampling_rate: float = SAMPLING_RATE,
    duration: float = DURATION,
    seed: int = 42,
) -> dict:
    """正常状态信号 v2：加入转速微波动和背景噪声。"""
    rng = np.random.default_rng(seed)
    n = int(sampling_rate * duration)
    t = np.arange(n) / sampling_rate

    # 转速微波动（±0.5% 的随机漂移，模拟真实工况）
    speed_variation = 1.0 + 0.005 * rng.standard_normal(n)
    inst_freq = F_ROTATION * speed_variation
    phase = 2 * np.pi * np.cumsum(inst_freq) / sampling_rate

    signal = np.zeros(n)

    # 转频谐波
    for order in range(1, 7):
        amp = 0.3 / order
        signal += amp * np.sin(order * phase + rng.uniform(0, 2*np.pi))

    # 柱塞通过频率谐波（用 7× 相位模拟）
    for order in range(1, 4):
        amp = 0.15 / order
        signal += amp * np.sin(order * NUM_PISTONS * phase + rng.uniform(0, 2*np.pi))

    # 背景机械噪声（模拟齿轮、轴承等宽频噪声）
    # 低频机械噪声
    for freq in [50, 100, 150, 250, 400]:
        amp = 0.02 * rng.uniform(0.5, 1.5)
        signal += amp * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2*np.pi))

    # 高频背景噪声（模拟传感器底噪）
    from scipy.signal import butter, filtfilt
    broadband_noise = 0.03 * rng.standard_normal(n)
    # 高通滤波模拟传感器特性
    b, a = butter(2, 100 / (sampling_rate/2), btype='high')
    broadband_noise = filtfilt(b, a, broadband_noise)
    signal += broadband_noise

    # 总体噪声
    signal += 0.04 * rng.standard_normal(n)

    return {
        "signal": signal,
        "time_axis": t,
        "sampling_rate": sampling_rate,
        "duration": duration,
        "label": "normal_v2",
        "description": "正常状态v2：转速微波动 + 背景机械噪声 + 传感器底噪",
    }


def generate_loose_slipper_v2(
    sampling_rate: float = SAMPLING_RATE,
    duration: float = DURATION,
    natural_freq: float = 8000.0,
    damping_ratio: float = 0.03,
    seed: int = 42,
) -> dict:
    """松靴故障信号 v2：加入冲击时间抖动和幅度随机性。

    改进点：
    - 冲击间隔有 ±5% 的时间抖动（模拟柱塞运动的不完全同步）
    - 冲击幅度有 ±30% 的随机变化（模拟不同柱塞的磨损程度不同）
    - 用多频率叠加模拟结构共振（不是单一 8kHz）
    - 加入转速微波动
    """
    rng = np.random.default_rng(seed)
    n = int(sampling_rate * duration)
    t = np.arange(n) / sampling_rate

    # 基底信号（与 normal_v2 相同）
    speed_variation = 1.0 + 0.005 * rng.standard_normal(n)
    inst_freq = F_ROTATION * speed_variation
    phase = 2 * np.pi * np.cumsum(inst_freq) / sampling_rate

    base = np.zeros(n)
    for order in range(1, 7):
        amp = 0.3 / order
        base += amp * np.sin(order * phase + rng.uniform(0, 2*np.pi))
    for order in range(1, 4):
        amp = 0.15 / order
        base += amp * np.sin(order * NUM_PISTONS * phase + rng.uniform(0, 2*np.pi))

    # 背景噪声
    for freq in [50, 100, 150, 250, 400]:
        amp = 0.02 * rng.uniform(0.5, 1.5)
        base += amp * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2*np.pi))

    # ---- 冲击序列（关键改进）----
    impact_interval = sampling_rate / F_PISTON  # 名义间隔 ≈ 115.8 个采样点

    # 生成冲击时刻（带时间抖动）
    impact_times = []
    current_time = 0
    while current_time < n:
        impact_times.append(int(current_time))
        # 下一个冲击：名义间隔 + ±5% 随机抖动
        jitter = impact_interval * rng.uniform(-0.05, 0.05)
        current_time += impact_interval + jitter

    # 冲击序列
    impacts = np.zeros(n)
    for idx in impact_times:
        if 0 <= idx < n:
            # 冲击幅度：基础值 × 随机变化（±30%）
            amp = rng.uniform(0.7, 1.3)
            impacts[idx] = amp

    # 结构固有频率响应（多频率叠加，更真实）
    # 主共振频率 + 次共振频率
    resonance_freqs = [natural_freq, natural_freq * 1.5, natural_freq * 0.7]
    resonance_amps = [1.0, 0.3, 0.2]

    resonance = np.zeros(n)
    for freq, amp in zip(resonance_freqs, resonance_amps):
        omega_n = 2 * np.pi * freq
        omega_d = omega_n * np.sqrt(1 - damping_ratio**2)
        tau = np.arange(0, 0.003, 1.0 / sampling_rate)  # 3ms 衰减窗口
        impulse_response = amp * np.exp(-damping_ratio * omega_n * tau) * np.sin(omega_d * tau)
        resonance += np.convolve(impacts, impulse_response, mode="full")[:n]

    # 合成
    signal = base + resonance + 0.04 * rng.standard_normal(n)

    return {
        "signal": signal,
        "time_axis": t,
        "sampling_rate": sampling_rate,
        "duration": duration,
        "label": "loose_slipper_v2",
        "description": "松靴v2：冲击时间抖动±5% + 幅度随机±30% + 多频率共振",
        "fault_params": {
            "impact_freq": F_PISTON,
            "natural_freq": natural_freq,
            "damping_ratio": damping_ratio,
            "timing_jitter": "±5%",
            "amplitude_variation": "±30%",
        },
    }


def generate_valve_plate_wear_v2(
    sampling_rate: float = SAMPLING_RATE,
    duration: float = DURATION,
    seed: int = 42,
) -> dict:
    """配流盘磨损信号 v2：加入转速波动和更真实的泄漏脉动。"""
    rng = np.random.default_rng(seed)
    n = int(sampling_rate * duration)
    t = np.arange(n) / sampling_rate

    # 转速波动
    speed_variation = 1.0 + 0.005 * rng.standard_normal(n)
    inst_freq = F_ROTATION * speed_variation
    phase = 2 * np.pi * np.cumsum(inst_freq) / sampling_rate

    signal = np.zeros(n)

    # 转频谐波：放大 3 倍
    for order in range(1, 7):
        amp = (0.3 / order) * 3.0
        signal += amp * np.sin(order * phase + rng.uniform(0, 2*np.pi))

    # 柱塞通过频率谐波：放大 3 倍
    for order in range(1, 4):
        amp = (0.15 / order) * 3.0
        signal += amp * np.sin(order * NUM_PISTONS * phase + rng.uniform(0, 2*np.pi))

    # 低频泄漏脉动（更宽的频带，模拟真实泄漏）
    for freq in [30, 60, 120, 200, 350, 500]:
        amp = 0.08 * rng.uniform(0.3, 1.7)
        signal += amp * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2*np.pi))

    # 背景噪声
    signal += 0.06 * rng.standard_normal(n)

    return {
        "signal": signal,
        "time_axis": t,
        "sampling_rate": sampling_rate,
        "duration": duration,
        "label": "valve_plate_wear_v2",
        "description": "配流盘磨损v2：谐波放大3倍 + 宽频泄漏脉动 + 转速波动",
    }


def generate_piston_wear_v2(
    sampling_rate: float = SAMPLING_RATE,
    duration: float = DURATION,
    seed: int = 42,
) -> dict:
    """柱塞磨损信号 v2。"""
    rng = np.random.default_rng(seed)
    n = int(sampling_rate * duration)
    t = np.arange(n) / sampling_rate

    speed_variation = 1.0 + 0.005 * rng.standard_normal(n)
    inst_freq = F_ROTATION * speed_variation
    phase = 2 * np.pi * np.cumsum(inst_freq) / sampling_rate

    signal = np.zeros(n)

    # 转频谐波：小幅放大
    for order in range(1, 7):
        amp = (0.3 / order) * 1.8
        signal += amp * np.sin(order * phase + rng.uniform(0, 2*np.pi))

    # 柱塞通过频率谐波：显著放大（主要特征）
    for order in range(1, 6):
        amp = (0.15 / order) * 2.5
        signal += amp * np.sin(order * NUM_PISTONS * phase + rng.uniform(0, 2*np.pi))

    # 泄漏脉动
    for freq in [80, 120, 200, 350, 500]:
        amp = 0.06 * rng.uniform(0.5, 1.5)
        signal += amp * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2*np.pi))

    signal += 0.05 * rng.standard_normal(n)

    return {
        "signal": signal,
        "time_axis": t,
        "sampling_rate": sampling_rate,
        "duration": duration,
        "label": "piston_wear_v2",
        "description": "柱塞磨损v2：柱塞频率谐波放大2.5倍 + 泄漏脉动",
    }


def main() -> None:
    import os

    output_dir = os.path.join(os.path.dirname(__file__), "synthetic_data_v2")
    os.makedirs(output_dir, exist_ok=True)

    signals = [
        generate_normal_v2(),
        generate_loose_slipper_v2(),
        generate_valve_plate_wear_v2(),
        generate_piston_wear_v2(),
    ]

    for data in signals:
        filepath = os.path.join(output_dir, f"{data['label']}.txt")
        np.savetxt(filepath, data["signal"], fmt="%.8f")
        rms = np.sqrt(np.mean(data["signal"]**2))
        peak = np.max(np.abs(data["signal"]))
        print(f"[{data['label']}] {data['description']}")
        print(f"  RMS={rms:.4f}, Peak={peak:.4f}, Points={len(data['signal'])}")
        print(f"  → {filepath}")

    print(f"\n设备: {NUM_PISTONS}柱塞, {SPEED_RPM} RPM, fs={SAMPLING_RATE} Hz")


if __name__ == "__main__":
    main()
