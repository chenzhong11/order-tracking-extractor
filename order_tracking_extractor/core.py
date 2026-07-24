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

PACKAGE_VERSION = "7.23"
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
    # ---- 冲击类：轴承故障 ----
    # 文献：[R3] 轴承外圈断裂故障试验；[R7][R12] Kurtogram+包络谱轴承诊断
    # BPFO/BPFI 需要轴承几何参数，此处用典型范围（4~8×f_r / 5~9×f_r）
    # 用户可替换为精确值
    "bearing_outer_race": FaultBandConfig(
        name="轴承外圈故障（冲击类）",
        low_freq_bands=(),
        high_freq_bands=((3000.0, 8000.0),),         # 轴承外圈固有频率共振带 [R7][R12]
        orders_of_interest=(4, 5, 6, 7, 8),          # BPFO ≈ 4~8×f_r 典型范围
        detection_method="envelope_spectrum_snr",    # 包络谱特征频率信噪比
    ),
    "bearing_inner_race": FaultBandConfig(
        name="轴承内圈故障（冲击类）",
        low_freq_bands=(),
        high_freq_bands=((3000.0, 8000.0),),         # 轴承内圈固有频率共振带 [R8]
        orders_of_interest=(5, 6, 7, 8, 9),          # BPFI ≈ 5~9×f_r 典型范围
        detection_method="envelope_spectrum_snr",    # 包络谱特征频率信噪比 + 转频边频验证
    ),
    # ---- 冲击类：气穴溃灭 ----
    # 文献：[R5] 空化检测与故障诊断；[R6] 空化振动噪声综述
    "cavitation": FaultBandConfig(
        name="气穴溃灭（冲击类·随机）",
        low_freq_bands=((10.0, 500.0),),             # 压力脉动低频段
        high_freq_bands=((2000.0, 8000.0),),         # 宽频冲击能量 [R5]
        orders_of_interest=(),                        # 无离散特征频率（随机冲击）
        detection_method="broadband_noise",           # 高频底噪抬升 + 无周期性
    ),
    # ---- 低频周期类：斜盘磨损 ----
    # 文献：[R4] 斜盘磨损振动特性；[R11] 斜盘局部缺陷动力学建模
    "swash_plate_mechanical": FaultBandConfig(
        name="斜盘磨损（低频周期力类）",
        low_freq_bands=((10.0, 250.0),),             # 转频谐波区 [R4]
        high_freq_bands=(),
        orders_of_interest=(1, 2, 3),                 # 1×f_r, 2×f_r, 3×f_r
        detection_method="order_amplitude",           # 转频谐波幅值
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

    elif method == "envelope_spectrum_snr":
        # 冲击类（轴承）：包络谱特征频率信噪比
        # 原理：在包络谱上定位特征频率，计算其幅值相对于背景噪声的信噪比
        # [R7] Kurtogram+包络谱轴承诊断；[R8] 包络谱+谱峭度联合诊断
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

            # 包络谱信噪比：特征频率幅值 / 包络谱中位数幅值
            # 这是方案第四阶段强调的核心指标
            env_snr = {}
            for band_key, (env_freqs, env_mags) in test_result.get("envelope_spectra", {}).items():
                if len(env_mags) == 0:
                    continue
                # 计算包络谱背景噪声水平（中位数）
                noise_level = float(np.median(env_mags))
                if noise_level < 1e-15:
                    noise_level = 1e-15
                # 找特征频率处的幅值（按 orders_of_interest 对应的频率）
                if rotational_freq is not None and fault_config.orders_of_interest:
                    peak_snrs = {}
                    for order in fault_config.orders_of_interest:
                        target_freq = order * rotational_freq
                        freq_mask = (env_freqs >= target_freq - 5) & (env_freqs <= target_freq + 5)
                        if np.any(freq_mask):
                            peak_amp = float(np.max(env_mags[freq_mask]))
                            peak_snrs[f"order_{order}_{target_freq:.0f}Hz"] = peak_amp / noise_level
                    env_snr[band_key] = peak_snrs
            diagnosis["details"]["envelope_spectrum_snr"] = env_snr

            diagnosis["is_fault"] = max_ratio > energy_ratio_threshold
            diagnosis["confidence"] = min(max_ratio / energy_ratio_threshold, 2.0)
        else:
            for band_key, val in test_result["high_band_energies"].items():
                diagnosis["details"][band_key] = val

    elif method == "broadband_noise":
        # 冲击类（气穴）：高频底噪整体抬升，无离散特征频率
        # 原理：气泡溃灭产生随机宽频冲击，无周期性，区别于松靴的 f_p 谐波
        # [R5] 空化检测；[R6] 空化振动噪声综述
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

            # 与松靴的区分：气穴无周期性
            # 检查包络谱中是否有突出的离散频率峰值
            has_discrete_peak = False
            for band_key, (env_freqs, env_mags) in test_result.get("envelope_spectra", {}).items():
                if len(env_mags) == 0:
                    continue
                median_amp = float(np.median(env_mags))
                max_amp = float(np.max(env_mags))
                # 如果最大幅值远超中位数，说明有突出的离散频率（非气穴）
                if median_amp > 0 and max_amp / median_amp > 5.0:
                    has_discrete_peak = True
            diagnosis["details"]["has_discrete_peak"] = has_discrete_peak
            # 气穴判定：高频底噪抬升 + 无突出离散频率
            diagnosis["is_fault"] = max_ratio > energy_ratio_threshold and not has_discrete_peak
            diagnosis["confidence"] = min(max_ratio / energy_ratio_threshold, 2.0) if diagnosis["is_fault"] else 0.0
        else:
            for band_key, val in test_result["high_band_energies"].items():
                diagnosis["details"][band_key] = val

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
# 5b. 故障特定频带特征
# ============================================================

def _fault_band_features(signal: np.ndarray, fs: float, config: dict) -> Dict[str, Any]:
    """按故障类型提取敏感频带能量。

    针对已归类的故障类型，从 FAULT_BAND_PRESETS 中读取频带配置，
    提取每个故障类型的关键频带能量，作为诊断特征集的补充。

    冲击类故障：高频共振带包络 RMS + 包络谱特征频率幅值
    磨损类故障：低频带 FFT 能量
    """
    from .core import FAULT_BAND_PRESETS

    signal = np.asarray(signal, dtype=float).reshape(-1)
    nyq = fs / 2
    f_r = config.get("speed_rpm", 1480) / 60
    f_p = f_r * config.get("n_pistons", 7)

    result = {}

    for fault_key, fault_config in FAULT_BAND_PRESETS.items():
        fault_result = {}

        # 低频带能量
        for (low, high) in fault_config.low_freq_bands:
            lo = max(low, 1.0) / nyq
            hi = min(high, nyq * 0.99) / nyq
            if lo >= hi:
                fault_result[f"low_{low:.0f}_{high:.0f}Hz"] = 0.0
                continue
            sos = butter(4, [lo, hi], btype="band", output="sos")
            filtered = sosfiltfilt(sos, signal)
            fault_result[f"low_{low:.0f}_{high:.0f}Hz"] = float(np.sqrt(np.mean(filtered ** 2)))

        # 高频共振带包络 RMS
        for (low, high) in fault_config.high_freq_bands:
            lo = max(low, 1.0) / nyq
            hi = min(high, nyq * 0.99) / nyq
            if lo >= hi:
                fault_result[f"env_{low:.0f}_{high:.0f}Hz"] = 0.0
                continue
            sos = butter(4, [lo, hi], btype="band", output="sos")
            filtered = sosfiltfilt(sos, signal)
            env = np.abs(hilbert(filtered))
            env = env - np.mean(env)
            fault_result[f"env_{low:.0f}_{high:.0f}Hz"] = float(np.sqrt(np.mean(env ** 2)))

            # 包络谱中特征频率幅值
            env_freqs, env_mags = compute_fft_spectrum(env, fs)
            for order in fault_config.orders_of_interest:
                target_f = order * f_r
                if target_f > fs / 2.56:
                    continue
                idx = np.argmin(np.abs(env_freqs - target_f))
                lo_idx = max(0, idx - 3)
                hi_idx = min(len(env_mags), idx + 4)
                peak_val = float(np.max(env_mags[lo_idx:hi_idx]))
                fault_result[f"env_peak_{order}x_fr"] = peak_val

        # 重点阶次幅值（从 FFT）
        if fault_config.orders_of_interest:
            freqs, mags = compute_fft_spectrum(signal, fs)
            for order in fault_config.orders_of_interest:
                target_f = order * f_r
                if target_f > fs / 2.56:
                    continue
                idx = np.argmin(np.abs(freqs - target_f))
                lo_idx = max(0, idx - 3)
                hi_idx = min(len(mags), idx + 4)
                fault_result[f"fft_peak_{order}x_fr"] = float(np.max(mags[lo_idx:hi_idx]))

        result[fault_key] = fault_result

    return result


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
        "fault_band_domain": _fault_band_features(signal, sampling_rate, config),
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





# ============================================================
# 基于特征变化率的数据驱动诊断
# ============================================================


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


# ============================================================
# 基于故障物理机理的分类诊断



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
    # 文献：[R4] 斜盘磨损振动特性；[R11] 斜盘局部缺陷动力学建模
    "swash_plate_wear": FaultDiagnosticConfig(
        name="斜盘磨损",
        mechanism="斜盘摩擦面磨损，柱塞运动不平稳，轴向力波动 [R4][R11]",
        primary_features=(
            ("axes.Z.order_domain.tot_key_orders.7x_fp", 1.3, "above"),
            ("axes.Z.time_domain.rms", 1.3, "above"),
        ),
        secondary_features=(
            ("axes.Z.freq_domain.band_energies.band_0_100Hz", 1.2, "above"),
        ),
        combination_logic="all",
    ),

    # ---- 轴承外圈故障 ----
    # 物理机理：外圈滚道点蚀 → 滚动体经过剥落坑产生冲击 → 激发外圈固有频率
    # 包络谱特征：BPFO 及其谐波，无转频边频 [R3][R7][R8][R12]
    "bearing_outer_race": FaultDiagnosticConfig(
        name="轴承外圈故障",
        mechanism="外圈滚道点蚀/剥落，滚动体经过剥落坑产生冲击，激发外圈固有频率 [R3][R7]",
        primary_features=(
            # 冲击类核心特征：峭度增大
            ("axes.Z.time_domain.kurtosis", 2.0, "above"),
            # 高频共振带能量增大
            ("axes.Z.impulse_domain.envelope_bands.6k_7_5kHz.rms", 1.5, "above"),
        ),
        secondary_features=(
            # 波峰因子增大（但弱于松靴）
            ("axes.Z.time_domain.crest_factor", 1.2, "above"),
            # 包络谱峰值频率应落在 BPFO 范围（需人工确认）
            ("axes.Z.impulse_domain.envelope_bands.6k_7_5kHz.peak_amp", 1.5, "above"),
        ),
        combination_logic="any",
    ),

    # ---- 轴承内圈故障 ----
    # 物理机理：内圈滚道点蚀 → 冲击频率 = BPFI，受转频调制
    # 包络谱特征：BPFI 及其谐波，每个谐波两侧有 ±f_r 边频 [R4][R8]
    "bearing_inner_race": FaultDiagnosticConfig(
        name="轴承内圈故障",
        mechanism="内圈滚道点蚀/剥落，冲击频率受转频调制，包络谱有转频边频 [R4][R8]",
        primary_features=(
            # 冲击类核心特征：峭度增大
            ("axes.Z.time_domain.kurtosis", 2.0, "above"),
            # 高频共振带能量增大
            ("axes.Z.impulse_domain.envelope_bands.6k_7_5kHz.rms", 1.5, "above"),
        ),
        secondary_features=(
            # 角域峭度（内圈随轴旋转，角域冲击更明显）
            ("axes.Z.impulse_domain.angle_domain_kurtosis", 1.5, "above"),
            # 包络谱峰值幅值
            ("axes.Z.impulse_domain.envelope_bands.6k_7_5kHz.peak_amp", 1.5, "above"),
        ),
        combination_logic="any",
    ),

    # ---- 气穴溃灭 ----
    # 物理机理：气泡溃灭产生随机宽频冲击，无明确特征频率 [R5][R6]
    # 与松靴的区别：气穴无周期性，松靴有 f_p 周期
    "cavitation": FaultDiagnosticConfig(
        name="气穴溃灭",
        mechanism="气泡溃灭产生随机宽频冲击，高频底噪抬升，无离散特征频率 [R5][R6]",
        primary_features=(
            # 高频底噪整体抬升（宽频激励）
            ("axes.Z.freq_domain.band_energies.band_4000_6000Hz", 1.5, "above"),
            # 谱熵增大（能量更分散，区别于松靴的集中冲击）
            ("axes.Z.freq_domain.spectral_entropy", 1.1, "above"),
        ),
        secondary_features=(
            # 峭度有增大但弱于松靴
            ("axes.Z.time_domain.kurtosis", 1.3, "above"),
            # 全频带 RMS 增大
            ("axes.Z.time_domain.rms", 1.2, "above"),
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


# ============================================================
# 统计阈值校准与模式切换诊断
# ============================================================

def calibrate_statistical_thresholds(
    normal_features_list: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """用多个正常样本计算每个特征的统计阈值。

    参数:
        normal_features_list: 正常样本的特征字典列表
            每个元素是 extract_multi_axis_features() 的输出

    返回: {"axes.X.time_domain.kurtosis": {"mean": 5.2, "std": 1.1, "3sigma": 8.5, "p95": 7.0, "n": 97}, ...}
    """
    # 展平所有样本的特征
    all_flat = [_flatten_features(f) for f in normal_features_list]

    # 收集所有特征路径
    all_paths = set()
    for f in all_flat:
        all_paths.update(f.keys())

    result = {}
    for path in sorted(all_paths):
        values = [f[path] for f in all_flat if path in f and not np.isnan(f[path])]
        if len(values) < 2:
            continue
        arr = np.array(values)
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        p95 = float(np.percentile(arr, 95))
        result[path] = {
            "mean": mean,
            "std": std,
            "3sigma": mean + 3 * std,
            "p95": p95,
            "n": len(values),
        }
    return result


def calibrate_from_signal(
    normal_signal: np.ndarray,
    sampling_rate: float = 20000.0,
    window_size: int = 2048,
    overlap_ratio: float = 0.5,
    config: Optional[dict] = None,
) -> Dict[str, Dict[str, float]]:
    """从单段正常信号中切分伪样本，计算统计阈值。

    用滑动窗口将长信号切成多段，每段提取特征，作为独立样本。
    """
    segments = sliding_window_segments(normal_signal, window_size, overlap_ratio)
    if len(segments) < 3:
        raise ValueError(f"信号太短，只能切出 {len(segments)} 段，至少需要 3 段")

    features_list = []
    for seg in segments:
        feat = extract_multi_axis_features({"X": seg}, sampling_rate, config)
        features_list.append(feat)

    return calibrate_statistical_thresholds(features_list)


def diagnose_single_fault_statistical(
    fault_features: Dict[str, Any],
    fault_config: FaultDiagnosticConfig,
    threshold_config: Dict[str, Dict[str, float]],
    mode: str = "3sigma",
) -> Dict[str, Any]:
    """用统计阈值诊断单种故障。

    参数:
        fault_features: 故障信号特征
        fault_config: 故障诊断配置
        threshold_config: calibrate_statistical_thresholds 的输出
        mode: "3sigma" 或 "p95"
    """
    thresh_key = mode  # "3sigma" 或 "p95"

    primary_results = []
    for feat_path, ratio_threshold, direction in fault_config.primary_features:
        fault_val = _get_feature_value(fault_features, feat_path)

        # 查找统计阈值
        stat = threshold_config.get(feat_path)
        if stat is not None:
            thresh = stat[thresh_key]
            if direction == "above":
                triggered = fault_val > thresh
            else:
                triggered = fault_val < thresh
            primary_results.append({
                "feature": feat_path,
                "fault_value": fault_val,
                "threshold": thresh,
                "threshold_mode": mode,
                "mean": stat["mean"],
                "std": stat["std"],
                "direction": direction,
                "triggered": triggered,
            })
        else:
            # 没有统计阈值，回退到固定比值
            primary_results.append({
                "feature": feat_path,
                "fault_value": fault_val,
                "threshold": ratio_threshold,
                "threshold_mode": "fallback_fixed",
                "direction": direction,
                "triggered": False,
            })

    secondary_results = []
    for feat_path, ratio_threshold, direction in fault_config.secondary_features:
        fault_val = _get_feature_value(fault_features, feat_path)
        stat = threshold_config.get(feat_path)
        if stat is not None:
            thresh = stat[thresh_key]
            if direction == "above":
                triggered = fault_val > thresh
            else:
                triggered = fault_val < thresh
            secondary_results.append({
                "feature": feat_path,
                "fault_value": fault_val,
                "threshold": thresh,
                "threshold_mode": mode,
                "mean": stat["mean"],
                "std": stat["std"],
                "direction": direction,
                "triggered": triggered,
            })
        else:
            secondary_results.append({
                "feature": feat_path,
                "fault_value": fault_val,
                "threshold": ratio_threshold,
                "threshold_mode": "fallback_fixed",
                "direction": direction,
                "triggered": False,
            })

    # 组合判定
    primary_triggered = [r["triggered"] for r in primary_results]
    if fault_config.combination_logic == "any":
        is_fault = any(primary_triggered)
    elif fault_config.combination_logic == "all":
        is_fault = all(primary_triggered)
    else:
        is_fault = any(primary_triggered)

    primary_count = sum(primary_triggered)
    total_primary = len(primary_results)
    confidence = (primary_count / total_primary) if total_primary > 0 else 0.0

    return {
        "fault_type": fault_config.name,
        "mechanism": fault_config.mechanism,
        "is_fault": is_fault,
        "confidence": round(confidence, 2),
        "primary_features": primary_results,
        "secondary_features": secondary_results,
        "primary_triggered_count": f"{primary_count}/{total_primary}",
        "threshold_mode": mode,
    }


def diagnose_by_fault_pattern_statistical(
    fault_features: Dict[str, Any],
    threshold_config: Dict[str, Dict[str, float]],
    mode: str = "3sigma",
) -> Dict[str, Any]:
    """用统计阈值遍历所有故障类型。"""
    all_results = []
    for fault_key, fault_config in FAULT_DIAGNOSTICS.items():
        result = diagnose_single_fault_statistical(
            fault_features, fault_config, threshold_config, mode
        )
        result["fault_key"] = fault_key
        all_results.append(result)

    triggered = [r for r in all_results if r["is_fault"]]
    if not triggered:
        conclusion = "未检测到已知故障模式"
        detected_faults = []
    elif len(triggered) == 1:
        conclusion = f"检测到: {triggered[0]['fault_type']}"
        detected_faults = [triggered[0]["fault_type"]]
    else:
        triggered.sort(key=lambda x: x["confidence"], reverse=True)
        conclusion = f"检测到多种可能故障，最可能是: {triggered[0]['fault_type']}"
        detected_faults = [t["fault_type"] for t in triggered]

    return {
        "conclusion": conclusion,
        "detected_faults": detected_faults,
        "all_results": all_results,
    }


def compare_threshold_modes(
    normal_signal: np.ndarray,
    fault_features: Dict[str, Any],
    normal_features: Dict[str, Any],
    sampling_rate: float = 20000.0,
) -> Dict[str, Any]:
    """对比三种阈值模式的诊断结果。

    返回: {"fixed": {...}, "3sigma": {...}, "p95": {...}}
    """
    # 模式 A：固定比值（原有方法）
    result_fixed = diagnose_by_fault_pattern(fault_features, normal_features)

    # 计算统计阈值
    thresh_config = calibrate_from_signal(normal_signal, sampling_rate)

    # 模式 B：3σ
    result_3sigma = diagnose_by_fault_pattern_statistical(
        fault_features, thresh_config, mode="3sigma"
    )

    # 模式 C：P95
    result_p95 = diagnose_by_fault_pattern_statistical(
        fault_features, thresh_config, mode="p95"
    )

    return {
        "fixed": result_fixed,
        "3sigma": result_3sigma,
        "p95": result_p95,
        "threshold_config": thresh_config,
    }
