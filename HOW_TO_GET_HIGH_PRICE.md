# How to Extract High Price from Websocket Data

## 🔍 Understanding the Data

The websocket sends **two types of messages**:

### 1. Market Info (No Price Data)

```python
{
  'type': 'market_info',
  'currentTs': '1759835001482',
  'marketInfo': {...}  # Market status for different exchanges
}
```

**→ Skip this - it has no price data**

### 2. Feed Data (Has Price Data)

```python
{
  'feeds': {
    'NSE_INDEX|Nifty 50': {
      'fullFeed': {
        'indexFF': {
          'ltpc': {
            'ltp': 25108.3,        # Last Traded Price
            'cp': 25077.65         # Change from previous close
          },
          'marketOHLC': {
            'ohlc': [
              {
                'interval': '1d',   # Daily candle
                'open': 25085.3,
                'high': 25220.9,   # ← THIS IS THE HIGH PRICE!
                'low': 25076.3,
                'close': 25108.3,  # Current price
                'ts': '1759775400000'
              },
              {
                'interval': 'I1',   # Intraday candle
                'high': 25112.0    # ← Intraday high
              }
            ]
          }
        }
      }
    }
  }
}
```

## 📊 Data Path to High Price

For **Index** (like Nifty 50):

```
data_dict
  → ['feeds']
    → ['NSE_INDEX|Nifty 50']
      → ['fullFeed']
        → ['indexFF']
          → ['marketOHLC']
            → ['ohlc']
              → [0]              # First element = daily data
                → ['high']       # ← HIGH PRICE HERE!
```

For **Stocks**:

```
data_dict
  → ['feeds']
    → ['NSE_EQ|INE669E01016']   # Stock instrument key
      → ['fullFeed']
        → ['marketFF']           # Notice: marketFF (not indexFF)
          → ['marketOHLC']
            → ['ohlc']
              → [0]
                → ['high']       # ← HIGH PRICE HERE!
```

## 💡 Why JSON dumps vs Print Difference?

**`print(data_dict)`**

```python
{'type': 'market_info', 'currentTs': '...'}  # Python dict with single quotes
```

**`print(json.dumps(data_dict))`**

```json
{"type": "market_info", "currentTs": "..."}  # JSON string with double quotes
```

**They're the SAME data!** Just different formats:

- `print(data_dict)` → Shows Python dictionary
- `json.dumps(data_dict)` → Converts to JSON string

## ✅ How It Works Now

1. **Websocket receives data** → `data_dict`
2. **Check if it has feeds**:
   - If `'feeds'` exists → Has price data
   - If not → Market info only (skip)
3. **Extract high price safely**:
   ```python
   if 'feeds' in data_dict:
       feed = data_dict['feeds']['NSE_INDEX|Nifty 50']
       if 'fullFeed' in feed:
           if 'indexFF' in feed['fullFeed']:  # For Index
               ohlc = feed['fullFeed']['indexFF']['marketOHLC']['ohlc'][0]
               high_price = float(ohlc['high'])
               current_price = float(ohlc['close'])
   ```
4. **Call trading logic**:
   ```python
   kamal.when_to_buy(
       start_hour=9,
       start_minute=15,
       end_hour=15,
       end_minute=30,
       current_price=current_price,
       high_price=tracked_high_price
   )
   ```

## 🎯 Trading Flow

```
Websocket → Extract prices → Check time window → Compare prices → Buy decision
```

### Example Output:

```
📊 HIGH: ₹25220.9 | CURRENT: ₹25108.3
✅ IN TRADING WINDOW | Current: ₹25108.3 | High: ₹25220.9
📊 Monitoring... Drop: 0.45%
```

## 🚀 Run Your Bot

```bash
python websocket_for_us_data.py
```

It will:

1. ✅ Connect to websocket
2. ✅ Extract high price and current price
3. ✅ Track highest price seen
4. ✅ Check if it's trading time
5. ✅ Decide when to buy based on price drop

## 🔧 Customize

Change trading hours:

```python
tracked_high_price = kamal.when_to_buy(
    start_hour=9,     # Start at 9:15 AM
    start_minute=15,
    end_hour=15,      # End at 3:30 PM
    end_minute=30,
    current_price=current_price,
    high_price=tracked_high_price
)
```

Change buy trigger:
In `mani.py` line 130:

```python
if drop_percentage > 0.5:  # Change this value
    # Buy if price dropped more than 0.5%
```
