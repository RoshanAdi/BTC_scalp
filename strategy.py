import pandas as pd
import ta
from typing import Tuple, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class StrategyAnalyzer:
    """Analyzes trading signals based on the strategy"""
    
    @staticmethod
    def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI (Relative Strength Index)"""
        rsi_indicator = ta.momentum.RSIIndicator(close=data['close'], window=period)
        return rsi_indicator.rsi()
    
    @staticmethod
    def calculate_macd(data: pd.DataFrame) -> pd.DataFrame:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        macd_indicator = ta.trend.MACD(close=data['close'])
        return pd.DataFrame({
            'macd': macd_indicator.macd(),
            'macd_signal': macd_indicator.macd_signal(),
            'macd_diff': macd_indicator.macd_diff()
        })
    
    @staticmethod
    def is_bullish_candle(open_price: float, close_price: float) -> bool:
        """Check if candle is bullish (close > open)"""
        return close_price > open_price
    
    @staticmethod
    def analyze_signal(klines: list, threshold: int = 30) -> Dict[str, any]:
        """
        Analyze candles for entry signal
        
        Strategy Logic:
        1. Previous candle (N) must be BULLISH (close > open)
        2. Previous candle (N) RSI at close must be BELOW threshold
        3. Current candle (N+1) HIGH must PASS the HIGH of candle N
        4. If all conditions met -> ENTER TRADE
        
        Returns:
            {
                'should_enter': bool,
                'reason': str,
                'current_rsi': float,
                'candle_pattern': str
            }
        """
        result = {
            'should_enter': False,
            'reason': '',
            'current_rsi': None,
            'previous_rsi': None,
            'candle_pattern': None
        }
        
        if len(klines) < 3:
            result['reason'] = "Not enough candles"
            return result
        
        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # Convert to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        # Calculate RSI for all candles
        rsi = StrategyAnalyzer.calculate_rsi(df)
        current_rsi = rsi.iloc[-1]
        previous_rsi = rsi.iloc[-2]  # RSI at the close of previous candle (the bullish candle)
        
        result['current_rsi'] = current_rsi
        result['previous_rsi'] = previous_rsi
        
        # Get candles:
        # - previous_candle (N): The bullish candle that should have RSI below threshold
        # - current_candle (N+1): The candle that should pass the high of N
        current_candle = df.iloc[-1]
        previous_candle = df.iloc[-2]
        
        # Check conditions:
        # 1. Previous candle (N) is bullish (close > open)
        previous_is_bullish = StrategyAnalyzer.is_bullish_candle(
            previous_candle['open'], previous_candle['close']
        )
        
        # 2. Previous candle (N) RSI at close is below threshold
        previous_rsi_below_threshold = previous_rsi < threshold
        
        # 3. Current candle (N+1) high > previous candle (N) high
        current_high_passes_previous = current_candle['high'] > previous_candle['high']
        
        result['candle_pattern'] = {
            'previous_rsi': round(previous_rsi, 2) if not pd.isna(previous_rsi) else None,
            'current_rsi': round(current_rsi, 2) if not pd.isna(current_rsi) else None,
            'previous_rsi_below_threshold': previous_rsi_below_threshold,
            'previous_is_bullish': previous_is_bullish,
            'current_high_passes_previous': current_high_passes_previous,
            'previous_high': float(previous_candle['high']),
            'current_high': float(current_candle['high']),
            'previous_open': float(previous_candle['open']),
            'previous_close': float(previous_candle['close'])
        }
        
        # Entry condition: 
        # Previous candle is BULLISH with RSI < threshold
        # AND current candle's HIGH passes the previous candle's HIGH
        should_enter = (
            previous_is_bullish and 
            previous_rsi_below_threshold and 
            current_high_passes_previous
        )
        
        if should_enter:
            result['should_enter'] = True
            result['reason'] = f"Bullish candle with RSI {previous_rsi:.2f}<{threshold}, next candle passed high"
        else:
            reasons = []
            if not previous_is_bullish:
                reasons.append("Previous candle not bullish")
            if not previous_rsi_below_threshold:
                reasons.append(f"Previous candle RSI not below {threshold} (was: {previous_rsi:.2f})")
            if not current_high_passes_previous:
                reasons.append(f"Current high ({current_candle['high']:.2f}) didn't pass previous high ({previous_candle['high']:.2f})")
            result['reason'] = " | ".join(reasons)
        
        return result
    
    @staticmethod
    def calculate_exit_price(entry_price: float, profit_fraction: float = 0.005) -> float:
        """Calculate exit price based on profit target (fraction, e.g., 0.005 for 0.5%)"""
        return entry_price * (1 + profit_fraction)
    
    @staticmethod
    def check_exit_condition(current_price: float, trade: dict, 
                            profit_target: float) -> Tuple[bool, str]:
        """
        Check if current trade should be closed
        
        Returns:
            (should_exit, reason)
        """
        entry_price = trade['entry_price']
        target_price = StrategyAnalyzer.calculate_exit_price(entry_price, profit_target)
        
        if trade['position_type'] == 'LONG':
            should_exit = current_price >= target_price
            reason = f"Profit target reached: {current_price:.2f} >= {target_price:.2f}"
        else:
            should_exit = current_price <= target_price
            reason = f"Profit target reached: {current_price:.2f} <= {target_price:.2f}"
        
        return should_exit, reason
