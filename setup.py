#!/usr/bin/env python3
"""
Setup and test script for the trading bot
Run this to validate your setup before starting the bot
"""

import sys
import logging
from config import BINANCE_API_KEY, BINANCE_API_SECRET, SYMBOL, TIMEFRAME
from logger import setup_logging
from binance_api import BinanceAPI
from strategy import StrategyAnalyzer

logger = setup_logging("setup.log", "INFO")


def test_api_connection():
    """Test Binance API connection"""
    logger.info("\n" + "="*60)
    logger.info("Testing Binance API Connection")
    logger.info("="*60)
    
    if BINANCE_API_KEY == "your_api_key_here":
        logger.error("❌ API credentials not configured")
        logger.error("Please update config.py with your API key and secret")
        return False
    
    try:
        client = BinanceAPI(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=True)
        
        # Test getting price
        price = client.get_current_price(SYMBOL)
        if price:
            logger.info(f"✓ Successfully fetched price: {SYMBOL} = ${price:.2f}")
        else:
            logger.error("❌ Failed to fetch price")
            return False
        
        # Test getting klines
        klines = client.get_klines(SYMBOL, TIMEFRAME, limit=5)
        if klines:
            logger.info(f"✓ Successfully fetched {len(klines)} klines")
        else:
            logger.error("❌ Failed to fetch klines")
            return False
        
        # Test account info
        account = client.get_account_info()
        if account:
            logger.info(f"✓ Successfully fetched account info")
        else:
            logger.error("❌ Failed to fetch account info")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
        return False


def test_strategy():
    """Test strategy analysis"""
    logger.info("\n" + "="*60)
    logger.info("Testing Strategy Analysis")
    logger.info("="*60)
    
    try:
        client = BinanceAPI(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=True)
        
        klines = client.get_klines(SYMBOL, TIMEFRAME, limit=50)
        if not klines:
            logger.error("❌ Could not fetch klines for testing")
            return False
        
        signal = StrategyAnalyzer.analyze_signal(klines)
        logger.info(f"✓ Strategy analysis complete")
        logger.info(f"Current RSI: {signal['candle_pattern']['current_rsi']}")
        logger.info(f"Should enter: {signal['should_enter']}")
        logger.info(f"Reason: {signal['reason']}")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Strategy test failed: {e}")
        return False


def main():
    """Run all tests"""
    logger.info("Starting Trading Bot Setup & Validation")
    
    # Test 1: API Connection
    api_ok = test_api_connection()
    
    # Test 2: Strategy
    strategy_ok = test_strategy()
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("Setup Summary")
    logger.info("="*60)
    logger.info(f"API Connection: {'✓ OK' if api_ok else '❌ FAILED'}")
    logger.info(f"Strategy Analysis: {'✓ OK' if strategy_ok else '❌ FAILED'}")
    
    if api_ok and strategy_ok:
        logger.info("\n✓ All tests passed! Ready to run bot.py")
        return 0
    else:
        logger.error("\n❌ Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
