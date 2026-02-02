"""
Base Strategy Template
========================
Template for creating custom trading strategies.
"""
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum


class SignalType(Enum):
    """Trading signal direction"""
    BUY_CE = "BUY_CE"      # Buy Call Option
    BUY_PE = "BUY_PE"      # Buy Put Option
    SELL_CE = "SELL_CE"    # Sell Call Option
    SELL_PE = "SELL_PE"    # Sell Put Option
    EXIT = "EXIT"          # Exit position


@dataclass
class Signal:
    """Represents a trading signal"""
    timestamp: pd.Timestamp
    signal_type: SignalType
    strike: int
    entry_price: float
    stop_loss: float
    target: float
    reason: str
    strength: float = 1.0  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'signal_type': self.signal_type.value,
            'strike': self.strike,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'target': self.target,
            'reason': self.reason,
            'strength': self.strength,
        }


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """
    
    def __init__(self, name: str, config: Dict = None):
        self.name = name
        self.config = config or {}
        self.signals: List[Signal] = []
        self._configure()
    
    def _configure(self):
        """Override to set default configuration."""
        self.default_config = {
            'stop_loss_pct': 30,
            'target_pct': 50,
            'entry_time_start': '09:30',
            'entry_time_end': '14:30',
            'exit_time': '15:15',
        }
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
    
    @abstractmethod
    def generate_signals(self, 
                        index_df: pd.DataFrame, 
                        strikes_data: Dict[str, Dict[int, pd.DataFrame]],
                        symbol: str) -> List[Signal]:
        """Generate trading signals based on data."""
        raise NotImplementedError()
    
    def signals_to_dataframe(self) -> pd.DataFrame:
        """Convert signals to DataFrame."""
        if not self.signals:
            return pd.DataFrame()
        return pd.DataFrame([s.to_dict() for s in self.signals])
