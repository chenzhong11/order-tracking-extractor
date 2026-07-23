"""阶次分析特征提取封装包 v7.22。

单文件集成版，所有算法在 core.py 中。
"""

from .core import (
    # 版本
    PACKAGE_VERSION, ALGORITHM_ID, ALGORITHM_VERSION, FEATURE_SCHEMA_VERSION,
    CREATOR, LAST_EDIT_DATE, get_version_info,
    # 配置
    OrderTrackingConfig, FaultBandConfig, FAULT_BAND_PRESETS,
    # 异常
    OrderTrackingError, ConfigError, SignalInputError, ComputationError,
    # 阶次分析
    OrderTrackingAnalyzer,
    run_order_tracking, cot_order_analysis, tot_order_analysis, vk_order_analysis,
    # 阈值标定
    calibrate_thresholds, check_diagnosis,
    calibrate_3sigma, check_3sigma,
    calibrate_percentile, check_percentile,
    calibrate_sliding_window, check_sliding_window,
    # 频带分析
    extract_fault_band_energy, diagnose_by_fault_type,
    # 信号处理
    compute_fft_spectrum, compute_stft, bandpass_filter,
    compute_envelope, compute_envelope_spectrum,
    # 阶次能量
    extract_order_energy, extract_order_energy_from_spectrum, sliding_window_segments,
    # 转速
    tachometer_to_speed,
    # 特征提取
    extract_features, extract_multi_axis_features, save_features, load_features,
    # 数据驱动诊断
    compute_feature_changes, match_fault_pattern,
    diagnose_by_sensitivity, diagnose_and_report,
    # 物理机理诊断
    FaultDiagnosticConfig, FAULT_DIAGNOSTICS,
    diagnose_single_fault, diagnose_all_faults,
    diagnose_by_fault_pattern,
)

__version__ = PACKAGE_VERSION
