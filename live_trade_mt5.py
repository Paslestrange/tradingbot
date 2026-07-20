from models.risk_supervisor import RiskSupervisor
import time
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from stable_baselines3 import PPO

from features.make_features import compute_features

# --- CONFIG ---
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
VOLUME = 0.01  # Minimum lot size
DEVIATION = 20
MODEL_PATH = "train/ppo_xauusd_latest.zip"
WINDOW = 64

# Mapping: 0=Flat, 1=Long
# (If we had Short, it would be mapped here too)

# --- RISK SUPERVISOR (module-level) ---
risk_supervisor = RiskSupervisor()
last_reset_date = None


def build_market_data(df):
    """Build real market_data dict for risk supervisor from live dataframe."""
    # Volatility: latest rolling std of log returns from features
    volatility = float(df['vol'].iloc[-1]) if 'vol' in df.columns else 0.0
    # Scale to comparable units with threshold (default 3.0)
    volatility_scaled = volatility * np.sqrt(252 * 24)  # annualized

    # Spread proxy: average (high - low) / close over last 5 candles
    recent = df.tail(5)
    spread = float(((recent['high'] - recent['low']) / recent['close']).mean())

    # DXY momentum proxy: if macro cols available use them, else 0
    dxy_momentum = 0.0
    if 'dxy_close' in df.columns:
        dxy_momentum = float(df['dxy_close'].pct_change(24).iloc[-1])

    return {
        'volatility': volatility_scaled,
        'spread': spread,
        'dxy_momentum': dxy_momentum,
        'is_high_impact_event': False,
        'is_event_window': False,
        'is_market_open': True,
    }


def maybe_reset_daily():
    """Call reset_daily once per UTC calendar day."""
    global last_reset_date
    today = datetime.utcnow().date()
    if last_reset_date is None or today != last_reset_date:
        risk_supervisor.reset_daily()
        last_reset_date = today


def get_market_data(symbol, n=500):
    """Fetch recent candles from MT5"""
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)
    if rates is None:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    return df

def execute_trade(action, current_pos_type):
    """
    Execute trade based on model action vs current position.
    action: 0 (Flat), 1 (Long)
    current_pos_type: 0 (Flat), 1 (Long)
    """
    
    # Logic:
    # If Action is LONG (1) and we are FLAT (0) -> BUY
    # If Action is FLAT (0) and we are LONG (1) -> CLOSE BUY
    # If Action == Current -> Do nothing
    
    if action == current_pos_type:
        return
    
    # Close existing position if any
    if current_pos_type == 1: # We are Long, need to Close
        print("🔻 Closing Long Position...")
        close_position(mt5.POSITION_TYPE_BUY)
        
    # Open new position
    if action == 1: # We want to be Long
        print("🟢 Opening Long Position...")
        open_order(mt5.ORDER_TYPE_BUY)

def open_order(order_type):
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": VOLUME,
        "type": order_type,
        "price": price,
        "deviation": DEVIATION,
        "magic": 234000,
        "comment": "RL_Agent_v1",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    print(f"Order Send Result: {result.comment if result else 'Failed'}")

def close_position(position_type):
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for pos in positions:
            if pos.type == position_type:
                tick = mt5.symbol_info_tick(SYMBOL)
                price = tick.bid if position_type == mt5.ORDER_TYPE_BUY else tick.ask
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL if position_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                    "position": pos.ticket,
                    "price": price,
                    "deviation": DEVIATION,
                    "magic": 234000,
                    "comment": "RL_Agent_Close",
                }
                mt5.order_send(request)

def get_current_position_type():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return 0 # Flat
    
    # Simplified: Assume only 1 position at a time for this magic number
    for pos in positions:
        if pos.magic == 234000:
            if pos.type == mt5.POSITION_TYPE_BUY:
                return 1
            # If we supported short, we'd check SELL here
            
    return 0

def main():
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        return

    print(f"✅ Connected to MT5: {mt5.terminal_info().name}")
    
    # Load Model
    model = PPO.load(MODEL_PATH)
    print(f"🧠 Model loaded: {MODEL_PATH}")

    # Initialize risk supervisor equity from account
        account_info = mt5.account_info()
        if account_info:
            risk_supervisor.current_equity = account_info.equity
            risk_supervisor.peak_equity = account_info.equity
            print(f"💰 Starting equity: ${account_info.equity:.2f}")

        print("🚀 Starting Live Trading Loop (Ctrl+C to stop)...")
    
        try:
            last_candle_time = None
            while True:
                # Daily reset check
                maybe_reset_daily()

                # 1. Get Data
                df = get_market_data(SYMBOL, n=200) # Fetch enough for MA(50) + Window(64)
                if df is None:
                    print("❌ Failed to fetch data, retrying...")
                    time.sleep(10)
                    continue

                # Check for new completed candle (prevent duplicate orders)
                # df.iloc[-1] is current forming candle, df.iloc[-2] is last completed
                if len(df) < 2:
                    print("⏳ Waiting for candle data...")
                    time.sleep(10)
                    continue

                current_candle_time = df.iloc[-2]['time']  # Last completed candle

                if last_candle_time is not None and current_candle_time == last_candle_time:
                    # No new candle completed, skip processing to prevent duplicate orders
                    time.sleep(10)
                    continue

                # New candle completed, process signal
                last_candle_time = current_candle_time

                # 2. Compute Features
                _, feats, _ = compute_features(df)

                # Get observation (last 64 steps)
                if len(feats) < WINDOW:
                    print("⏳ Not enough data yet...")
                    time.sleep(10)
                    continue

                obs_features = feats[-WINDOW:] # (64, F)

                # Get current position state for Observation
                current_pos = get_current_position_type()

                # Construct Observation: [features_flat, pos]
                obs = np.concatenate([obs_features.reshape(-1), np.array([current_pos], dtype=np.float32)])

                # 3. Predict Action
                action, _ = model.predict(obs, deterministic=True)
                action = int(action)

                print(f"⏰ {datetime.now().strftime('%H:%M:%S')} | Candle: {current_candle_time} | Pos: {current_pos} | Action: {action} ({'Long' if action==1 else 'Flat'})")
            # 4. Risk check with real market data
            market_data = build_market_data(df)
            state = {'position': current_pos, 'equity': risk_supervisor.current_equity}
            approved, reason = risk_supervisor.check_trade(action, state, market_data)
            if not approved:
                print(f"🚫 Trade rejected: {reason}")
                time.sleep(10)
                continue

            # 5. Execute trade
            prev_equity = risk_supervisor.current_equity
            execute_trade(action, current_pos)

            # 6. Update risk supervisor state after trade
            account_info = mt5.account_info()
            if account_info:
                new_equity = account_info.equity
                pnl = new_equity - prev_equity
                is_win = pnl > 0 if action != current_pos else None
                risk_supervisor.update_state(pnl, new_equity, is_win)
            
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n🛑 Stopping Agent...")
        mt5.shutdown()

if __name__ == "__main__":
    main()
