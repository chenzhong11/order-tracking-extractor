"""阶次分析核心算法模块（单文件集成版）。

合并自：
- order_tracking_core.py（阶次分析核心算法）
- feature_extractor.py（多维度特征提取）
- sensitivity_diagnostics.py（基于特征变化率的数据驱动诊断）
- fault_diagnostics.py（基于故障物理机理的分类诊断）

版本: 7.22
日期: 2026-07-22
"""

from __future__ import annotations

# ============================================================
# 版本元数据
# ============================================================

PACKAGE_VERSION = "7.22"
ALGORITHM_ID = "order_tracking_v2"
ALGORITHM_VERSION = "A-7.22"
FEATURE_SCHEMA_VERSION = "2026.07"
CREATOR = "位豪"
LAST_EDIT_DATE = "2026-07-22"

def get_version_info() -> dict[str, str]:
    """返回版本信息字典，便于集成方记录算法来源。"""
    return {
        "package_version": PACKAGE_VERSION,
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "creator": CREATOR,
        "last_edit_date": LAST_EDIT_DATE,
    }


# ============================================================
# 核心阶次分析算法
# ============================================================


from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.interpolate import interp1d
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.signal import butter, sosfiltfilt, hilbert, stft as scipy_stft



# ============================================================
# 第一部分：异常定义
# ============================================================

class OrderTrackingError(Exception):
    """封装包异常基类，便于上层程序统一捕获本包抛出的错误。"""


class ConfigError(ValueError, OrderTrackingError):
    """配置参数非法时抛出。"""


class SignalInputError(ValueError, OrderTrackingError):
    """输入信号非法时抛出。"""


class ComputationError(RuntimeError, OrderTrackingError):
    """计算过程异常时抛出。"""


# ============================================================
# 第二部分：配置类
# ============================================================

@dataclass(frozen=True)
class OrderTrackingConfig:
    """阶次分析配置。

    Attributes:
        sampling_rate: 采样率 Hz
        max_order: 最大分析阶次
        method: 分析方法 ('cot' / 'tot' / 'fft')
        speed_unit: 转速单位 ('hz' / 'rad/s' / 'rpm')
        window_size: STFT 窗长
        overlap_ratio: STFT 重叠率
        nfft: STFT FFT 点数
        freq_search_range: COT 转频搜索范围 Hz
        segment_length: 标定分段长度
        calibration_overlap: 标定分段重叠率
        energy_bandwidth: 时域能量带宽 ±Hz
        percentile_value: 百分位数阈值
        min_fft_length: 最小 FFT 长度（零填充）
    """

    sampling_rate: float = 20000.0
    max_order: int = 15
    method: str = "cot"
    speed_unit: str = "hz"
    window_size: int = 1024
    overlap_ratio: float = 0.5
    nfft: int = 4096
    freq_search_range: Tuple[float, float] = (10.0, 100.0)
    segment_length: int = 2048
    calibration_overlap: float = 0.5
    energy_bandwidth: float = 10.0
    percentile_value: float = 95.0
    min_fft_length: int = 8192

    def validate(self) -> None:
        """校验配置参数。"""
        if self.sampling_rate <= 0:
            raise ConfigError("sampling_rate must be greater than 0.")
        if self.max_order <= 0:
            raise ConfigError("max_order must be greater than 0.")
        if self.method not in ("cot", "tot", "fft"):
            raise ConfigError("method must be 'cot', 'tot', or 'fft'.")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "sampling_rate": self.sampling_rate,
            "max_order": self.max_order,
            "method": self.method,
            "speed_unit": self.speed_unit,
            "window_size": self.window_size,
            "overlap_ratio": self.overlap_ratio,
            "nfft": self.nfft,
            "freq_search_range": self.freq_search_range,
            "segment_length": self.segment_length,
            "calibration_overlap": self.calibration_overlap,
            "energy_bandwidth": self.energy_bandwidth,
            "percentile_value": self.percentile_value,
            "min_fft_length": self.min_fft_length,
        }


# ============================================================
# 第三部分：信号处理基础函数
# ============================================================

def compute_fft_spectrum(
    signal_data: np.ndarray, sampling_rate: float
) -> Tuple[np.ndarray, np.ndarray]:
    """计算单边FFT频谱。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-02
    输入参数:
        signal_data，时域振动信号；
        sampling_rate，采样率 Hz。
    输出参数:
        freqs，频率轴 Hz；
        magnitudes，幅值谱（单边，已归一化）。
    """
    n = len(signal_data)
    fft_result = np.fft.rfft(signal_data)
    freqs = np.fft.rfftfreq(n, 1.0 / sampling_rate)
    magnitudes = np.abs(fft_result) / n * 2
    return freqs, magnitudes


def compute_stft(
    signal_data: np.ndarray,
    sampling_rate: float,
    window_size: int = 1024,
    overlap_ratio: float = 0.5,
    nfft: int = 4096,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """计算短时傅里叶变换（STFT），得到时频谱。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-02
    输入参数:
        signal_data，时域振动信号；
        sampling_rate，采样率 Hz；
        window_size，窗长（采样点数）；
        overlap_ratio，重叠率 0~1；
        nfft，FFT点数。
    输出参数:
        freqs，频率轴 Hz；
        times，时间轴 s；
        stft_magnitude，STFT幅值矩阵。
    """
    noverlap = int(window_size * overlap_ratio)
    freqs, times, Zxx = scipy_stft(
        signal_data, fs=sampling_rate,
        window="hann", nperseg=window_size,
        noverlap=noverlap, nfft=nfft,
    )
    stft_magnitude = np.abs(Zxx)
    return freqs, times, stft_magnitude


def bandpass_filter(
    signal_data: np.ndarray,
    sampling_rate: float,
    low_freq: float,
    high_freq: float,
    order: int = 4,
) -> np.ndarray:
    """带通滤波。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-02
    """
    nyquist = sampling_rate / 2
    low = low_freq / nyquist
    high = min(high_freq / nyquist, 0.99)
    sos = butter(order, [low, high], btype="band", output="sos")
    return sosfiltfilt(sos, signal_data)


def compute_envelope(
    signal_data: np.ndarray,
    sampling_rate: float,
    bandpass_range: Tuple[float, float] = (500.0, 5000.0),
) -> np.ndarray:
    """计算包络信号：带通滤波 + Hilbert变换。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-02
    """
    filtered = bandpass_filter(signal_data, sampling_rate, bandpass_range[0], bandpass_range[1])
    analytic_signal = hilbert(filtered)
    envelope = np.abs(analytic_signal)
    envelope = envelope - np.mean(envelope)
    return envelope


def compute_envelope_spectrum(
    signal_data: np.ndarray,
    sampling_rate: float,
    bandpass_range: Tuple[float, float] = (500.0, 5000.0),
) -> Tuple[np.ndarray, np.ndarray]:
    """计算包络谱：对包络信号做FFT。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-02
    """
    envelope = compute_envelope(signal_data, sampling_rate, bandpass_range)
    env_freqs, env_magnitudes = compute_fft_spectrum(envelope, sampling_rate)
    return env_freqs, env_magnitudes


# ============================================================
# 第四部分：阶次能量提取
# ============================================================

def sliding_window_segments(
    data: np.ndarray, segment_length: int, overlap_ratio: float = 0.5
) -> List[np.ndarray]:
    """滑动窗口分段。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    step = int(segment_length * (1 - overlap_ratio))
    if step < 1:
        step = 1
    segments = []
    start = 0
    while start + segment_length <= len(data):
        segments.append(data[start : start + segment_length])
        start += step
    return segments


def extract_order_energy(
    signal_data: np.ndarray,
    sampling_rate: float,
    rotational_freq: float,
    max_order: int = 15,
    bandwidth: float = 10.0,
) -> Dict[str, Any]:
    """提取各阶次的频带能量。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    freqs, magnitudes = compute_fft_spectrum(signal_data, sampling_rate)

    orders = np.arange(1, max_order + 1, dtype=float)
    order_energies = np.zeros(max_order)
    order_amplitudes = np.zeros(max_order)

    for i, order in enumerate(orders):
        center_freq = order * rotational_freq
        low = center_freq - bandwidth
        high = center_freq + bandwidth

        mask = (freqs >= low) & (freqs <= high)
        if np.any(mask):
            band_mags = magnitudes[mask]
            order_energies[i] = np.sum(band_mags ** 2)
            order_amplitudes[i] = np.max(band_mags)

    return {
        "orders": orders,
        "order_energies": order_energies,
        "order_amplitudes": order_amplitudes,
        "freqs": freqs,
        "magnitudes": magnitudes,
        "energy_bandwidth": bandwidth,
    }


def extract_order_energy_from_spectrum(
    freqs: np.ndarray,
    magnitudes: np.ndarray,
    rotational_freq: float,
    max_order: int = 15,
    bandwidth: float = 10.0,
) -> Dict[str, Any]:
    """从已有的频谱数据提取阶次能量。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    orders = np.arange(1, max_order + 1, dtype=float)
    order_energies = np.zeros(max_order)
    order_amplitudes = np.zeros(max_order)

    for i, order in enumerate(orders):
        center_freq = order * rotational_freq
        low = center_freq - bandwidth
        high = center_freq + bandwidth

        mask = (freqs >= low) & (freqs <= high)
        if np.any(mask):
            band_mags = magnitudes[mask]
            order_energies[i] = np.sum(band_mags ** 2)
            order_amplitudes[i] = np.max(band_mags)

    return {
        "orders": orders,
        "order_energies": order_energies,
        "order_amplitudes": order_amplitudes,
        "freqs": freqs,
        "magnitudes": magnitudes,
        "energy_bandwidth": bandwidth,
    }


# ============================================================
# 第五部分：阈值标定方法
# ============================================================

def calibrate_3sigma(feature_matrix: np.ndarray) -> Dict[str, Any]:
    """3σ准则阈值校准。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    mean = np.mean(feature_matrix, axis=0)
    std = np.std(feature_matrix, axis=0)
    threshold = mean + 3 * std
    return {
        "method": "3sigma",
        "mean": mean,
        "std": std,
        "threshold": threshold,
        "n_samples": len(feature_matrix),
    }


def check_3sigma(
    feature_vector: np.ndarray, threshold_config: Dict[str, Any]
) -> Dict[str, Any]:
    """检查特征向量是否超过3σ阈值。"""
    threshold = threshold_config["threshold"]
    ratios = feature_vector / threshold
    exceeded_indices = np.where(feature_vector > threshold)[0]
    return {
        "is_exceeded": len(exceeded_indices) > 0,
        "exceeded_indices": exceeded_indices,
        "ratios": ratios,
    }


def calibrate_percentile(
    feature_matrix: np.ndarray, percentile: float = 95
) -> Dict[str, Any]:
    """百分位数法阈值校准。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    threshold = np.percentile(feature_matrix, percentile, axis=0)
    return {
        "method": f"percentile_{percentile}",
        "percentile": percentile,
        "threshold": threshold,
        "n_samples": len(feature_matrix),
    }


def check_percentile(
    feature_vector: np.ndarray, threshold_config: Dict[str, Any]
) -> Dict[str, Any]:
    """检查特征向量是否超过百分位数阈值。"""
    threshold = threshold_config["threshold"]
    ratios = feature_vector / threshold
    exceeded_indices = np.where(feature_vector > threshold)[0]
    return {
        "is_exceeded": len(exceeded_indices) > 0,
        "exceeded_indices": exceeded_indices,
        "ratios": ratios,
    }


def calibrate_sliding_window(feature_matrix: np.ndarray) -> Dict[str, Any]:
    """滑动窗口法阈值校准。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-17
    """
    max_vals = np.max(feature_matrix, axis=0)
    mean_vals = np.mean(feature_matrix, axis=0)
    return {
        "method": "sliding_window",
        "threshold": max_vals,
        "max": max_vals,
        "mean": mean_vals,
        "n_samples": len(feature_matrix),
    }


def check_sliding_window(
    feature_vector: np.ndarray, threshold_config: Dict[str, Any]
) -> Dict[str, Any]:
    """检查特征向量是否超过滑动窗口阈值。"""
    threshold = threshold_config["threshold"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = np.where(threshold > 0, feature_vector / threshold, 0.0)
    exceeded_indices = np.where(feature_vector > threshold)[0]
    return {
        "is_exceeded": len(exceeded_indices) > 0,
        "exceeded_indices": exceeded_indices,
        "ratios": ratios,
    }


# ============================================================
# 第六部分：COT 算法
# ============================================================

def cot_order_analysis(
    signal_data: np.ndarray,
    sampling_rate: float,
    rotational_freq: Optional[float] = None,
    freq_search_range: Tuple[float, float] = (10.0, 100.0),
    max_order: int = 15,
    window_size: int = 1024,
    overlap_ratio: float = 0.5,
    nfft: int = 4096,
) -> Dict[str, Any]:
    """COT阶次分析主函数。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    cot_result: Dict[str, Any] = {"method": "COT"}

    if rotational_freq is not None:
        cot_result["rotational_freq"] = rotational_freq
        total_time = len(signal_data) / sampling_rate
        time_axis = np.linspace(0, total_time, len(signal_data))
        instantaneous_freq = np.full(len(signal_data), rotational_freq)
    else:
        time_axis, instantaneous_freq = _estimate_instantaneous_frequency(
            signal_data, sampling_rate, freq_search_range,
            window_size, overlap_ratio, nfft,
        )
        cot_result["rotational_freq"] = float(np.mean(instantaneous_freq))

    cot_result["time_axis"] = time_axis
    cot_result["instantaneous_freq"] = instantaneous_freq

    angle_curve = _compute_angle_curve(time_axis, instantaneous_freq)

    signal_time_axis = np.arange(len(signal_data)) / sampling_rate
    angle_curve_interp = np.interp(signal_time_axis, time_axis, angle_curve)

    angle_axis, resampled_signal = _resample_to_angle_domain(
        signal_data, signal_time_axis, angle_curve_interp
    )
    cot_result["angle_axis"] = angle_axis
    cot_result["resampled_signal"] = resampled_signal

    orders, order_amplitudes, order_axis, full_magnitudes = _compute_order_spectrum_cot(
        angle_axis, resampled_signal, max_order
    )
    cot_result["orders"] = orders
    cot_result["order_amplitudes"] = order_amplitudes
    cot_result["order_axis"] = order_axis
    cot_result["full_magnitudes"] = full_magnitudes

    return cot_result


def _estimate_instantaneous_frequency(
    signal_data: np.ndarray,
    sampling_rate: float,
    freq_search_range: Tuple[float, float],
    window_size: int,
    overlap_ratio: float,
    nfft: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """通过STFT脊线提取瞬时频率。"""
    freqs, times, stft_mag = compute_stft(
        signal_data, sampling_rate, window_size, overlap_ratio, nfft
    )
    freq_mask = (freqs >= freq_search_range[0]) & (freqs <= freq_search_range[1])
    freqs_in_range = freqs[freq_mask]
    stft_in_range = stft_mag[freq_mask, :]

    peak_indices = np.argmax(stft_in_range, axis=0)
    instantaneous_freq = freqs_in_range[peak_indices]

    instantaneous_freq = median_filter(instantaneous_freq, size=5)
    instantaneous_freq = uniform_filter1d(instantaneous_freq, size=10)

    return times, instantaneous_freq


def _compute_angle_curve(
    time_axis: np.ndarray, instantaneous_freq: np.ndarray
) -> np.ndarray:
    """从瞬时频率计算累积转角曲线。"""
    angular_velocity = 2 * np.pi * instantaneous_freq
    dt = np.diff(time_axis, prepend=time_axis[0])
    angle_curve = np.cumsum(angular_velocity * dt)
    return angle_curve


def _resample_to_angle_domain(
    signal_data: np.ndarray,
    time_axis: np.ndarray,
    angle_curve: np.ndarray,
    angular_resolution: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """等角度重采样。"""
    if angular_resolution is None:
        total_angle = angle_curve[-1]
        total_time = time_axis[-1]
        avg_freq = total_angle / (2 * np.pi * total_time) if total_time > 0 else 1
        samples_per_rev = int(20000 / avg_freq)
        angular_resolution = 2 * np.pi / max(samples_per_rev, 64)

    max_angle = angle_curve[-1]
    angle_axis = np.arange(0, max_angle, angular_resolution)

    interp_func = interp1d(
        angle_curve, time_axis, kind="linear", fill_value="extrapolate"
    )
    resampled_times = interp_func(angle_axis)

    signal_interp = interp1d(
        time_axis, signal_data, kind="linear", fill_value="extrapolate"
    )
    resampled_signal = signal_interp(resampled_times)

    return angle_axis, resampled_signal


def _compute_order_spectrum_cot(
    angle_axis: np.ndarray, resampled_signal: np.ndarray, max_order: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """对角域信号做FFT，得到阶次谱。"""
    n = len(resampled_signal)
    fft_result = np.fft.rfft(resampled_signal)
    delta_theta = angle_axis[1] - angle_axis[0] if len(angle_axis) > 1 else 1
    order_axis = np.fft.rfftfreq(n, d=delta_theta / (2 * np.pi))
    magnitudes = np.abs(fft_result) / n * 2

    orders = np.arange(1, max_order + 1, dtype=float)
    order_amplitudes = np.zeros(max_order)
    for i, order in enumerate(orders):
        idx = np.argmin(np.abs(order_axis - order))
        idx_start = max(0, idx - 2)
        idx_end = min(len(magnitudes), idx + 3)
        order_amplitudes[i] = np.max(magnitudes[idx_start:idx_end])

    return orders, order_amplitudes, order_axis, magnitudes


# ============================================================
# 第七部分：TOT 算法
# ============================================================

def _convert_speed_to_freq(speed_signal: np.ndarray, speed_unit: str) -> np.ndarray:
    """将转速信号统一转换为转频（Hz）。"""
    if speed_unit == "hz":
        return speed_signal
    elif speed_unit == "rad/s":
        return speed_signal / (2 * np.pi)
    elif speed_unit == "rpm":
        return speed_signal / 60.0
    else:
        raise ValueError(f"不支持的转速单位: {speed_unit}，支持 'hz', 'rad/s', 'rpm'")


def tot_order_analysis(
    signal_data: np.ndarray,
    sampling_rate: float,
    tachometer_signal: Optional[np.ndarray] = None,
    tachometer_rate: Optional[float] = None,
    speed_unit: str = "hz",
    rotational_freq: Optional[float] = None,
    max_order: int = 15,
) -> Dict[str, Any]:
    """TOT阶次分析主函数。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    tot_result: Dict[str, Any] = {"method": "TOT"}
    n = len(signal_data)
    total_time = n / sampling_rate
    time_axis = np.linspace(0, total_time, n)

    if tachometer_signal is not None:
        freq_signal = _convert_speed_to_freq(
            np.array(tachometer_signal, dtype=float), speed_unit
        )
        tac_rate = tachometer_rate if tachometer_rate else sampling_rate
        if tac_rate != sampling_rate or len(freq_signal) != n:
            tac_time = np.linspace(0, len(freq_signal) / tac_rate, len(freq_signal))
            interp_func = interp1d(
                tac_time, freq_signal, kind="linear", fill_value="extrapolate"
            )
            instantaneous_freq = interp_func(time_axis)
        else:
            instantaneous_freq = freq_signal
        tot_result["speed_source"] = "tachometer"

    elif rotational_freq is not None:
        freq_val = _convert_speed_to_freq(
            np.atleast_1d(float(rotational_freq)), speed_unit
        )[0]
        instantaneous_freq = np.full(n, freq_val)
        tot_result["speed_source"] = "constant"

    else:
        raise ValueError("必须提供 tachometer_signal 或 rotational_freq")

    tot_result["time_axis"] = time_axis
    tot_result["instantaneous_freq"] = instantaneous_freq
    tot_result["rotational_freq"] = float(np.mean(instantaneous_freq))

    angular_velocity = 2 * np.pi * instantaneous_freq
    dt = np.diff(time_axis, prepend=time_axis[0])
    angle_curve = np.cumsum(angular_velocity * dt)

    avg_freq = tot_result["rotational_freq"]
    samples_per_rev = int(sampling_rate / avg_freq) if avg_freq > 0 else 256
    angular_resolution = 2 * np.pi / max(samples_per_rev, 64)

    max_angle = angle_curve[-1]
    angle_axis = np.arange(0, max_angle, angular_resolution)

    interp_t = interp1d(
        angle_curve, time_axis, kind="linear", fill_value="extrapolate"
    )
    resampled_times = interp_t(angle_axis)

    interp_s = interp1d(
        time_axis, signal_data, kind="linear", fill_value="extrapolate"
    )
    resampled_signal = interp_s(resampled_times)

    tot_result["angle_axis"] = angle_axis
    tot_result["resampled_signal"] = resampled_signal

    fft_len = len(resampled_signal)
    fft_result = np.fft.rfft(resampled_signal)
    delta_theta = angle_axis[1] - angle_axis[0] if len(angle_axis) > 1 else 1
    order_axis = np.fft.rfftfreq(fft_len, d=delta_theta / (2 * np.pi))
    magnitudes = np.abs(fft_result) / fft_len * 2

    orders = np.arange(1, max_order + 1, dtype=float)
    order_amplitudes = np.zeros(max_order)
    for i, order in enumerate(orders):
        idx = np.argmin(np.abs(order_axis - order))
        idx_start = max(0, idx - 2)
        idx_end = min(len(magnitudes), idx + 3)
        order_amplitudes[i] = np.max(magnitudes[idx_start:idx_end])

    tot_result["orders"] = orders
    tot_result["order_amplitudes"] = order_amplitudes
    tot_result["order_axis"] = order_axis
    tot_result["full_magnitudes"] = magnitudes

    return tot_result


def tachometer_to_speed(
    tach_signal: np.ndarray,
    sampling_rate: float,
    pulses_per_rev: int = 360,
    threshold: Optional[float] = None,
) -> np.ndarray:
    """将转速脉冲信号转换为连续瞬时转频。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    signal = np.asarray(tach_signal, dtype=float)

    if threshold is None:
        threshold = (signal.min() + signal.max()) / 2.0

    binary = signal >= threshold
    rising_edges = np.where(np.diff(binary.astype(int)) == 1)[0]

    if len(rising_edges) < 2:
        return np.full(len(signal), 0.0)

    edge_times = rising_edges / sampling_rate
    periods = np.diff(edge_times)
    freq_at_edges = 1.0 / (periods * pulses_per_rev)

    mid_times = (edge_times[:-1] + edge_times[1:]) / 2.0
    time_axis = np.arange(len(signal)) / sampling_rate

    freq_ext = np.concatenate([[freq_at_edges[0]], freq_at_edges, [freq_at_edges[-1]]])
    time_ext = np.concatenate([[time_axis[0]], mid_times, [time_axis[-1]]])

    interp_func = interp1d(time_ext, freq_ext, kind="linear", fill_value="extrapolate")
    speed_hz = interp_func(time_axis)
    speed_hz = np.clip(speed_hz, 0.1, 200.0)

    return speed_hz


# ============================================================
# 第八部分：统一接口
# ============================================================

_MIN_FFT_LENGTH = 8192


def _compute_order_spectrum(
    angle_signal: np.ndarray, angle_axis: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """从角域信号计算阶次谱（统一方法）。"""
    n = len(angle_signal)
    delta_theta = angle_axis[1] - angle_axis[0] if len(angle_axis) > 1 else 1
    fft_len = max(n, _MIN_FFT_LENGTH)
    fft_result = np.fft.rfft(angle_signal, n=fft_len)
    order_axis = np.fft.rfftfreq(fft_len, d=delta_theta / (2 * np.pi))
    magnitudes = np.abs(fft_result) / n * 2
    return order_axis, magnitudes


def _extract_order_energies_from_angle(
    angle_signal: np.ndarray, angle_axis: np.ndarray, max_order: int
) -> np.ndarray:
    """从角域信号提取各阶次能量（统一方法）。"""
    order_axis, magnitudes = _compute_order_spectrum(angle_signal, angle_axis)
    result = extract_order_energy_from_spectrum(
        order_axis, magnitudes, rotational_freq=1.0, max_order=max_order, bandwidth=0.5
    )
    return result["order_energies"]


def _windowed_order_energies(
    angle_signal: np.ndarray,
    angle_axis: np.ndarray,
    max_order: int,
    segment_length: int = 2048,
    overlap_ratio: float = 0.5,
) -> np.ndarray:
    """窗口化提取阶次能量（与标定方法一致）。"""
    segments = sliding_window_segments(angle_signal, segment_length, overlap_ratio)
    if not segments:
        return _extract_order_energies_from_angle(angle_signal, angle_axis, max_order)

    all_energies = []
    for seg in segments:
        seg_angle_axis = angle_axis[: len(seg)] if angle_axis is not None else None
        seg_energies = _extract_order_energies_from_angle(seg, seg_angle_axis, max_order)
        all_energies.append(seg_energies)

    energy_matrix = np.array(all_energies)
    return np.max(energy_matrix, axis=0)


def run_order_tracking(
    vibration: np.ndarray,
    method: str,
    sampling_rate: float,
    speed: Optional[np.ndarray] = None,
    speed_unit: str = "rad/s",
    max_order: int = 15,
    bandwidth: float = 10.0,
) -> Dict[str, Any]:
    """阶次跟踪统一入口。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-17
    """
    if method == "tot":
        return _run_tot(vibration, speed, sampling_rate, speed_unit, max_order, bandwidth)
    elif method == "cot":
        return _run_cot(vibration, sampling_rate, max_order, bandwidth)
    else:
        raise ValueError(f"未知方法: {method}，支持 'cot' / 'tot'")


def _run_tot(
    vibration: np.ndarray,
    speed: Optional[np.ndarray],
    sampling_rate: float,
    speed_unit: str,
    max_order: int,
    bandwidth: float,
) -> Dict[str, Any]:
    """TOT 阶次跟踪。"""
    tot_result = tot_order_analysis(
        vibration, sampling_rate,
        tachometer_signal=speed, speed_unit=speed_unit, max_order=max_order,
    )

    angle_signal = tot_result.get("resampled_signal", None)
    angle_axis = tot_result.get("angle_axis", None)

    if angle_signal is not None and len(angle_signal) >= 2048:
        order_energies = _windowed_order_energies(angle_signal, angle_axis, max_order)
    else:
        order_energies = (
            _extract_order_energies_from_angle(angle_signal, angle_axis, max_order)
            if angle_signal is not None
            else np.zeros(max_order)
        )

    freq_axis, freq_magnitudes = compute_fft_spectrum(vibration, sampling_rate)

    return {
        "method": "TOT",
        "orders": tot_result["orders"],
        "order_amplitudes": tot_result["order_amplitudes"][:max_order],
        "order_energies": order_energies,
        "angle_axis": tot_result["angle_axis"],
        "resampled_signal": tot_result["resampled_signal"],
        "freq_axis": freq_axis,
        "freq_magnitudes": freq_magnitudes,
        "rotational_freq": tot_result.get("rotational_freq", 0),
    }


def _run_cot(
    vibration: np.ndarray, sampling_rate: float, max_order: int, bandwidth: float
) -> Dict[str, Any]:
    """COT 阶次跟踪。"""
    cot_result = cot_order_analysis(vibration, sampling_rate, max_order=max_order)

    angle_signal = cot_result.get("resampled_signal", None)
    angle_axis = cot_result.get("angle_axis", None)

    if angle_signal is not None and len(angle_signal) >= 2048:
        order_energies = _windowed_order_energies(angle_signal, angle_axis, max_order)
    else:
        order_energies = (
            _extract_order_energies_from_angle(angle_signal, angle_axis, max_order)
            if angle_signal is not None
            else np.zeros(max_order)
        )

    freq_axis, freq_magnitudes = compute_fft_spectrum(vibration, sampling_rate)

    return {
        "method": "COT",
        "orders": cot_result["orders"],
        "order_amplitudes": cot_result["order_amplitudes"][:max_order],
        "order_energies": order_energies,
        "angle_axis": cot_result["angle_axis"],
        "resampled_signal": cot_result["resampled_signal"],
        "freq_axis": freq_axis,
        "freq_magnitudes": freq_magnitudes,
        "rotational_freq": cot_result.get("rotational_freq", 0),
    }


# ============================================================
# 第九部分：阈值标定与诊断
# ============================================================

def _calibrate_with_tot(
    vibration: np.ndarray,
    tachometer_signal: np.ndarray,
    sampling_rate: float,
    tachometer_rate: Optional[float] = None,
    max_order: int = 15,
    segment_length: int = 2048,
    overlap_ratio: float = 0.5,
    bandwidth: float = 10.0,
) -> np.ndarray:
    """TOT 方式标定。"""
    tot_result = tot_order_analysis(
        vibration, sampling_rate,
        tachometer_signal=tachometer_signal,
        tachometer_rate=tachometer_rate,
        speed_unit="rad/s",
        max_order=max_order,
    )

    angle_signal = tot_result.get("resampled_signal", None)
    angle_axis = tot_result.get("angle_axis", None)

    if angle_signal is not None and len(angle_signal) >= segment_length:
        segments = sliding_window_segments(angle_signal, segment_length, overlap_ratio)
        energy_list = []
        for seg in segments:
            seg_angle_axis = angle_axis[: len(seg)] if angle_axis is not None else None
            seg_energies = _extract_order_energies_from_angle(seg, seg_angle_axis, max_order)
            energy_list.append(seg_energies)
        return np.array(energy_list)

    return np.array([tot_result["order_amplitudes"][:max_order]])


def _calibrate_with_cot(
    vibration: np.ndarray,
    sampling_rate: float,
    max_order: int,
    segment_length: int,
    overlap_ratio: float,
    bandwidth: float,
) -> np.ndarray:
    """COT 方式标定。"""
    cot_result = cot_order_analysis(vibration, sampling_rate, max_order=max_order)

    angle_signal = cot_result.get("resampled_signal", None)
    angle_axis = cot_result.get("angle_axis", None)

    if angle_signal is not None and len(angle_signal) >= segment_length:
        segments = sliding_window_segments(angle_signal, segment_length, overlap_ratio)
        energy_list = []
        for seg in segments:
            seg_angle_axis = angle_axis[: len(seg)] if angle_axis is not None else None
            seg_energies = _extract_order_energies_from_angle(seg, seg_angle_axis, max_order)
            energy_list.append(seg_energies)
        return np.array(energy_list)

    return np.array([cot_result["order_amplitudes"][:max_order]])


def _calibrate_with_fft(
    vibration: np.ndarray,
    sampling_rate: float,
    rotational_freq: float,
    max_order: int,
    segment_length: int,
    overlap_ratio: float,
    bandwidth: float,
) -> np.ndarray:
    """FFT 方式标定。"""
    segments = sliding_window_segments(vibration, segment_length, overlap_ratio)
    energy_list = []
    for seg in segments:
        freqs, mags = compute_fft_spectrum(seg, sampling_rate)
        energy_result = extract_order_energy_from_spectrum(
            freqs, mags, rotational_freq, max_order, bandwidth
        )
        energy_list.append(energy_result["order_energies"])
    return np.array(energy_list) if energy_list else np.array([])


def calibrate_thresholds(
    healthy_vibration: np.ndarray,
    method: str,
    sampling_rate: float,
    tachometer_signal: Optional[np.ndarray] = None,
    tachometer_rate: Optional[float] = None,
    rotational_freq: Optional[float] = None,
    max_order: int = 15,
    segment_length: int = 2048,
    overlap_ratio: float = 0.5,
    bandwidth: float = 10.0,
    percentile_value: float = 95,
) -> Dict[str, Any]:
    """用健康振动数据标定阶次能量阈值。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-17
    """
    if method == "tot":
        energy_matrix = _calibrate_with_tot(
            healthy_vibration, tachometer_signal, sampling_rate,
            tachometer_rate=tachometer_rate,
            max_order=max_order, segment_length=segment_length,
            overlap_ratio=overlap_ratio, bandwidth=bandwidth,
        )
    elif method == "cot":
        energy_matrix = _calibrate_with_cot(
            healthy_vibration, sampling_rate,
            max_order, segment_length, overlap_ratio, bandwidth,
        )
    elif method == "fft":
        energy_matrix = _calibrate_with_fft(
            healthy_vibration, sampling_rate, rotational_freq,
            max_order, segment_length, overlap_ratio, bandwidth,
        )
    else:
        raise ValueError(f"未知方法: {method}，支持 'cot' / 'tot' / 'fft'")

    if len(energy_matrix) == 0:
        raise ValueError("标定失败：未提取到有效能量分段，请检查输入数据长度")

    threshold_3sigma = calibrate_3sigma(energy_matrix)
    threshold_percentile = calibrate_percentile(energy_matrix, percentile_value)
    threshold_sliding_window = calibrate_sliding_window(energy_matrix)

    return {
        "method": method,
        "energy_matrix": energy_matrix,
        "threshold_3sigma": threshold_3sigma,
        "threshold_percentile": threshold_percentile,
        "threshold_sliding_window": threshold_sliding_window,
        "params": {
            "sampling_rate": sampling_rate,
            "max_order": max_order,
            "segment_length": segment_length,
            "overlap_ratio": overlap_ratio,
            "bandwidth": bandwidth,
            "percentile": percentile_value,
            "n_segments": len(energy_matrix),
        },
    }


def check_diagnosis(
    fault_order_energies: np.ndarray, calibration_result: Dict[str, Any]
) -> Dict[str, Any]:
    """用标定好的阈值对故障阶次能量做诊断。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-17
    """
    diag_3sigma = check_3sigma(fault_order_energies, calibration_result["threshold_3sigma"])
    diag_percentile = check_percentile(
        fault_order_energies, calibration_result["threshold_percentile"]
    )
    diag_sliding_window = check_sliding_window(
        fault_order_energies, calibration_result["threshold_sliding_window"]
    )

    return {
        "method": calibration_result["method"],
        "is_fault_3sigma": diag_3sigma["is_exceeded"],
        "is_fault_percentile": diag_percentile["is_exceeded"],
        "is_fault_sliding_window": diag_sliding_window["is_exceeded"],
        "exceeded_3sigma": diag_3sigma["exceeded_indices"],
        "exceeded_percentile": diag_percentile["exceeded_indices"],
        "exceeded_sliding_window": diag_sliding_window["exceeded_indices"],
        "ratios_3sigma": diag_3sigma["ratios"],
        "ratios_percentile": diag_percentile["ratios"],
        "ratios_sliding_window": diag_sliding_window["ratios"],
    }


# ============================================================
# 第十部分：Vold-Kalman 滤波
# ============================================================

def vk_order_analysis(
    signal_data: np.ndarray,
    sampling_rate: float,
    rotational_freq: Optional[float] = None,
    instantaneous_freq: Optional[np.ndarray] = None,
    max_order: int = 15,
    bandwidth_ratio: float = 0.3,
) -> Dict[str, Any]:
    """Vold-Kalman阶次分析主函数（带通滤波+Hilbert近似实现）。

    函数版本: F-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-09
    """
    vk_result: Dict[str, Any] = {"method": "VK"}
    n = len(signal_data)

    if instantaneous_freq is not None:
        inst_freq = instantaneous_freq
        if len(inst_freq) != n:
            t_old = np.linspace(0, 1, len(inst_freq))
            t_new = np.linspace(0, 1, n)
            inst_freq = interp1d(t_old, inst_freq, kind="linear")(t_new)
    elif rotational_freq is not None:
        inst_freq = np.full(n, rotational_freq)
    else:
        raise ValueError("必须提供 rotational_freq 或 instantaneous_freq")

    vk_result["instantaneous_freq"] = inst_freq
    vk_result["rotational_freq"] = float(np.mean(inst_freq))

    orders = np.arange(1, max_order + 1, dtype=float)
    order_amplitudes = np.zeros(max_order)
    order_envelopes: Dict[int, np.ndarray] = {}

    nyquist = sampling_rate / 2

    for i, order in enumerate(orders):
        center_freq = order * inst_freq
        avg_center = np.mean(center_freq)

        bw = avg_center * bandwidth_ratio
        low = max((avg_center - bw / 2) / nyquist, 0.01)
        high = min((avg_center + bw / 2) / nyquist, 0.99)

        if low >= high or high <= 0.01:
            order_amplitudes[i] = 0.0
            order_envelopes[int(order)] = np.zeros(n)
            continue

        filter_order = min(4, max(1, int(sampling_rate / avg_center / 2)))
        try:
            sos = butter(filter_order, [low, high], btype="band", output="sos")
            filtered = sosfiltfilt(sos, signal_data)
        except Exception:
            order_amplitudes[i] = 0.0
            order_envelopes[int(order)] = np.zeros(n)
            continue

        analytic = hilbert(filtered)
        envelope = np.abs(analytic)

        order_amplitudes[i] = np.mean(envelope)
        order_envelopes[int(order)] = envelope

    vk_result["orders"] = orders
    vk_result["order_amplitudes"] = order_amplitudes
    vk_result["order_envelopes"] = order_envelopes

    return vk_result


# ============================================================
# 第十一部分：基于故障机理的频带分析
# ============================================================

@dataclass(frozen=True)
class FaultBandConfig:
    """故障频带配置。

    按故障机理定义目标频带，取代逐阶次平铺的提取方式。

    Attributes:
        name: 故障类型名称
        low_freq_bands: 低频特征带列表 [(low, high), ...] Hz
        high_freq_bands: 高频共振带列表 [(low, high), ...] Hz
        orders_of_interest: 重点关注的阶次编号（1-based）
        detection_method: 检测方法
    """

    name: str
    low_freq_bands: Tuple[Tuple[float, float], ...] = ()
    high_freq_bands: Tuple[Tuple[float, float], ...] = ()
    orders_of_interest: Tuple[int, ...] = ()
    detection_method: str = "energy_ratio"


# 预置配置：7柱塞，1480 RPM (f_r=24.67Hz, f_p=172.67Hz)
# 注意：采样率 20kHz 时，实际可用频率上限 = 20000/2.56 ≈ 7.8kHz
# 高频共振带不能超过 7.5kHz，否则混叠
FAULT_BAND_PRESETS: Dict[str, FaultBandConfig] = {
    "loose_slipper": FaultBandConfig(
        name="松靴/滑靴磨损（冲击类）",
        low_freq_bands=((150.0, 550.0),),          # f_p 及谐波
        high_freq_bands=((6000.0, 7500.0),),        # 结构固有频率共振带（受采样率限制）
        orders_of_interest=(7, 14),                  # 1×f_p, 2×f_p
        detection_method="energy_ratio",             # 高频带能量/基线比值
    ),
    "valve_plate_wear": FaultBandConfig(
        name="配流盘磨损（低频周期力类）",
        low_freq_bands=((10.0, 250.0), (150.0, 700.0)),  # 转频谐波 + 柱塞频率带
        high_freq_bands=(),
        orders_of_interest=(1, 2, 3, 4, 5, 6, 7),   # 转频倍频 + 柱塞频率
        detection_method="order_amplitude",           # 阶次幅值超阈值
    ),
    "piston_wear": FaultBandConfig(
        name="柱塞-缸孔磨损（低频泄漏类）",
        low_freq_bands=((50.0, 500.0), (150.0, 900.0)),  # 泄漏脉动 + 柱塞频率带
        high_freq_bands=(),
        orders_of_interest=(7, 14, 21),               # 1×f_p, 2×f_p, 3×f_p
        detection_method="order_amplitude",            # 柱塞频率谐波幅值
    ),
    "uniform_wear": FaultBandConfig(
        name="均匀磨损（整体劣化）",
        low_freq_bands=((10.0, 10000.0),),           # 全频带
        high_freq_bands=(),
        orders_of_interest=(),
        detection_method="rms_trend",                 # RMS 趋势
    ),
}


def extract_fault_band_energy(
    signal_data: np.ndarray,
    sampling_rate: float,
    fault_config: FaultBandConfig,
    rotational_freq: Optional[float] = None,
    max_order: int = 15,
) -> Dict[str, Any]:
    """按故障类型提取目标频带能量。

    函数版本: F-1.0.0
    创建人: AI
    编辑日期: 2026-07-22

    与 extract_order_energy 的区别：
    - 不再逐阶次平铺，而是按故障机理分组
    - 冲击类故障：提取高频共振带的宽带 RMS
    - 周期力类故障：提取指定阶次的幅值
    - 返回值包含各频带能量和诊断指标

    参数:
        signal_data: 一维振动信号
        sampling_rate: 采样率 Hz
        fault_config: 故障频带配置
        rotational_freq: 转频 Hz（可选，用于阶次定位）
        max_order: 最大分析阶次

    返回: dict, 包含各频带能量、阶次幅值、诊断指标
    """
    signal_data = np.asarray(signal_data, dtype=float).reshape(-1)
    if signal_data.size == 0:
        raise SignalInputError("signal_data must not be empty.")

    nyquist = sampling_rate / 2
    result: Dict[str, Any] = {
        "fault_type": fault_config.name,
        "detection_method": fault_config.detection_method,
        "sampling_rate": sampling_rate,
    }

    # ---- 1. 低频特征带能量 ----
    low_band_energies: Dict[str, float] = {}
    for i, (low, high) in enumerate(fault_config.low_freq_bands):
        low_norm = max(low, 1.0) / nyquist
        high_norm = min(high, nyquist * 0.99) / nyquist
        if low_norm >= high_norm:
            low_band_energies[f"{low:.0f}-{high:.0f}Hz"] = 0.0
            continue
        sos = butter(4, [low_norm, high_norm], btype="band", output="sos")
        filtered = sosfiltfilt(sos, signal_data)
        rms_val = float(np.sqrt(np.mean(filtered ** 2)))
        low_band_energies[f"{low:.0f}-{high:.0f}Hz"] = rms_val
    result["low_band_energies"] = low_band_energies

    # ---- 2. 高频共振带能量 + 包络谱分析 ----
    # 共振解调：带通滤波 → Hilbert包络 → 包络谱
    # 包络谱中能反映冲击重复频率（如 f_p=172.67Hz）
    high_band_energies: Dict[str, float] = {}
    envelope_spectra: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for i, (low, high) in enumerate(fault_config.high_freq_bands):
        low_norm = max(low, 1.0) / nyquist
        high_norm = min(high, nyquist * 0.99) / nyquist
        if low_norm >= high_norm:
            high_band_energies[f"{low:.0f}-{high:.0f}Hz"] = 0.0
            continue
        sos = butter(4, [low_norm, high_norm], btype="band", output="sos")
        filtered = sosfiltfilt(sos, signal_data)
        # Hilbert 包络
        analytic = hilbert(filtered)
        envelope = np.abs(analytic)
        envelope = envelope - np.mean(envelope)
        # 包络 RMS
        rms_val = float(np.sqrt(np.mean(envelope ** 2)))
        high_band_energies[f"{low:.0f}-{high:.0f}Hz"] = rms_val
        # 包络谱：对包络做 FFT，看冲击重复频率
        env_freqs, env_mags = compute_fft_spectrum(envelope, sampling_rate)
        envelope_spectra[f"{low:.0f}-{high:.0f}Hz"] = (env_freqs, env_mags)
    result["high_band_energies"] = high_band_energies
    result["envelope_spectra"] = envelope_spectra

    # ---- 3. 重点阶次幅值 ----
    order_amplitudes: Dict[int, float] = {}
    if fault_config.orders_of_interest and rotational_freq is not None:
        freqs, magnitudes = compute_fft_spectrum(signal_data, sampling_rate)
        for order in fault_config.orders_of_interest:
            center = order * rotational_freq
            bw = 10.0  # ±10 Hz
            mask = (freqs >= center - bw) & (freqs <= center + bw)
            if np.any(mask):
                order_amplitudes[order] = float(np.max(magnitudes[mask]))
            else:
                order_amplitudes[order] = 0.0
    result["order_amplitudes_of_interest"] = order_amplitudes

    # ---- 4. 全频带 RMS ----
    result["overall_rms"] = float(np.sqrt(np.mean(signal_data ** 2)))

    return result


def diagnose_by_fault_type(
    test_signal: np.ndarray,
    sampling_rate: float,
    fault_config: FaultBandConfig,
    baseline_result: Optional[Dict[str, Any]] = None,
    rotational_freq: Optional[float] = None,
    energy_ratio_threshold: float = 2.0,
    order_amplitude_threshold: float = 3.0,
) -> Dict[str, Any]:
    """按故障类型诊断。

    函数版本: F-1.0.0
    创建人: AI
    编辑日期: 2026-07-22

    诊断逻辑：
    - energy_ratio（冲击类）: 高频共振带能量 / 基线能量 > 阈值 → 故障
    - order_amplitude（周期力类）: 重点阶次幅值 / 基线幅值 > 阈值 → 故障
    - rms_trend（均匀磨损）: 全频带 RMS / 基线 RMS > 阈值 → 故障

    参数:
        test_signal: 待诊断信号
        sampling_rate: 采样率
        fault_config: 故障频带配置
        baseline_result: 健康信号的 extract_fault_band_energy 结果（可选）
        rotational_freq: 转频 Hz
        energy_ratio_threshold: 能量比阈值（冲击类）
        order_amplitude_threshold: 阶次幅值比阈值（周期力类）

    返回: dict, 诊断结论
    """
    test_result = extract_fault_band_energy(
        test_signal, sampling_rate, fault_config,
        rotational_freq=rotational_freq,
    )

    diagnosis: Dict[str, Any] = {
        "fault_type": fault_config.name,
        "detection_method": fault_config.detection_method,
        "is_fault": False,
        "confidence": 0.0,
        "details": {},
    }

    method = fault_config.detection_method

    if method == "energy_ratio":
        # 冲击类：高频共振带能量比
        if baseline_result and baseline_result.get("high_band_energies"):
            ratios = {}
            max_ratio = 0.0
            for band_key, test_val in test_result["high_band_energies"].items():
                base_val = baseline_result["high_band_energies"].get(band_key, 1e-10)
                ratio = test_val / base_val if base_val > 0 else float("inf")
                ratios[band_key] = ratio
                max_ratio = max(max_ratio, ratio)
            diagnosis["details"]["high_band_ratios"] = ratios
            diagnosis["details"]["max_ratio"] = max_ratio
            diagnosis["is_fault"] = max_ratio > energy_ratio_threshold
            diagnosis["confidence"] = min(max_ratio / energy_ratio_threshold, 2.0)
        else:
            # 无基线时，用绝对能量判断（需经验阈值）
            for band_key, val in test_result["high_band_energies"].items():
                diagnosis["details"][band_key] = val

    elif method == "order_amplitude":
        # 周期力类：重点阶次幅值比
        if baseline_result and baseline_result.get("order_amplitudes_of_interest"):
            ratios = {}
            max_ratio = 0.0
            for order, test_val in test_result["order_amplitudes_of_interest"].items():
                base_val = baseline_result["order_amplitudes_of_interest"].get(order, 1e-10)
                ratio = test_val / base_val if base_val > 0 else float("inf")
                ratios[order] = ratio
                max_ratio = max(max_ratio, ratio)
            diagnosis["details"]["order_ratios"] = ratios
            diagnosis["details"]["max_ratio"] = max_ratio
            diagnosis["is_fault"] = max_ratio > order_amplitude_threshold
            diagnosis["confidence"] = min(max_ratio / order_amplitude_threshold, 2.0)
        else:
            for order, val in test_result["order_amplitudes_of_interest"].items():
                diagnosis["details"][f"order_{order}"] = val

    elif method == "rms_trend":
        # 均匀磨损：全频带 RMS 比
        if baseline_result:
            base_rms = baseline_result.get("overall_rms", 1e-10)
            ratio = test_result["overall_rms"] / base_rms if base_rms > 0 else float("inf")
            diagnosis["details"]["rms_ratio"] = ratio
            diagnosis["is_fault"] = ratio > energy_ratio_threshold
            diagnosis["confidence"] = min(ratio / energy_ratio_threshold, 2.0)
        else:
            diagnosis["details"]["overall_rms"] = test_result["overall_rms"]

    diagnosis["test_result"] = test_result
    return diagnosis


# ============================================================
# 第十二部分：高级封装类
# ============================================================

class OrderTrackingAnalyzer:
    """阶次分析器。

    函数版本: C-1.0.0
    创建人: 位豪
    编辑日期: 2026-06-29

    使用示例:
        config = OrderTrackingConfig(sampling_rate=20000, method='cot')
        analyzer = OrderTrackingAnalyzer(config)
        result = analyzer.analyze_cot(signal)
    """

    def __init__(self, config: Optional[OrderTrackingConfig] = None) -> None:
        if config is None:
            config = OrderTrackingConfig()
        config.validate()
        self._config = config

    @property
    def config(self) -> OrderTrackingConfig:
        """返回当前配置。"""
        return self._config

    def analyze_cot(self, signal: np.ndarray) -> Dict[str, Any]:
        """COT 阶次分析。

        输入参数: signal，一维振动信号数组。
        输出参数: 阶次分析结果字典。
        """
        signal = np.asarray(signal, dtype=float).reshape(-1)
        if signal.size == 0:
            raise SignalInputError("signal must not be empty.")
        return run_order_tracking(
            signal, "cot", self._config.sampling_rate, max_order=self._config.max_order,
        )

    def analyze_tot(
        self, signal: np.ndarray, tacho: np.ndarray
    ) -> Dict[str, Any]:
        """TOT 阶次分析。

        输入参数:
            signal，一维振动信号数组；
            tacho，一维转速信号数组。
        输出参数: 阶次分析结果字典。
        """
        signal = np.asarray(signal, dtype=float).reshape(-1)
        tacho = np.asarray(tacho, dtype=float).reshape(-1)
        if signal.size == 0:
            raise SignalInputError("signal must not be empty.")
        if tacho.size == 0:
            raise SignalInputError("tacho must not be empty.")
        return run_order_tracking(
            signal, "tot", self._config.sampling_rate,
            speed=tacho, speed_unit=self._config.speed_unit,
            max_order=self._config.max_order,
        )

    def calibrate_thresholds(
        self, healthy_signal: np.ndarray, **kwargs: Any
    ) -> Dict[str, Any]:
        """标定阈值。

        输入参数: healthy_signal，健康振动信号。
        输出参数: 标定结果字典。
        """
        healthy_signal = np.asarray(healthy_signal, dtype=float).reshape(-1)
        if healthy_signal.size == 0:
            raise SignalInputError("healthy_signal must not be empty.")
        return calibrate_thresholds(
            healthy_signal, self._config.method, self._config.sampling_rate,
            max_order=self._config.max_order,
            segment_length=self._config.segment_length,
            overlap_ratio=self._config.calibration_overlap,
            bandwidth=self._config.energy_bandwidth,
            percentile_value=self._config.percentile_value,
            **kwargs,
        )

    def diagnose(
        self, test_signal: np.ndarray, calibration_result: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        """诊断。

        输入参数:
            test_signal，待诊断振动信号；
            calibration_result，calibrate_thresholds 的返回值。
        输出参数: 诊断结果字典。
        """
        test_signal = np.asarray(test_signal, dtype=float).reshape(-1)
        if test_signal.size == 0:
            raise SignalInputError("test_signal must not be empty.")

        result = run_order_tracking(
            test_signal, self._config.method, self._config.sampling_rate,
            max_order=self._config.max_order,
        )
        return check_diagnosis(result["order_energies"], calibration_result)


# ============================================================
# 多维度特征提取器
# ============================================================


import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from scipy.signal import butter, sosfiltfilt, hilbert


# ============================================================
# 默认设备配置（7柱塞，1480 RPM，20kHz 采样）
# ============================================================

DEFAULT_CONFIG = {
    "sampling_rate": 20000.0,
    "n_pistons": 7,
    "speed_rpm": 1480.0,
    "max_order": 15,
}


# ============================================================
# 1. 时域统计特征
# ============================================================

def _time_features(signal: np.ndarray) -> Dict[str, float]:
    """时域统计特征：反映信号的整体形态。

    不针对任何特定故障，纯粹描述信号的统计特性。
    """
    rms = float(np.sqrt(np.mean(signal**2)))
    peak = float(np.max(np.abs(signal)))
    mean_val = float(np.mean(signal))
    std_val = float(np.std(signal))
    abs_mean = float(np.mean(np.abs(signal)))
    pp = float(np.max(signal) - np.min(signal))

    crest_factor = peak / rms if rms > 0 else 0.0
    impulse_factor = peak / abs_mean if abs_mean > 0 else 0.0

    # 峭度（超额峭度）：反映分布的"尖锐程度"
    kurtosis = float(np.mean(((signal - mean_val) / std_val)**4) - 3) if std_val > 0 else 0.0

    # 偏度：反映分布的不对称性
    skewness = float(np.mean(((signal - mean_val) / std_val)**3)) if std_val > 0 else 0.0

    # 裕度因子
    rms_abs = np.sqrt(np.mean(np.abs(signal)**2))
    clearance_factor = peak / (rms_abs**2) if rms_abs > 0 else 0.0

    # 方差、均方根频率
    variance = float(std_val**2)

    return {
        "rms": rms,
        "peak": peak,
        "peak_to_peak": pp,
        "mean": mean_val,
        "std": std_val,
        "variance": variance,
        "crest_factor": crest_factor,
        "impulse_factor": impulse_factor,
        "kurtosis": kurtosis,
        "skewness": skewness,
        "clearance_factor": clearance_factor,
    }


# ============================================================
# 2. 频域特征
# ============================================================

def _freq_features(signal: np.ndarray, fs: float) -> Dict[str, Any]:
    """频域特征：反映能量在频率上的分布。

    频带划分基于采样率的物理约束，不针对特定故障。
    """
    nyq = fs / 2
    n = len(signal)

    # FFT
    fft_result = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    magnitudes = np.abs(fft_result) / n * 2

    # 频谱统计量
    total_mag = np.sum(magnitudes)
    if total_mag > 0:
        spectral_centroid = float(np.sum(freqs * magnitudes) / total_mag)
        spectral_variance = float(np.sum(((freqs - spectral_centroid)**2) * magnitudes) / total_mag)
        spectral_spread = float(np.sqrt(spectral_variance))
        # 频谱熵
        p = magnitudes / total_mag
        p = p[p > 0]
        spectral_entropy = float(-np.sum(p * np.log2(p)))
    else:
        spectral_centroid = 0.0
        spectral_spread = 0.0
        spectral_entropy = 0.0

    # 频带 RMS（按频率均匀划分，覆盖 0 ~ Nyquist）
    # 不预设哪个频带有用，按物理约束等分
    band_edges = [0, 100, 250, 500, 1000, 2000, 4000, 6000, min(7500, nyq * 0.95)]
    band_energies = {}
    for i in range(len(band_edges) - 1):
        low = band_edges[i]
        high = band_edges[i + 1]
        name = f"band_{low}_{high}Hz"
        lo = max(low, 1.0) / nyq
        hi = min(high, nyq * 0.99) / nyq
        if lo >= hi:
            band_energies[name] = 0.0
            continue
        sos = butter(4, [lo, hi], btype="band", output="sos")
        filtered = sosfiltfilt(sos, signal)
        band_energies[name] = float(np.sqrt(np.mean(filtered**2)))

    # 总 RMS
    band_energies["total_rms"] = float(np.sqrt(np.mean(signal**2)))

    return {
        "band_energies": band_energies,
        "spectral_centroid": spectral_centroid,
        "spectral_spread": spectral_spread,
        "spectral_entropy": spectral_entropy,
    }


# ============================================================
# 3. 阶次域特征
# ============================================================

def _order_features(signal: np.ndarray, fs: float, config: dict) -> Dict[str, Any]:
    """阶次域特征：反映与转速同步的周期性成分。

    基于设备参数（柱塞数、转速）计算，不预设哪些阶次有用。
    """

    f_r = config["speed_rpm"] / 60.0
    max_order = config.get("max_order", 15)

    # COT 分析
    cot_result = cot_order_analysis(signal, fs, max_order=max_order)
    cot_amps = [float(x) for x in cot_result["order_amplitudes"]]

    # TOT 分析
    tacho = np.full(len(signal), f_r)
    tot_result = tot_order_analysis(signal, fs, tachometer_signal=tacho, max_order=max_order)
    tot_amps = [float(x) for x in tot_result["order_amplitudes"]]

    # 基于设备参数的重点阶次（柱塞通过频率及其谐波）
    n_pistons = config.get("n_pistons", 7)
    key_order_indices = {
        f"{n_pistons}x_fp": n_pistons,           # 柱塞通过频率
        f"{2*n_pistons}x_2fp": 2 * n_pistons,    # 2倍柱塞通过频率
        f"{3*n_pistons}x_3fp": 3 * n_pistons,    # 3倍柱塞通过频率
    }

    cot_key = {}
    tot_key = {}
    for name, idx in key_order_indices.items():
        if idx - 1 < len(cot_amps):
            cot_key[name] = cot_amps[idx - 1]
            tot_key[name] = tot_amps[idx - 1]

    # 阶次域统计量
    cot_mean = float(np.mean(cot_amps))
    cot_std = float(np.std(cot_amps))
    tot_mean = float(np.mean(tot_amps))
    tot_std = float(np.std(tot_amps))

    return {
        "cot_order_amplitudes": cot_amps,
        "tot_order_amplitudes": tot_amps,
        "cot_key_orders": cot_key,
        "tot_key_orders": tot_key,
        "cot_rotational_freq": float(cot_result["rotational_freq"]),
        "tot_rotational_freq": float(tot_result["rotational_freq"]),
        "cot_order_mean": cot_mean,
        "cot_order_std": cot_std,
        "tot_order_mean": tot_mean,
        "tot_order_std": tot_std,
    }


# ============================================================
# 4. 冲击域特征
# ============================================================

def _impulse_features(signal: np.ndarray, fs: float, config: dict) -> Dict[str, Any]:
    """冲击域特征：反映瞬态冲击和共振解调信息。

    包络谱分析覆盖多个频段（不只是 6~7.5kHz），不预设共振频率。
    角域冲击特征基于 TOT 路径提取。
    """

    f_r = config["speed_rpm"] / 60.0
    nyq = fs / 2

    # ---- 包络谱：多个频段的共振解调 ----
    # 按采样率可用范围等分，不预设哪个频段有用
    env_bands = [
        ("1k_2kHz", 1000, 2000),
        ("2k_4kHz", 2000, 4000),
        ("4k_6kHz", 4000, 6000),
        ("6k_7_5kHz", 6000, min(7500, nyq * 0.95)),
    ]

    envelope_results = {}
    for name, low, high in env_bands:
        lo = max(low, 1.0) / nyq
        hi = min(high, nyq * 0.99) / nyq
        if lo >= hi:
            envelope_results[name] = {"rms": 0.0, "peak_freq": 0.0, "peak_amp": 0.0}
            continue
        try:
            sos = butter(4, [lo, hi], btype="band", output="sos")
            filtered = sosfiltfilt(sos, signal)
            env = np.abs(hilbert(filtered))
            env = env - np.mean(env)
            env_rms = float(np.sqrt(np.mean(env**2)))

            env_fft = np.abs(np.fft.rfft(env)) / len(env) * 2
            env_freqs = np.fft.rfftfreq(len(env), 1.0 / fs)

            # 取包络谱中的峰值频率和幅值（0~500Hz 范围，反映冲击重复频率）
            mask = (env_freqs > 10) & (env_freqs < 500)
            if np.any(mask):
                peak_idx = np.argmax(env_fft[mask])
                peak_freq = float(env_freqs[mask][peak_idx])
                peak_amp = float(env_fft[mask][peak_idx])
            else:
                peak_freq = 0.0
                peak_amp = 0.0

            envelope_results[name] = {
                "rms": env_rms,
                "peak_freq": peak_freq,
                "peak_amp": peak_amp,
            }
        except Exception:
            envelope_results[name] = {"rms": 0.0, "peak_freq": 0.0, "peak_amp": 0.0}

    # ---- 角域冲击特征（TOT 路径）----
    tacho = np.full(len(signal), f_r)
    tot_result = tot_order_analysis(signal, fs, tachometer_signal=tacho, max_order=config.get("max_order", 15))
    ang_signal = tot_result.get("resampled_signal", signal)

    ang_rms = float(np.sqrt(np.mean(ang_signal**2)))
    ang_peak = float(np.max(np.abs(ang_signal)))
    ang_cf = ang_peak / ang_rms if ang_rms > 0 else 0.0
    ang_mean = float(np.mean(ang_signal))
    ang_std = float(np.std(ang_signal))
    ang_kurt = float(np.mean(((ang_signal - ang_mean) / ang_std)**4) - 3) if ang_std > 0 else 0.0
    ang_skew = float(np.mean(((ang_signal - ang_mean) / ang_std)**3)) if ang_std > 0 else 0.0

    return {
        "envelope_bands": envelope_results,
        "angle_domain_rms": ang_rms,
        "angle_domain_peak": ang_peak,
        "angle_domain_crest_factor": ang_cf,
        "angle_domain_kurtosis": ang_kurt,
        "angle_domain_skewness": ang_skew,
    }


# ============================================================
# 主提取函数
# ============================================================

def extract_features(
    signal: np.ndarray,
    sampling_rate: float = 20000.0,
    config: Optional[dict] = None,
    axis_label: str = "unknown",
) -> Dict[str, Any]:
    """提取单轴全部特征。

    设备驱动，全量输出，不预设故障场景。
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()

    signal = np.asarray(signal, dtype=float).reshape(-1)

    return {
        "meta": {
            "axis": axis_label,
            "sampling_rate": sampling_rate,
            "signal_length": len(signal),
            "duration": len(signal) / sampling_rate,
            "config": config,
        },
        "time_domain": _time_features(signal),
        "freq_domain": _freq_features(signal, sampling_rate),
        "order_domain": _order_features(signal, sampling_rate, config),
        "impulse_domain": _impulse_features(signal, sampling_rate, config),
    }


def extract_multi_axis_features(
    signals: Dict[str, np.ndarray],
    sampling_rate: float = 20000.0,
    config: Optional[dict] = None,
) -> Dict[str, Any]:
    """提取多轴特征 + 轴间关系。"""
    if config is None:
        config = DEFAULT_CONFIG.copy()

    axis_features = {}
    for axis, sig in signals.items():
        axis_features[axis] = extract_features(sig, sampling_rate, config, axis_label=axis)

    # 轴间关系（通用，不针对特定故障）
    cross_axis = {}
    axes = sorted(signals.keys())
    for i, a1 in enumerate(axes):
        for j, a2 in enumerate(axes):
            if i < j:
                rms1 = axis_features[a1]["time_domain"]["rms"]
                rms2 = axis_features[a2]["time_domain"]["rms"]
                cross_axis[f"rms_ratio_{a1}_{a2}"] = rms1 / rms2 if rms2 > 0 else float("inf")

                kurt1 = axis_features[a1]["time_domain"]["kurtosis"]
                kurt2 = axis_features[a2]["time_domain"]["kurtosis"]
                cross_axis[f"kurtosis_diff_{a1}_{a2}"] = kurt1 - kurt2

                peak1 = axis_features[a1]["time_domain"]["peak"]
                peak2 = axis_features[a2]["time_domain"]["peak"]
                cross_axis[f"peak_ratio_{a1}_{a2}"] = peak1 / peak2 if peak2 > 0 else float("inf")

    return {
        "axes": axis_features,
        "cross_axis": cross_axis,
    }


def save_features(features: Dict[str, Any], filepath: str) -> None:
    """保存特征到 JSON 文件。"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(features, f, indent=2, ensure_ascii=False)


def load_features(filepath: str) -> Dict[str, Any]:
    """从 JSON 文件加载特征。"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 基于特征变化率的数据驱动诊断
# ============================================================


import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ============================================================
# 特征路径遍历
# ============================================================

def _flatten_features(obj: Any, prefix: str = "") -> Dict[str, float]:
    """将嵌套的特征字典展平为 {路径: 值} 的形式。

    例如: {"time_domain": {"rms": 0.05}} → {"time_domain.rms": 0.05}
    """
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                flat.update(_flatten_features(v, new_key))
            elif isinstance(v, (int, float)):
                flat[new_key] = float(v)
            elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], (int, float)):
                # 列表型特征（如阶次幅值），展开为索引
                for i, val in enumerate(v):
                    flat[f"{new_key}[{i}]"] = float(val)
    return flat


def _is_meta_key(key: str) -> bool:
    """判断是否是元信息字段（不参与对比）。"""
    meta_prefixes = ["meta.", "axes.meta.", "order_domain.cot_rotational_freq",
                     "order_domain.tot_rotational_freq"]
    return any(key.startswith(p) or key == p.replace("axes.", "") for p in meta_prefixes)


# ============================================================
# 核心：特征变化率计算
# ============================================================

def compute_feature_changes(
    normal_features: Dict[str, Any],
    fault_features: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """计算每个特征的变化率，按变化幅度排序。

    返回: [{path, normal_value, fault_value, change_ratio, change_type}, ...]
    按 |change_ratio| 降序排列。
    """
    # 展平（只取单轴特征，取 X 轴作为主分析轴）
    normal_flat = {}
    fault_flat = {}

    # 多轴特征：展平每轴
    if "axes" in normal_features:
        for axis, axis_feat in normal_features["axes"].items():
            for k, v in _flatten_features(axis_feat).items():
                normal_flat[f"axes.{axis}.{k}"] = v
    if "axes" in fault_features:
        for axis, axis_feat in fault_features["axes"].items():
            for k, v in _flatten_features(axis_feat).items():
                fault_flat[f"axes.{axis}.{k}"] = v

    # 轴间关系
    if "cross_axis" in normal_features:
        for k, v in _flatten_features(normal_features["cross_axis"]).items():
            normal_flat[f"cross_axis.{k}"] = v
    if "cross_axis" in fault_features:
        for k, v in _flatten_features(fault_features["cross_axis"]).items():
            fault_flat[f"cross_axis.{k}"] = v

    # 计算变化率
    changes = []
    for key in normal_flat:
        if _is_meta_key(key):
            continue
        if key not in fault_flat:
            continue

        n_val = normal_flat[key]
        f_val = fault_flat[key]

        # 跳过无效值
        if np.isnan(n_val) or np.isnan(f_val):
            continue

        # 计算变化率
        if abs(n_val) > 1e-10:
            ratio = f_val / n_val
            change_type = "ratio"
        else:
            # 正常值接近 0，用绝对差值
            ratio = f_val - n_val
            change_type = "diff"

        changes.append({
            "path": key,
            "normal_value": round(n_val, 8),
            "fault_value": round(f_val, 8),
            "change_ratio": round(ratio, 4),
            "change_type": change_type,
            "abs_change": round(abs(ratio - 1) if change_type == "ratio" else abs(ratio), 4),
        })

    # 按变化幅度降序排列
    changes.sort(key=lambda x: x["abs_change"], reverse=True)
    return changes


# ============================================================
# 故障模式匹配
# ============================================================

# 已知故障模式的特征变化特征（基于物理机理 + 实测数据）
# 每个模式定义：哪些特征会变、变化方向、典型变化幅度
FAULT_PATTERNS = {
    "loose_slipper": {
        "name": "松靴/滑靴脱落",
        "mechanism": "柱塞球头松动，周期性撞击斜盘，冲击力激发结构共振",
        # 不绑定具体轴：找所有轴中变化最大的峭度
        # 物理本质：冲击类故障 → 峭度/波峰因子增大 → 包络谱能量增大
        "signature": [
            # 任意轴峭度增大（取所有轴的最大值）
            ("max_axis.kurtosis", "increase", 3.0),
            # 任意轴角域峭度增大
            ("max_axis.angle_domain_kurtosis", "increase", 2.0),
            # 包络谱能量增大（共振解调）
            ("max_axis.envelope_rms", "increase", 1.5),
            # 阶次能量也增大（冲击的调制效应）
            ("max_axis.order_mean", "increase", 1.5),
        ],
        "min_signature_matches": 2,
    },
    "valve_plate_wear": {
        "name": "配流盘磨损",
        "mechanism": "配流盘端面磨损，内泄漏增大，流量/压力脉动增大",
        # 物理本质：低频周期力 → 低频能量增大 → 阶次幅值均匀增大
        "signature": [
            ("max_axis.rms", "increase", 1.5),
            ("max_axis.order_mean", "increase", 1.5),
            ("max_axis.low_freq_energy", "increase", 1.5),
            # 高频不应显著增大（非冲击类）
            ("max_axis.high_freq_energy", "neutral", 0.5),
        ],
        "min_signature_matches": 2,
    },
    "piston_wear": {
        "name": "柱塞-缸孔磨损",
        "mechanism": "柱塞与缸孔间隙增大，内泄漏增大，流量脉动加剧",
        # 物理本质：柱塞频率谐波增大 + 泄漏脉动
        "signature": [
            ("max_axis.fp_amplitude", "increase", 1.5),
            ("max_axis.2fp_amplitude", "increase", 1.5),
            ("max_axis.mid_freq_energy", "increase", 1.3),
            ("max_axis.low_freq_energy", "increase", 1.3),
        ],
        "min_signature_matches": 2,
    },
}


# 通用特征名到实际路径后缀的映射
_FEATURE_MAP = {
    "kurtosis": "time_domain.kurtosis",
    "crest_factor": "time_domain.crest_factor",
    "rms": "time_domain.rms",
    "angle_domain_kurtosis": "impulse_domain.angle_domain_kurtosis",
    "envelope_rms": "impulse_domain.envelope_bands.6k_7_5kHz.rms",
    "order_mean": "order_domain.tot_order_mean",
    "low_freq_energy": "freq_domain.band_energies.band_100_250Hz",
    "high_freq_energy": "freq_domain.band_energies.band_4000_6000Hz",
    "mid_freq_energy": "freq_domain.band_energies.band_250_500Hz",
    "fp_amplitude": "order_domain.tot_key_orders.7x_fp",
    "2fp_amplitude": "order_domain.tot_key_orders.14x_2fp",
}


def _resolve_max_axis_feature(all_changes: List[Dict[str, Any]], feature_name: str) -> Optional[Dict[str, Any]]:
    """找所有轴中变化最大的特征。

    支持通用特征名（如 "kurtosis"）或完整后缀（如 "time_domain.kurtosis"）。
    自动在所有轴（X/Y/Z）中搜索，返回变化最大的那个。
    """
    # 先查映射表
    suffix = _FEATURE_MAP.get(feature_name, feature_name)
    target = "axes."
    full_suffix = f".{suffix}"
    candidates = [
        c for c in all_changes
        if c["path"].startswith(target) and c["path"].endswith(full_suffix)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x["abs_change"])


def match_fault_pattern(
    changes: List[Dict[str, Any]],
    pattern: Dict[str, Any],
) -> Dict[str, Any]:
    """将特征变化与已知故障模式匹配。

    支持 "max_axis.xxx" 路径：自动找所有轴中变化最大的。
    """
    change_dict = {c["path"]: c for c in changes}

    matched_features = []
    unmatched_features = []
    total_score = 0.0

    for feat_suffix, expected_direction, weight in pattern["signature"]:
        # 解析特征路径
        if feat_suffix.startswith("max_axis."):
            # 找所有轴中变化最大的
            suffix = feat_suffix[len("max_axis."):]
            change = _resolve_max_axis_feature(changes, suffix)
            if change is None:
                unmatched_features.append({"path": feat_suffix, "reason": "特征不存在"})
                continue
            actual_path = change["path"]
            ratio = change["change_ratio"]
        else:
            if feat_suffix not in change_dict:
                unmatched_features.append({"path": feat_suffix, "reason": "特征不存在"})
                continue
            change = change_dict[feat_suffix]
            actual_path = feat_suffix
            ratio = change["change_ratio"]

        # 判断变化方向是否符合预期
        if expected_direction == "increase":
            direction_match = ratio > 1.2
            actual_direction = "增大" if ratio > 1 else "减小"
        elif expected_direction == "decrease":
            direction_match = ratio < 0.8
            actual_direction = "减小" if ratio < 1 else "增大"
        else:  # neutral
            direction_match = 0.8 < ratio < 1.2
            actual_direction = "基本不变"

        if direction_match:
            score = weight * min(abs(ratio - 1) + 1, 3.0)
            total_score += score
            matched_features.append({
                "path": actual_path,
                "expected": expected_direction,
                "actual": actual_direction,
                "ratio": ratio,
                "score": round(score, 2),
            })
        else:
            unmatched_features.append({
                "path": actual_path,
                "expected": expected_direction,
                "actual": actual_direction,
                "ratio": ratio,
            })

    is_matched = len(matched_features) >= pattern["min_signature_matches"]

    return {
        "matched": is_matched,
        "score": round(total_score, 2),
        "matched_count": f"{len(matched_features)}/{len(pattern['signature'])}",
        "matched_features": matched_features,
        "unmatched_features": unmatched_features,
    }


# ============================================================
# 主诊断函数
# ============================================================

def diagnose_by_sensitivity(
    normal_features: Dict[str, Any],
    fault_features: Dict[str, Any],
    top_n: int = 10,
) -> Dict[str, Any]:
    """基于特征变化率的诊断。

    流程：
    1. 计算所有特征的变化率
    2. 排序，找出变化最大的 top_n 个特征
    3. 与已知故障模式匹配
    4. 输出诊断结论 + 敏感指标

    参数:
        normal_features: 正常信号的特征字典
        fault_features: 故障信号的特征字典
        top_n: 展示变化最大的前 N 个特征
    """
    # Step 1: 计算所有特征的变化率
    changes = compute_feature_changes(normal_features, fault_features)

    # Step 2: 取变化最大的 top_n
    top_changes = changes[:top_n]

    # Step 3: 与已知故障模式匹配
    pattern_results = []
    for pattern_key, pattern in FAULT_PATTERNS.items():
        result = match_fault_pattern(changes, pattern)
        result["fault_key"] = pattern_key
        result["fault_name"] = pattern["name"]
        result["mechanism"] = pattern["mechanism"]
        pattern_results.append(result)

    # 按得分排序
    pattern_results.sort(key=lambda x: x["score"], reverse=True)

    # Step 4: 生成结论
    detected = [p for p in pattern_results if p["matched"]]

    if not detected:
        conclusion = "未匹配到已知故障模式，可能是未知故障"
    elif len(detected) == 1:
        conclusion = f"匹配到: {detected[0]['fault_name']}（得分 {detected[0]['score']}）"
    else:
        conclusion = f"匹配到多种可能故障，最可能是: {detected[0]['fault_name']}（得分 {detected[0]['score']}）"

    return {
        "conclusion": conclusion,
        "detected_faults": [d["fault_name"] for d in detected],
        "top_sensitive_features": top_changes,
        "pattern_matching": pattern_results,
        "total_features_compared": len(changes),
    }


def diagnose_and_report(
    normal_features: Dict[str, Any],
    fault_features: Dict[str, Any],
    top_n: int = 10,
) -> str:
    """诊断并输出可读的报告文本。"""
    result = diagnose_by_sensitivity(normal_features, fault_features, top_n)

    lines = []
    lines.append("=" * 60)
    lines.append("  诊断报告（基于特征变化率）")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"结论: {result['conclusion']}")
    lines.append(f"对比特征总数: {result['total_features_compared']}")
    lines.append(f"检测到的故障: {result['detected_faults'] if result['detected_faults'] else '无'}")

    lines.append("")
    lines.append(f"--- 变化最大的 {len(result['top_sensitive_features'])} 个特征 ---")
    lines.append(f"{'排名':>4} | {'特征路径':>50} | {'正常值':>12} | {'故障值':>12} | {'变化率':>8} | {'方向':>6}")
    lines.append("-" * 100)

    for i, feat in enumerate(result["top_sensitive_features"]):
        ratio = feat["change_ratio"]
        if feat["change_type"] == "ratio":
            direction = "↑↑↑" if ratio > 2 else "↑↑" if ratio > 1.5 else "↑" if ratio > 1 else "↓" if ratio < 1 else "="
            ratio_str = f"{ratio:.2f}x"
        else:
            direction = "↑" if ratio > 0 else "↓"
            ratio_str = f"{ratio:+.4f}"

        lines.append(f"  {i+1:>2} | {feat['path']:>50} | {feat['normal_value']:>12.6f} | {feat['fault_value']:>12.6f} | {ratio_str:>8} | {direction}")

    lines.append("")
    lines.append("--- 故障模式匹配 ---")
    for p in result["pattern_matching"]:
        status = "✅ 匹配" if p["matched"] else "❌ 不匹配"
        lines.append(f"  {p['fault_name']}: {status} (得分={p['score']}, 匹配={p['matched_count']})")
        if p["matched_features"]:
            for mf in p["matched_features"]:
                lines.append(f"    ✅ {mf['path']}: {mf['actual']} ({mf['ratio']:.2f}x)")

    return "\n".join(lines)


# ============================================================
# 基于故障物理机理的分类诊断
# ============================================================


from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ============================================================
# 故障诊断配置
# ============================================================

@dataclass(frozen=True)
class FaultDiagnosticConfig:
    """单种故障的诊断配置。

    Attributes:
        name: 故障名称
        mechanism: 物理机理描述
        primary_features: 主判定特征列表 [(特征路径, 阈值, 方向), ...]
            特征路径格式: "axis.feature_group.feature_name"
            方向: "above" 表示故障时特征值增大, "below" 表示减小
        secondary_features: 辅助判定特征（用于提高置信度）
        combination_logic: 组合逻辑 "any"(任一超阈值) / "all"(全部超阈值) / "weighted"(加权)
    """

    name: str
    mechanism: str
    primary_features: Tuple[Tuple[str, float, str], ...]
    secondary_features: Tuple[Tuple[str, float, str], ...] = ()
    combination_logic: str = "any"


def _get_feature_value(features: dict, path: str) -> float:
    """从特征字典中按路径取值。

    支持两种格式：
    - 多轴特征: "axes.X.time_domain.kurtosis"
    - 轴间关系: "cross_axis.kurtosis_diff_X_Z"

    单轴兼容：当特征字典只有单轴数据时，axes.Y./axes.Z. 自动回退到存在的轴。
    """
    parts = path.split(".")
    obj = features
    for i, part in enumerate(parts):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        elif part == "axes" and isinstance(obj, dict) and "axes" in obj:
            obj = obj["axes"]
        elif (
            i == 1
            and part in ("Y", "Z")
            and isinstance(obj, dict)
            and part not in obj
        ):
            # 单轴数据：Y/Z 轴不存在时回退到存在的轴
            available = [k for k in obj.keys() if k in ("X", "Y", "Z")]
            if available:
                obj = obj[available[0]]
            else:
                return float("nan")
        else:
            return float("nan")
    return float(obj)


# ============================================================
# 故障诊断配置库（基于物理机理）
# ============================================================

FAULT_DIAGNOSTICS: Dict[str, FaultDiagnosticConfig] = {

    # ---- 松靴/滑靴脱落 ----
    # 物理机理：柱塞球头松动 → 每转一圈撞击斜盘一次 → 冲击力激发结构共振
    # 特征表现（基于真实数据）：
    #   - Z 轴峭度：6.30 → 21.71（比值 3.45x）
    #   - X 轴角域峭度：0.20 → 2.00（比值 9.86x）
    #   - X 轴 RMS：0.023 → 0.088（比值 3.82x）
    #   - X-Z 峭度差：-5.7 → -19.7（Z 轴峭度远高于 X）
    "loose_slipper": FaultDiagnosticConfig(
        name="松靴/滑靴脱落",
        mechanism="柱塞球头松动，周期性撞击斜盘，冲击力激发结构共振",
        primary_features=(
            # Z 轴峭度：松靴最显著的单一特征
            ("axes.Z.time_domain.kurtosis", 2.0, "above"),
            # X 轴角域峭度：TOT 路径的冲击特征
            ("axes.X.impulse_domain.angle_domain_kurtosis", 1.5, "above"),
        ),
        secondary_features=(
            # X 轴 RMS：冲击力导致整体振动增大
            ("axes.X.time_domain.rms", 1.5, "above"),
            # X-Z 峭度差：Z 轴峭度远高于 X 轴
            ("cross_axis.kurtosis_diff_X_Z", -3.0, "below"),
            # Z 轴波峰因子：冲击脉冲特征
            ("axes.Z.time_domain.crest_factor", 1.2, "above"),
        ),
        combination_logic="any",
    ),

    # ---- 配流盘磨损 ----
    # 物理机理：配流盘端面磨损 → 内泄漏 → 流量/压力脉动增大
    # 特征表现：
    #   - 低频带能量大幅增加（X 轴 10~250Hz：9.57x）
    #   - 阶次幅值均匀增大
    "valve_plate_wear": FaultDiagnosticConfig(
        name="配流盘磨损",
        mechanism="配流盘端面磨损，内泄漏增大，流量/压力脉动增大",
        primary_features=(
            ("axes.X.freq_domain.band_energies.band_0_100Hz", 2.0, "above"),
            ("axes.X.order_domain.tot_key_orders.7x_fp", 1.5, "above"),
        ),
        secondary_features=(
            ("axes.X.freq_domain.band_energies.band_100_250Hz", 1.5, "above"),
            ("axes.X.order_domain.tot_order_mean", 1.3, "above"),
        ),
        combination_logic="all",
    ),

    # ---- 柱塞-缸孔磨损 ----
    # 物理机理：间隙增大 → 内泄漏 → 流量脉动 → 柱塞频率谐波增大
    "piston_wear": FaultDiagnosticConfig(
        name="柱塞-缸孔磨损",
        mechanism="柱塞与缸孔间隙增大，内泄漏增大，流量脉动加剧",
        primary_features=(
            ("axes.X.order_domain.tot_key_orders.7x_fp", 1.5, "above"),
            ("axes.X.order_domain.tot_key_orders.14x_2fp", 1.5, "above"),
        ),
        secondary_features=(
            ("axes.X.freq_domain.band_energies.band_250_500Hz", 1.3, "above"),
            ("axes.X.freq_domain.band_energies.band_100_250Hz", 1.3, "above"),
        ),
        combination_logic="all",
    ),

    # ---- 斜盘磨损 ----
    # 物理机理：斜盘摩擦面磨损 → 柱塞运动不平稳 → 轴向力波动 → 转频谐波增大
    "swash_plate_wear": FaultDiagnosticConfig(
        name="斜盘磨损",
        mechanism="斜盘摩擦面磨损，柱塞运动不平稳，轴向力波动",
        primary_features=(
            ("axes.Z.order_domain.tot_key_orders.7x_fp", 1.3, "above"),
            ("axes.Z.time_domain.rms", 1.3, "above"),
        ),
        secondary_features=(
            ("axes.Z.freq_domain.band_energies.band_0_100Hz", 1.2, "above"),
        ),
        combination_logic="all",
    ),
}


# ============================================================
# 诊断函数
# ============================================================

def _compute_ratio(fault_val: float, normal_val: float) -> float:
    """计算比值，对同号负值特征（如峭度）做特殊处理。

    负值峭度的直接比值无物理意义（-0.06/-0.66=0.09 不代表“减弱”）。
    对于同号负值，用 1 + |变化量|/|基线| 作为比值，使其可与正阈值比较。
    """
    if np.isnan(fault_val) or np.isnan(normal_val) or abs(normal_val) < 1e-15:
        return 0.0
    if normal_val < 0 and fault_val < 0:
        # 同号负值：变化比例 + 1
        return 1.0 + abs(fault_val - normal_val) / abs(normal_val)
    if normal_val < 0 and fault_val >= 0:
        # 跨零：明确恶化
        return 1.0 + (abs(normal_val) + abs(fault_val)) / abs(normal_val)
    return fault_val / normal_val


def diagnose_single_fault(
    fault_features: Dict[str, Any],
    normal_features: Dict[str, Any],
    fault_config: FaultDiagnosticConfig,
) -> Dict[str, Any]:
    """用指定故障配置诊断特征字典。

    参数:
        fault_features: 故障信号的特征字典
        normal_features: 正常信号的特征字典（基线）
        fault_config: 故障诊断配置

    返回: 诊断结果，包含是否触发、各特征的判定详情、置信度
    """
    primary_results = []
    for feat_path, ratio_threshold, direction in fault_config.primary_features:
        fault_val = _get_feature_value(fault_features, feat_path)
        normal_val = _get_feature_value(normal_features, feat_path)

        ratio = _compute_ratio(fault_val, normal_val)
        if direction == "above":
            triggered = ratio > ratio_threshold
        else:  # below
            triggered = ratio < ratio_threshold
        primary_results.append({
            "feature": feat_path,
            "fault_value": fault_val,
            "normal_value": normal_val,
            "ratio": ratio,
            "threshold": ratio_threshold,
            "direction": direction,
            "triggered": triggered,
        })

    secondary_results = []
    for feat_path, ratio_threshold, direction in fault_config.secondary_features:
        fault_val = _get_feature_value(fault_features, feat_path)
        normal_val = _get_feature_value(normal_features, feat_path)

        ratio = _compute_ratio(fault_val, normal_val)
        if direction == "above":
            triggered = ratio > ratio_threshold
        else:
            triggered = ratio < ratio_threshold
        secondary_results.append({
            "feature": feat_path,
            "fault_value": fault_val,
            "normal_value": normal_val,
            "ratio": ratio,
            "threshold": ratio_threshold,
            "direction": direction,
            "triggered": triggered,
        })

    # 组合判定
    primary_triggered = [r["triggered"] for r in primary_results]
    secondary_triggered = [r["triggered"] for r in secondary_results]

    if fault_config.combination_logic == "any":
        is_fault = any(primary_triggered)
    elif fault_config.combination_logic == "all":
        is_fault = all(primary_triggered)
    else:
        is_fault = any(primary_triggered)

    # 置信度
    primary_count = sum(primary_triggered)
    total_primary = len(primary_results)
    primary_ratios = [abs(r["ratio"]) for r in primary_results if r["triggered"]]
    avg_ratio = np.mean(primary_ratios) if primary_ratios else 0.0

    confidence = 0.0
    if total_primary > 0:
        confidence = (primary_count / total_primary) * min(avg_ratio, 2.0)

    return {
        "fault_type": fault_config.name,
        "mechanism": fault_config.mechanism,
        "is_fault": is_fault,
        "confidence": round(confidence, 2),
        "primary_features": primary_results,
        "secondary_features": secondary_results,
        "primary_triggered_count": f"{primary_count}/{total_primary}",
    }


def diagnose_all_faults(
    fault_features: Dict[str, Any],
    normal_features: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """用所有故障配置诊断，返回每种故障的判定结果。"""
    results = []
    for fault_key, fault_config in FAULT_DIAGNOSTICS.items():
        result = diagnose_single_fault(fault_features, normal_features, fault_config)
        result["fault_key"] = fault_key
        results.append(result)
    return results


def diagnose_by_fault_pattern(
    fault_features: Dict[str, Any],
    normal_features: Dict[str, Any],
) -> Dict[str, Any]:
    """诊断入口：遍历所有故障类型，返回综合诊断结论。

    参数:
        fault_features: 待诊断信号的特征字典
        normal_features: 正常基线信号的特征字典
    """
    all_results = diagnose_all_faults(fault_features, normal_features)

    # 找出触发的故障
    triggered = [r for r in all_results if r["is_fault"]]

    if not triggered:
        conclusion = "未检测到已知故障模式"
        detected_faults = []
    elif len(triggered) == 1:
        conclusion = f"检测到: {triggered[0]['fault_type']}"
        detected_faults = [triggered[0]["fault_type"]]
    else:
        # 多个触发时，按置信度排序
        triggered.sort(key=lambda x: x["confidence"], reverse=True)
        conclusion = f"检测到多种可能故障，最可能是: {triggered[0]['fault_type']}"
        detected_faults = [t["fault_type"] for t in triggered]

    return {
        "conclusion": conclusion,
        "detected_faults": detected_faults,
        "all_results": all_results,
    }
