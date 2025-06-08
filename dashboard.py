import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import load_trade_data

# Set page config for wider layout
st.set_page_config(layout="wide")

st.title("Backtest Visualization Dashboard")

# Define the expected path for the results file
RESULTS_FILE = "backtest_results.json"
DEFAULT_CHART_DISPLAY = 1000


@st.cache_data  # Cache the data loading
def load_data(file_path):
    market_df = None
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                backtest_data = json.load(f)

            if backtest_data and 'parameters' in backtest_data and 'market_data_path' in backtest_data['parameters']:
                market_data_file_path = backtest_data['parameters']['market_data_path']
                if market_data_file_path:
                    try:
                        market_df = load_trade_data(market_data_file_path)
                        if market_df.empty:
                            st.warning(f"Market data file loaded from '{market_data_file_path}' is empty.")
                            market_df = None  # Ensure it's None if empty
                        else:
                            # Ensure 'time' column is datetime
                            if 'time' in market_df.columns:
                                market_df['time'] = pd.to_datetime(market_df['time'])
                            else:
                                st.warning(f"Market data from '{market_data_file_path}' is missing 'time' column.")
                                market_df = None  # Invalid market data
                    except FileNotFoundError:
                        st.warning(
                            f"Market data file not found at path specified in results: '{market_data_file_path}'.")
                        market_df = None
                    except Exception as e:
                        st.warning(f"Error loading market data from '{market_data_file_path}': {e}")
                        market_df = None
                else:
                    st.info("No market data path specified in backtest results.")
            else:
                st.info("Could not find 'market_data_path' in backtest results parameters.")

            return backtest_data, market_df
        except json.JSONDecodeError:
            st.error(f"Error decoding JSON from {file_path}. Ensure it's a valid JSON file.")
            return None, None
        except Exception as e:
            st.error(f"An unexpected error occurred while loading {file_path}: {e}")
            return None, None
    else:
        st.warning(
            f"Results file not found at {file_path}. Please run a backtest first using `main.py` or `src/backtester.py`.")
        return None, None


def prepare_ohlc_data(market_data_df: pd.DataFrame, resample_freq: str = '1T') -> pd.DataFrame:
    if market_data_df is None or market_data_df.empty:
        st.info("Market data is empty, cannot prepare OHLC data.")
        return pd.DataFrame()

    if 'time' not in market_data_df.columns or 'price' not in market_data_df.columns:
        st.warning("Market data must contain 'time' and 'price' columns for OHLC chart.")
        return pd.DataFrame()

    # Ensure 'time' is datetime and set as index
    market_df_indexed = market_data_df.copy()
    try:
        market_df_indexed['time'] = pd.to_datetime(market_df_indexed['time'])
        market_df_indexed = market_df_indexed.set_index('time')
    except Exception as e:
        st.warning(f"Error setting 'time' column as index for OHLC: {e}")
        return pd.DataFrame()

    try:
        ohlc = market_df_indexed['price'].resample(resample_freq).ohlc()
        return ohlc.reset_index()  # Reset index to have 'time' as a column for plotting
    except Exception as e:
        st.warning(f"Error resampling market data for OHLC: {e}")
        return pd.DataFrame()


def plot_ohlc_with_trades(ohlc_df: pd.DataFrame, trades_df: pd.DataFrame = None, visible_candles: int = 50):
    required_cols = ['time', 'open', 'high', 'low', 'close']
    if ohlc_df.empty or not all(col in ohlc_df.columns for col in required_cols):
        st.info("Not enough data or incorrect format for OHLC chart.")
        return

    # Ensure 'time' column is datetime, only if df is not empty and column exists
    if not ohlc_df.empty and 'time' in ohlc_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(ohlc_df['time']):
            try:
                ohlc_df['time'] = pd.to_datetime(ohlc_df['time'])
            except Exception as e:
                st.error(f"Error converting 'time' column in OHLC data to datetime: {e}")
                return
    else:  # Should not happen if prepare_ohlc_data is correct, but defensive
        st.error("OHLC data is missing 'time' column or is empty before time conversion.")
        return

    # Removed start_index and end_index logic
    # ohlc_display_df is replaced by ohlc_df

    if ohlc_df.empty: # Check the main ohlc_df
        st.info("No OHLC data to display.") # Adjusted message slightly
        return

    candlestick_trace = go.Candlestick(
        x=ohlc_df['time'], # Use ohlc_df
        open=ohlc_df['open'], # Use ohlc_df
        high=ohlc_df['high'], # Use ohlc_df
        low=ohlc_df['low'], # Use ohlc_df
        close=ohlc_df['close'], # Use ohlc_df
        name='OHLC'
    )
    fig_data = [candlestick_trace]

    if trades_df is not None and not trades_df.empty:
        # Ensure 'time' column is datetime, only if df is not empty and column exists
        if 'time' in trades_df.columns:
            if not pd.api.types.is_datetime64_any_dtype(trades_df['time']):
                try:
                    trades_df['time'] = pd.to_datetime(trades_df['time'])
                except Exception as e:
                    st.error(f"Error converting 'time' column in trades data to datetime: {e}")
                    trades_df = pd.DataFrame()  # Make it empty to skip plotting trades

            # Proceed only if trades_df is still valid (not emptied by error handling) and has time
            if not trades_df.empty and 'time' in trades_df.columns and not ohlc_df.empty: # Also check ohlc_df not empty
                min_time_ohlc = ohlc_df['time'].min() # Use ohlc_df for min time
                max_time_ohlc = ohlc_df['time'].max() # Use ohlc_df for max time
                relevant_trades = trades_df[(trades_df['time'] >= min_time_ohlc) & (trades_df['time'] <= max_time_ohlc)]

                if not relevant_trades.empty:
                    buy_trades = relevant_trades[relevant_trades['type'] == 'buy']
                    sell_trades = relevant_trades[relevant_trades['type'] == 'sell']

                    if not buy_trades.empty:
                        buy_trace = go.Scatter(
                            x=buy_trades['time'], y=buy_trades['price'],
                            mode='markers', name='Buy Trades',
                            marker=dict(color='green', size=8, symbol='triangle-up')
                        )
                        fig_data.append(buy_trace)

                    if not sell_trades.empty:
                        sell_trace = go.Scatter(
                            x=sell_trades['time'], y=sell_trades['price'],
                            mode='markers', name='Sell Trades',
                            marker=dict(color='red', size=8, symbol='triangle-down')
                        )
                        fig_data.append(sell_trace)
        else:  # 'time' column missing in trades_df
            st.warning("Trades data is missing 'time' column, cannot plot trades on OHLC.")

    layout = go.Layout(
        title='OHLC Chart with Trades',
        xaxis_title='Time', yaxis_title='Price',
        xaxis_rangeslider_visible=True,
        yaxis=dict(
            autorange=True,
            fixedrange=False  # Ensure fixedrange is False for y-axis too
        )
    )
    fig = go.Figure(data=fig_data, layout=layout)

    # Set initial X-axis range based on visible_candles
    if not ohlc_df.empty and visible_candles > 0 and len(ohlc_df) > 1:
        start_time = ohlc_df['time'].iloc[0]
        # Calculate end index, ensuring it's within bounds
        end_idx = min(visible_candles - 1, len(ohlc_df) - 1)
        end_time = ohlc_df['time'].iloc[end_idx]

        # Only update layout if start_time and end_time are different to avoid issues
        if start_time != end_time:
            fig.update_layout(xaxis_range=[start_time, end_time])
        # If start_time == end_time (e.g., only one data point in ohlc_df or visible_candles is 1),
        # Plotly will auto-range, which is acceptable.

    st.plotly_chart(fig, use_container_width=True)


backtest_data, market_data = load_data(RESULTS_FILE)

# 1. Display Parameters and Summary Statistics
st.header("Backtest Configuration & Summary")
if backtest_data:
    st.success(f"Successfully loaded backtest data from {RESULTS_FILE}")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Parameters")
        if 'parameters' in backtest_data and backtest_data['parameters'] is not None:
            st.json(backtest_data['parameters'])
        else:
            st.warning("Parameters not found or are null in backtest_data.")
    with col2:
        st.subheader("Summary Statistics")
        if 'summary_stats' in backtest_data and backtest_data['summary_stats'] is not None:
            st.json(backtest_data['summary_stats'])
        else:
            st.warning("Summary statistics not found or are null in backtest_data.")

    # 2. Display Trades Table
    st.header("Trade Log")
    if 'trades' in backtest_data and backtest_data['trades']:
        trades_df = pd.DataFrame(backtest_data['trades'])
        # Convert time to datetime if it's not already (it should be string from JSON)
        if 'time' in trades_df.columns:
            trades_df['time'] = pd.to_datetime(trades_df['time'])
        st.dataframe(trades_df, height=300, use_container_width=True)  # Added height parameter
    else:
        st.info("No trades to display.")

    # 3. Plot PnL Over Time
    st.header("Performance Analysis")  # Changed header to group performance plots
    if 'trades' in backtest_data and backtest_data['trades']:
        pnl_df = pd.DataFrame(backtest_data['trades'])
        if 'time' in pnl_df.columns and 'pnl' in pnl_df.columns:
            pnl_df['time'] = pd.to_datetime(pnl_df['time'])
            pnl_df = pnl_df.sort_values(by='time')
            st.subheader("PnL Over Time")

            # Sliders for PnL chart
            total_points = len(pnl_df)
            if total_points > 0:  # Ensure there's data before creating controls
                pnl_visible_points = st.number_input(
                    "Number of PnL data points to display",
                    min_value=10,
                    max_value=max(10, total_points),  # Ensure max_value is at least min_value
                    value=min(DEFAULT_CHART_DISPLAY, total_points),
                    step=10,
                    key="pnl_visible_points_input"
                )
                # Ensure pnl_visible_points is an int for calculations
                pnl_visible_points_val = int(pnl_visible_points)
                # pnl_start_point slider and associated filtering logic removed.

                # Plotly chart using the full pnl_df
                if not pnl_df.empty:
                    fig = px.line(pnl_df, x='time', y='pnl', title="PnL Over Time")
                    if pnl_visible_points_val > 0 and len(pnl_df) > 1:
                        end_idx = min(pnl_visible_points_val - 1, len(pnl_df) - 1)  # -1 because iloc is 0-indexed
                        if end_idx > 0:  # Ensure there's a valid range
                            # Check if start and end time are different to avoid Plotly error/warning
                            if pnl_df['time'].iloc[0] != pnl_df['time'].iloc[end_idx]:
                                fig.update_layout(xaxis_range=[pnl_df['time'].iloc[0], pnl_df['time'].iloc[end_idx]])
                            # If start and end time are the same (e.g. end_idx is 0 after -1, or all times are identical for the range)
                            # Plotly will auto-range, which is acceptable.
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No PnL data to display.")
            else:
                st.info("No PnL data points to plot.")
        else:
            st.warning("PnL data ('time' or 'pnl' column) not found in trades.")
    else:
        st.info("No trade data to plot PnL.")

    # 4. Plot Inventory Over Time
    if 'trades' in backtest_data and backtest_data['trades']:
        inventory_df = pd.DataFrame(backtest_data['trades'])
        if 'time' in inventory_df.columns and 'inventory' in inventory_df.columns:
            inventory_df['time'] = pd.to_datetime(inventory_df['time'])
            inventory_df = inventory_df.sort_values(by='time')
            st.subheader("Inventory Over Time")

            # Number input for Inventory chart
            inv_total_points = len(inventory_df)
            if inv_total_points > 0:
                inv_visible_points = st.number_input(
                    "Number of Inventory data points to display",
                    min_value=10,
                    max_value=max(10, inv_total_points),
                    value=min(DEFAULT_CHART_DISPLAY, inv_total_points),
                    step=10,
                    key="inv_visible_points_input"  # Unique key
                )
                # Ensure inv_visible_points is an int for calculations
                inv_visible_points_val = int(inv_visible_points)
                # inv_start_point slider and associated filtering logic removed.

                # Plotly chart using the full inventory_df
                if not inventory_df.empty:
                    fig_inv = px.line(inventory_df, x='time', y='inventory', title="Inventory Over Time")
                    if inv_visible_points_val > 0 and len(inventory_df) > 1:
                        end_idx = min(inv_visible_points_val - 1, len(inventory_df) - 1)
                        if end_idx > 0:
                            if inventory_df['time'].iloc[0] != inventory_df['time'].iloc[end_idx]:
                                fig_inv.update_layout(
                                    xaxis_range=[inventory_df['time'].iloc[0], inventory_df['time'].iloc[end_idx]])
                    st.plotly_chart(fig_inv, use_container_width=True)
                else:
                    st.info("No Inventory data to display.")
            else:
                st.info("No Inventory data points to plot.")
        else:
            st.warning("Inventory data ('time' or 'inventory' column) not found in trades.")
    # No redundant else here, if 'trades' is empty/None, PnL plot's else covers it.
else:
    st.info("No backtest data to display. Run a backtest to generate `backtest_results.json`.")

# 5. OHLC Chart
st.header("Market Data")
if market_data is not None and not market_data.empty:
    st.success(f"Successfully loaded market data from {backtest_data['parameters']['market_data_path']}")

    # Resample frequency selection
    freq_options = {'1 Second': '1S', '1 Minute': '1T', '30 Minutes': '30T', '1 Hour': '1H', '12 Hours': '12H',
                    '1 Day': '1D', '1 Week': '1W', '1 Month': '1M'}
    selected_freq_label = st.selectbox("OHLC Resample Frequency", options=list(freq_options.keys()), index=0)
    resample_freq_code = freq_options[selected_freq_label]

    ohlc_df = prepare_ohlc_data(market_data, resample_freq_code)

    if not ohlc_df.empty:
        st.subheader(f"Market OHLC ({selected_freq_label})")

        total_candles = len(ohlc_df)

        # Number input for visible candles (no longer in columns)
        visible_candles_ohlc = st.number_input(
            "Number of OHLC candles to display for initial view", # Updated label
            min_value=10,
            max_value=max(10, total_candles),
            value=min(50, total_candles),  # Default to 50 or total_candles if less
            step=10,
            key="ohlc_visible_candles"
        )

        # Ensure types are correct for the function
        visible_candles_ohlc = int(visible_candles_ohlc)
        # start_index_ohlc and its conversion to int are removed

        # Get the trades_df if available
        raw_trades_list = backtest_data.get('trades')
        current_trades_df = None
        if raw_trades_list:  # Check if list is not None and not empty
            current_trades_df = pd.DataFrame(raw_trades_list)
            if 'time' in current_trades_df.columns:
                # Time conversion is now handled inside plot_ohlc_with_trades
                # but ensuring it's a valid datetime type early can be good.
                # For now, rely on plot_ohlc_with_trades's internal conversion.
                pass
            else:
                st.warning("Trades data loaded for OHLC plot is missing 'time' column.")
                current_trades_df = None  # Invalidate if 'time' column is missing

        # Call plot_ohlc_with_trades without start_index_ohlc
        # The actual slicing for display is now controlled by Plotly's own zoom/pan
        # and the visible_candles_ohlc and start_index_ohlc sliders will be used
        # to set the initial view range of the chart if desired, or removed if
        # full chart view is default. For now, let's assume they might be used
        # to set an initial viewport if that feature is kept or added later
        # outside this specific function. The function itself now ignores start_index.
        # The visible_candles parameter is also not used for slicing anymore.
        # For now, we pass visible_candles_ohlc but it's not used inside plot_ohlc_with_trades
        # for slicing. It could be used for layout hints if needed.
        plot_ohlc_with_trades(ohlc_df, current_trades_df, visible_candles_ohlc)

    else:
        st.info("OHLC data could not be prepared. Check warnings above.")
else:
    st.info(
        "No market data available to generate OHLC chart. Ensure 'market_data_path' was in results and the file is valid."
    )
