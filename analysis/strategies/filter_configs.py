"""
Filter Configurations
Different filter presets for different trading styles
"""

# STRICT - Professional/Conservative (High win rate, fewer trades)
STRICT_CONFIG = {
    'min_rr_ratio': 2.0,
    'atr_stop_multiplier': 1.5,
    'atr_target_multiplier': 3.0,
    'use_time_filter': True,
    'use_trend_filter': True,
    'use_volatility_filter': True,
    'use_rsi_filter': True,
    'use_volume_filter': True,
}

# MODERATE - Balanced (Good quality, more trades)
MODERATE_CONFIG = {
    'min_rr_ratio': 1.5,
    'atr_stop_multiplier': 1.2,
    'atr_target_multiplier': 2.0,
    'use_time_filter': True,
    'use_trend_filter': True,
    'use_volatility_filter': False,  # Relaxed
    'use_rsi_filter': True,
    'use_volume_filter': False,      # Relaxed
}

# RELAXED - More signals (Higher quantity, more filtering needed later)
RELAXED_CONFIG = {
    'min_rr_ratio': 1.0,
    'atr_stop_multiplier': 1.0,
    'atr_target_multiplier': 1.5,
    'use_time_filter': False,        # Trade anytime
    'use_trend_filter': False,       # Trade any direction
    'use_volatility_filter': False,
    'use_rsi_filter': False,
    'use_volume_filter': False,
}

# SCALPING - Quick trades
SCALPING_CONFIG = {
    'min_rr_ratio': 1.0,
    'atr_stop_multiplier': 0.5,
    'atr_target_multiplier': 0.75,
    'use_time_filter': True,
    'use_trend_filter': False,
    'use_volatility_filter': True,
    'use_rsi_filter': False,
    'use_volume_filter': True,
}

# SWING - Larger moves
SWING_CONFIG = {
    'min_rr_ratio': 2.5,
    'atr_stop_multiplier': 2.0,
    'atr_target_multiplier': 5.0,
    'use_time_filter': False,
    'use_trend_filter': True,
    'use_volatility_filter': True,
    'use_rsi_filter': True,
    'use_volume_filter': True,
}

def get_config(style: str = 'moderate') -> dict:
    """Get filter configuration by style name"""
    configs = {
        'strict': STRICT_CONFIG,
        'moderate': MODERATE_CONFIG,
        'relaxed': RELAXED_CONFIG,
        'scalping': SCALPING_CONFIG,
        'swing': SWING_CONFIG,
    }
    return configs.get(style.lower(), MODERATE_CONFIG)
