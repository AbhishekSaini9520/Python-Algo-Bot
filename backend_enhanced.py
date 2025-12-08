# """
# backend.py - Enhanced Trading Bot Backend with Signal Broadcasting
# Receives real trade data, signals, and historical trades from your bot
# """

# from flask import Flask, render_template, jsonify
# from flask_cors import CORS
# from flask_socketio import SocketIO, emit, disconnect
# import json
# import time
# import logging

# import requests
# from threading import Thread
# from datetime import datetime
# from collections import deque

# logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
# logger = logging.getLogger(__name__)

# app = Flask(__name__)
# CORS(app)
# socketio = SocketIO(app, cors_allowed_origins="*")

# # ✅ ENHANCED BOT STATE with signal tracking
# bot_state = {
#     "status": "LIVE",
#     "account_balance": 10000,
#     "floating_pnl": 0,
#     "open_positions": 0,
#     "total_trades": 0,
#     "winning_trades": 0,
#     "losing_trades": 0,
#     "win_rate": 0,
#     "profit_factor": 0,
#     "active_positions": [],
#     "recent_trades": deque(maxlen=100),  # Store last 100 trades
#     "trading_signals": deque(maxlen=50),  # Store last 50 signals
#     "config": {}
# }

# connected_clients = 0

# # ✅ API ENDPOINT: Receive Trading Signals (Bullish hammer, Bearish hammer, etc)

# @app.route('/api/signal', methods=['POST'])
# def receive_signal():
#     """
#     Receive real-time trading signals from bot
#     Examples:
#     - "🟢 Bullish Hammer Detected | BTC_USD | M5"
#     - "🔴 Bearish Hammer Detected | XAU_USD | M15"
#     - "⏳ Candle Completed | BTC_USD | M5 | Close: 42150.25"
#     """
#     from flask import request
#     try:
#         data = request.get_json()
#         signal_type = data.get('type')  # 'bullish', 'bearish', 'candle_complete', 'pattern_alert'
#         message = data.get('message')
#         instrument = data.get('instrument')
#         timeframe = data.get('timeframe')
        
#         signal_event = {
#             "type": signal_type,
#             "message": message,
#             "instrument": instrument,
#             "timeframe": timeframe,
#             "timestamp": datetime.now().strftime("%H:%M:%S"),
#             "timestamp_ms": time.time()
#         }
        
#         # Add to signals queue
#         bot_state["trading_signals"].append(signal_event)
        
#         logger.info(f"📊 Signal received: {signal_type} | {instrument} | {timeframe}")
        
#         # Broadcast to all dashboards
#         socketio.emit('trading_signal', signal_event, to=None)
#         socketio.emit('bot_update', {
#             "signals": list(bot_state["trading_signals"]),
#             "status": bot_state["status"]
#         }, to=None)
        
#         return jsonify({"status": "success"}), 200
    
#     except Exception as e:
#         logger.error(f"❌ Error processing signal: {e}")
#         return jsonify({"status": "error", "message": str(e)}), 500


# # ✅ API ENDPOINT: Receive New Trade

# @app.route('/api/trade', methods=['POST'])
# def receive_trade():
#     """Receive new trade execution from bot"""
#     from flask import request
#     try:
#         data = request.get_json()
        
#         trade = {
#             "id": f"{data.get('instrument')}_{data.get('timeframe')}_{int(time.time())}",
#             "type": data.get('type'),  # BUY or SELL
#             "instrument": data.get('instrument'),
#             "timeframe": data.get('timeframe'),
#             "entry": data.get('entry'),
#             "sl": data.get('sl'),
#             "tp": data.get('tp'),
#             "timestamp": datetime.now().strftime("%H:%M:%S"),
#             "pnl": 0,
#             "status": "OPEN"
#         }
        
#         # Add to active positions
#         bot_state["active_positions"].append(trade)
#         bot_state["open_positions"] = len(bot_state["active_positions"])
#         bot_state["total_trades"] += 1
        
#         # Add to recent trades
#         bot_state["recent_trades"].append(trade)
        
#         logger.info(f"✅ Trade added: {trade['type']} {trade['instrument']} @ {trade['entry']}")
        
#         # Broadcast update
#         socketio.emit('bot_update', bot_state, to=None)
        
#         return jsonify({"status": "success"}), 200
    
#     except Exception as e:
#         logger.error(f"❌ Error adding trade: {e}")
#         return jsonify({"status": "error", "message": str(e)}), 500


# # ✅ API ENDPOINT: Update Position P&L

# @app.route('/api/position-update', methods=['POST'])
# def update_position():
#     """Update P&L for open position"""
#     from flask import request
#     try:
#         data = request.get_json()
#         instrument = data.get('instrument')
#         timeframe = data.get('timeframe')
#         pnl = data.get('pnl')
#         current_price = data.get('current_price')
        
#         # Find and update position
#         for pos in bot_state["active_positions"]:
#             if pos["instrument"] == instrument and pos["timeframe"] == timeframe:
#                 pos["pnl"] = pnl
#                 pos["current_price"] = current_price
#                 break
        
#         # Update floating P&L
#         bot_state["floating_pnl"] = sum(p.get("pnl", 0) for p in bot_state["active_positions"])
        
#         socketio.emit('bot_update', bot_state, to=None)
        
#         return jsonify({"status": "success"}), 200
    
#     except Exception as e:
#         logger.error(f"❌ Error updating position: {e}")
#         return jsonify({"status": "error", "message": str(e)}), 500


# # ✅ API ENDPOINT: Close Trade

# @app.route('/api/trade-close', methods=['POST'])
# def close_trade():
#     """Close a trade and calculate P&L"""
#     from flask import request
#     try:
#         data = request.get_json()
#         instrument = data.get('instrument')
#         timeframe = data.get('timeframe')
#         exit_price = data.get('exit_price')
#         pnl = data.get('pnl')
        
#         # Find trade in active positions
#         for i, pos in enumerate(bot_state["active_positions"]):
#             if pos["instrument"] == instrument and pos["timeframe"] == timeframe:
#                 pos["exit_price"] = exit_price
#                 pos["pnl"] = pnl
#                 pos["status"] = "CLOSED"
#                 pos["close_time"] = datetime.now().strftime("%H:%M:%S")
                
#                 # Update win/loss counts
#                 if pnl > 0:
#                     bot_state["winning_trades"] += 1
#                 else:
#                     bot_state["losing_trades"] += 1
                
#                 # Move to recent trades
#                 bot_state["recent_trades"].append(pos)
#                 bot_state["active_positions"].pop(i)
#                 break
        
#         # Update metrics
#         bot_state["open_positions"] = len(bot_state["active_positions"])
#         bot_state["floating_pnl"] = sum(p.get("pnl", 0) for p in bot_state["active_positions"])
        
#         # Calculate win rate
#         total = bot_state["winning_trades"] + bot_state["losing_trades"]
#         if total > 0:
#             bot_state["win_rate"] = round((bot_state["winning_trades"] / total) * 100, 1)
        
#         logger.info(f"🏁 Trade closed: {pnl} | Win rate: {bot_state['win_rate']}%")
        
#         socketio.emit('bot_update', bot_state, to=None)
        
#         return jsonify({"status": "success"}), 200
    
#     except Exception as e:
#         logger.error(f"❌ Error closing trade: {e}")
#         return jsonify({"status": "error", "message": str(e)}), 500


# # ✅ API ENDPOINT: Load Historical Trades (from database or Oanda)

# @app.route('/api/load-history', methods=['POST'])
# def load_history():
#     """
#     Load all historical trades from your trading history
#     You can call this from your bot to populate initial data
#     """
#     from flask import request
#     try:
#         data = request.get_json()
#         historical_trades = data.get('trades', [])
        
#         # Clear and reload
#         bot_state["recent_trades"].clear()
#         bot_state["active_positions"] = []
#         bot_state["total_trades"] = 0
#         bot_state["winning_trades"] = 0
#         bot_state["losing_trades"] = 0
        
#         # Process historical trades
#         for trade in historical_trades:
#             bot_state["recent_trades"].append(trade)
#             bot_state["total_trades"] += 1
            
#             if trade.get("status") == "CLOSED":
#                 pnl = trade.get("pnl", 0)
#                 if pnl > 0:
#                     bot_state["winning_trades"] += 1
#                 else:
#                     bot_state["losing_trades"] += 1
#             elif trade.get("status") == "OPEN":
#                 bot_state["active_positions"].append(trade)
        
#         # Recalculate stats
#         bot_state["open_positions"] = len(bot_state["active_positions"])
#         total = bot_state["winning_trades"] + bot_state["losing_trades"]
#         if total > 0:
#             bot_state["win_rate"] = round((bot_state["winning_trades"] / total) * 100, 1)
        
#         logger.info(f"📚 Loaded {len(historical_trades)} historical trades")
        
#         socketio.emit('bot_update', bot_state, to=None)
        
#         return jsonify({
#             "status": "success",
#             "trades_loaded": len(historical_trades),
#             "total_trades": bot_state["total_trades"],
#             "win_rate": bot_state["win_rate"]
#         }), 200
    
#     except Exception as e:
#         logger.error(f"❌ Error loading history: {e}")
#         return jsonify({"status": "error", "message": str(e)}), 500


# # ✅ API ENDPOINT: Get Current State

# @app.route('/api/state', methods=['GET'])
# def get_state():
#     """Get current bot state"""
#     return jsonify({
#         **bot_state,
#         "recent_trades": list(bot_state["recent_trades"]),
#         "trading_signals": list(bot_state["trading_signals"])
#     }), 200


# def fetch_oanda_account_balance():
#     """Fetch account balance from Oanda API"""
#     try:
#         api_key = "5c821a3a1a23d3b8a18ffb0b8d10d852-887ec40cabdda2551683deb7e6d329a4"
#         account_id = "101-011-36217286-002"
#         base_url = "https://api-fxpractice.oanda.com"
        
#         headers = {
#             "Authorization": f"Bearer {api_key}",
#             "Content-Type": "application/json"
#         }
        
#         url = f"{base_url}/v3/accounts/{account_id}"
#         response = requests.get(url, headers=headers, timeout=10)
        
#         if response.status_code == 200:
#             data = response.json()
#             balance = float(data.get("account", {}).get("balance", 10000))
#             logger.info(f"💰 Account balance: ${balance:.2f}")
#             return balance
#         return None
#     except Exception as e:
#         logger.warning(f"⚠️ Error fetching balance: {e}")
#         return None


# # ✅ WEBSOCKET EVENTS

# @socketio.on('connect')
# def handle_connect():
#     global connected_clients
#     connected_clients += 1
#     logger.info(f"✅ Dashboard connected! (Total: {connected_clients})")
    
#     # ✅ FIX: Fetch balance before emitting
#     balance = fetch_oanda_account_balance()
#     if balance is not None:
#         bot_state["account_balance"] = balance
    
#     emit('initial_data', {
#         "status": bot_state["status"],
#         "account_balance": bot_state["account_balance"],  # ✅ Include balance
#         "floating_pnl": bot_state["floating_pnl"],
#         "open_positions": bot_state["open_positions"],
#         "total_trades": bot_state["total_trades"],
#         "winning_trades": bot_state["winning_trades"],
#         "losing_trades": bot_state["losing_trades"],
#         "win_rate": bot_state["win_rate"],
#         "active_positions": bot_state["active_positions"],
#         "recent_trades": list(bot_state["recent_trades"]),
#         "trading_signals": list(bot_state["trading_signals"])
#     })



# @socketio.on('disconnect')
# def handle_disconnect():
#     global connected_clients
#     connected_clients -= 1
#     logger.info(f"❌ Dashboard disconnected (Total: {connected_clients})")


# @socketio.on('request_update')
# def handle_update_request():
#     """Dashboard can request fresh data"""
#     emit('bot_update', {
#         **bot_state,
#         "recent_trades": list(bot_state["recent_trades"]),
#         "trading_signals": list(bot_state["trading_signals"])
#     })


# def broadcast_bot_state():
#     """Broadcast state every 2 seconds with balance fetch"""
#     while True:
#         try:
#             if connected_clients > 0:
#                 # ✅ FIX 1: Fetch balance from Oanda
#                 balance = fetch_oanda_account_balance()
#                 if balance is not None:
#                     bot_state["account_balance"] = balance
                
#                 # ✅ FIX 2: Emit bot_state with proper structure
#                 socketio.emit('bot_update', {
#                     "status": bot_state["status"],
#                     "account_balance": bot_state["account_balance"],  # ✅ Include balance
#                     "floating_pnl": bot_state["floating_pnl"],
#                     "open_positions": bot_state["open_positions"],
#                     "total_trades": bot_state["total_trades"],
#                     "winning_trades": bot_state["winning_trades"],
#                     "losing_trades": bot_state["losing_trades"],
#                     "win_rate": bot_state["win_rate"],
#                     "active_positions": bot_state["active_positions"],
#                     "recent_trades": list(bot_state["recent_trades"]),
#                     "trading_signals": list(bot_state["trading_signals"])
#                 }, to=None)
#         except Exception as e:
#             logger.warning(f"⚠️ Broadcast error: {e}")
        
#         time.sleep(2)



# if __name__ == "__main__":
#     # Start background broadcasting
#     socketio.start_background_task(broadcast_bot_state)
    
#     print("\n" + "="*80)
#     print("🚀 TRADING BOT BACKEND SERVER (ENHANCED)")
#     print("="*80)
#     print(f"\n✅ WebSocket Server running on http://localhost:5000")
#     print(f"✅ API Endpoints:")
#     print(f"   - POST http://localhost:5000/api/signal (Trading signals)")
#     print(f"   - POST http://localhost:5000/api/trade (New trades)")
#     print(f"   - POST http://localhost:5000/api/position-update (Update P&L)")
#     print(f"   - POST http://localhost:5000/api/trade-close (Close trades)")
#     print(f"   - POST http://localhost:5000/api/load-history (Load history)")
#     print(f"   - GET http://localhost:5000/api/state (Get state)")
#     print(f"\n📊 Dashboard: Open dashboard.html in browser")
#     print("\n" + "="*80 + "\n")
    
#     socketio.run(app, host="0.0.0.0", port=5000, debug=False)
"""
FIXED backend_enhanced.py - Converts deque to list for JSON
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import time
import logging
from threading import Thread
from datetime import datetime
from collections import deque

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

bot_state = {
    "status": "LIVE",
    "account_balance": 10000,
    "floating_pnl": 0,
    "open_positions": 0,
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "win_rate": 0,
    "profit_factor": 0,
    "active_positions": [],
    "recent_trades": deque(maxlen=100),
    "trading_signals": deque(maxlen=50),
    "config": {}
}

def deque_to_list(obj):
    """Convert deque objects to lists for JSON serialization"""
    if isinstance(obj, deque):
        return list(obj)
    raise TypeError

@app.route('/api/signal', methods=['POST'])
def receive_signal():
    """Receive real-time trading signals from bot"""
    try:
        data = request.get_json()
        signal_type = data.get('type')
        message = data.get('message')
        instrument = data.get('instrument')
        timeframe = data.get('timeframe')
        
        signal_event = {
            "type": signal_type,
            "message": message,
            "instrument": instrument,
            "timeframe": timeframe,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_ms": time.time()
        }
        
        bot_state["trading_signals"].append(signal_event)
        logger.info(f"📊 Signal received: {signal_type} | {instrument} | {timeframe}")
        
        socketio.emit('trading_signal', signal_event, to=None)

        socketio.emit('bot_update', {
            "status": bot_state["status"],
            "account_balance": bot_state["account_balance"],
            "floating_pnl": bot_state["floating_pnl"],
            "open_positions": bot_state["open_positions"],
            "total_trades": bot_state["total_trades"],
            "winning_trades": bot_state["winning_trades"],
            "losing_trades": bot_state["losing_trades"],
            "win_rate": bot_state["win_rate"],
            "active_positions": bot_state["active_positions"],
            "recent_trades": list(bot_state["recent_trades"]),
            "trading_signals": list(bot_state["trading_signals"]),
        }, to=None)

        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"❌ Error processing signal: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade', methods=['POST'])
def receive_trade():
    """Receive new trade execution from bot"""
    try:
        data = request.get_json()
        trade = {
            "id": f"{data.get('instrument')}_{data.get('timeframe')}_{int(time.time())}",
            "type": data.get('type'),
            "instrument": data.get('instrument'),
            "timeframe": data.get('timeframe'),
            "entry": data.get('entry'),
            "sl": data.get('sl'),
            "tp": data.get('tp'),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "pnl": 0,
            "status": "OPEN"
        }
        
        bot_state["active_positions"].append(trade)
        bot_state["open_positions"] = len(bot_state["active_positions"])
        bot_state["total_trades"] += 1
        bot_state["recent_trades"].append(trade)
        
        logger.info(f"✅ Trade added: {trade['type']} {trade['instrument']} @ {trade['entry']}")
        
        socketio.emit('bot_update', {
            "status": bot_state["status"],
            "account_balance": bot_state["account_balance"],
            "floating_pnl": bot_state["floating_pnl"],
            "open_positions": bot_state["open_positions"],
            "total_trades": bot_state["total_trades"],
            "winning_trades": bot_state["winning_trades"],
            "losing_trades": bot_state["losing_trades"],
            "win_rate": bot_state["win_rate"],
            "active_positions": bot_state["active_positions"],
            "recent_trades": list(bot_state["recent_trades"]),
            "trading_signals": list(bot_state["trading_signals"]),
        }, to=None)


        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"❌ Error adding trade: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/position-update', methods=['POST'])
def update_position():
    """Update P&L for open position"""
    try:
        data = request.get_json()
        instrument = data.get('instrument')
        timeframe = data.get('timeframe')
        pnl = data.get('pnl')
        current_price = data.get('current_price')
        
        for pos in bot_state["active_positions"]:
            if pos["instrument"] == instrument and pos["timeframe"] == timeframe:
                pos["pnl"] = pnl
                pos["current_price"] = current_price
                break
        
        bot_state["floating_pnl"] = sum(p.get("pnl", 0) for p in bot_state["active_positions"])
        
        socketio.emit('bot_update', {
            "status": bot_state["status"],
            "account_balance": bot_state["account_balance"],
            "floating_pnl": bot_state["floating_pnl"],
            "open_positions": bot_state["open_positions"],
            "total_trades": bot_state["total_trades"],
            "winning_trades": bot_state["winning_trades"],
            "losing_trades": bot_state["losing_trades"],
            "win_rate": bot_state["win_rate"],
            "active_positions": bot_state["active_positions"],
            "recent_trades": list(bot_state["recent_trades"]),
            "trading_signals": list(bot_state["trading_signals"]),
        }, to=None)


        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"❌ Error updating position: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade-close', methods=['POST'])
def close_trade():
    """Close a trade and calculate P&L"""
    try:
        data = request.get_json()
        instrument = data.get('instrument')
        timeframe = data.get('timeframe')
        exit_price = data.get('exit_price')
        pnl = data.get('pnl')
        
        for i, pos in enumerate(bot_state["active_positions"]):
            if pos["instrument"] == instrument and pos["timeframe"] == timeframe:
                pos["exit_price"] = exit_price
                pos["pnl"] = pnl
                pos["status"] = "CLOSED"
                pos["close_time"] = datetime.now().strftime("%H:%M:%S")
                
                if pnl > 0:
                    bot_state["winning_trades"] += 1
                else:
                    bot_state["losing_trades"] += 1
                
                bot_state["recent_trades"].append(pos)
                bot_state["active_positions"].pop(i)
                break
        
        bot_state["open_positions"] = len(bot_state["active_positions"])
        bot_state["floating_pnl"] = sum(p.get("pnl", 0) for p in bot_state["active_positions"])
        
        total = bot_state["winning_trades"] + bot_state["losing_trades"]
        if total > 0:
            bot_state["win_rate"] = round((bot_state["winning_trades"] / total) * 100, 1)
        
        logger.info(f"🏁 Trade closed: {pnl} | Win rate: {bot_state['win_rate']}%")
        
        socketio.emit('bot_update', {
    "status": bot_state["status"],
    "account_balance": bot_state["account_balance"],
    "floating_pnl": bot_state["floating_pnl"],
    "open_positions": bot_state["open_positions"],
    "total_trades": bot_state["total_trades"],
    "winning_trades": bot_state["winning_trades"],
    "losing_trades": bot_state["losing_trades"],
    "win_rate": bot_state["win_rate"],
    "active_positions": bot_state["active_positions"],
    "recent_trades": list(bot_state["recent_trades"]),
    "trading_signals": list(bot_state["trading_signals"]),
}, to=None)

        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"❌ Error closing trade: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/load-history', methods=['POST'])
def load_history():
    """Load historical trades from Oanda"""
    try:
        data = request.get_json()
        historical_trades = data.get('trades', [])
        
        bot_state["recent_trades"].clear()
        bot_state["active_positions"] = []
        bot_state["total_trades"] = 0
        bot_state["winning_trades"] = 0
        bot_state["losing_trades"] = 0
        
        for trade in historical_trades:
            bot_state["recent_trades"].append(trade)
            bot_state["total_trades"] += 1
            
            if trade.get("status") == "CLOSED":
                pnl = trade.get("pnl", 0)
                if pnl > 0:
                    bot_state["winning_trades"] += 1
                else:
                    bot_state["losing_trades"] += 1
            elif trade.get("status") == "OPEN":
                bot_state["active_positions"].append(trade)
        
        bot_state["open_positions"] = len(bot_state["active_positions"])
        total = bot_state["winning_trades"] + bot_state["losing_trades"]
        if total > 0:
            bot_state["win_rate"] = round((bot_state["winning_trades"] / total) * 100, 1)
        
        logger.info(f"📚 Loaded {len(historical_trades)} historical trades")
        
        socketio.emit('bot_update', {
    "status": bot_state["status"],
    "account_balance": bot_state["account_balance"],
    "floating_pnl": bot_state["floating_pnl"],
    "open_positions": bot_state["open_positions"],
    "total_trades": bot_state["total_trades"],
    "winning_trades": bot_state["winning_trades"],
    "losing_trades": bot_state["losing_trades"],
    "win_rate": bot_state["win_rate"],
    "active_positions": bot_state["active_positions"],
    "recent_trades": list(bot_state["recent_trades"]),
    "trading_signals": list(bot_state["trading_signals"]),
}, to=None)

        
        return jsonify({
            "status": "success",
            "trades_loaded": len(historical_trades),
            "total_trades": bot_state["total_trades"],
            "win_rate": bot_state["win_rate"]
        }), 200
    except Exception as e:
        logger.error(f"❌ Error loading history: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def index():
    """Serve dashboard"""
    return render_template('dashboard_enhanced.html')

@app.route('/api/status')
def get_status():
    """Get bot status"""
    return jsonify({
        "status": "success",
        "data": {
            "status": bot_state["status"],
            "total_trades": bot_state["total_trades"],
            "winning_trades": bot_state["winning_trades"],
            "losing_trades": bot_state["losing_trades"],
            "win_rate": bot_state["win_rate"],
            "open_positions": bot_state["open_positions"],
            "floating_pnl": bot_state["floating_pnl"],
            "recent_trades": list(bot_state["recent_trades"]),  # Convert deque to list
            "trading_signals": list(bot_state["trading_signals"])  # Convert deque to list
        }
    }), 200

connected_clients = 0

@socketio.on('connect')
def handle_connect():
    global connected_clients
    connected_clients += 1
    logger.info(f"✅ Dashboard connected! (Total: {connected_clients})")

    emit('initial_data', {
        "status": bot_state["status"],
        "account_balance": bot_state["account_balance"],
        "floating_pnl": bot_state["floating_pnl"],
        "open_positions": bot_state["open_positions"],
        "total_trades": bot_state["total_trades"],
        "winning_trades": bot_state["winning_trades"],
        "losing_trades": bot_state["losing_trades"],
        "win_rate": bot_state["win_rate"],
        "active_positions": bot_state["active_positions"],
        "recent_trades": list(bot_state["recent_trades"]),
        "trading_signals": list(bot_state["trading_signals"]),
    })


if __name__ == '__main__':
    logger.info("🚀 Backend starting...")
    socketio.run(app, host='127.0.0.1', port=5000, debug=False)