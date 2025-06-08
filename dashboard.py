import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from src.data_loader import load_trade_data

# Set page config for wider layout
st.set_page_config(layout="wide")

st.title("Backtest Visualization Dashboard")

# Define the expected path for the results file
RESULTS_FILE = "backtest_results.json"

@st.cache_data # Cache the data loading
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
                            market_df = None # Ensure it's None if empty
                        else:
                            # Ensure 'time' column is datetime
                            if 'time' in market_df.columns:
                                market_df['time'] = pd.to_datetime(market_df['time'])
                            else:
                                st.warning(f"Market data from '{market_data_file_path}' is missing 'time' column.")
                                market_df = None # Invalid market data
                    except FileNotFoundError:
                        st.warning(f"Market data file not found at path specified in results: '{market_data_file_path}'.")
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
        st.warning(f"Results file not found at {file_path}. Please run a backtest first using `main.py` or `src/backtester.py`.")
        return None, None

backtest_data, market_data = load_data(RESULTS_FILE)

if backtest_data:
    st.success(f"Successfully loaded backtest data from {RESULTS_FILE}")
    if market_data is not None and not market_data.empty:
        st.success(f"Successfully loaded market data from {backtest_data['parameters']['market_data_path']}")
    elif 'parameters' in backtest_data and backtest_data['parameters'].get('market_data_path'):
        # Warning for market data loading failure was already shown in load_data
        pass # Avoid duplicate warning if path was present but loading failed
    else:
        st.info("Market data path not found in results or market data could not be loaded.")


    # 1. Display Parameters and Summary Statistics
    st.header("Backtest Configuration & Summary")
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
        st.dataframe(trades_df, height=300, use_container_width=True) # Added height parameter
    else:
        st.info("No trades to display.")

    # 3. Plot PnL Over Time
    st.header("Performance Analysis") # Changed header to group performance plots
    if 'trades' in backtest_data and backtest_data['trades']:
        pnl_df = pd.DataFrame(backtest_data['trades'])
        if 'time' in pnl_df.columns and 'pnl' in pnl_df.columns:
            pnl_df['time'] = pd.to_datetime(pnl_df['time'])
            pnl_df = pnl_df.sort_values(by='time')
            st.subheader("PnL Over Time")

            # Sliders for PnL chart
            total_points = len(pnl_df)
            if total_points > 0: # Ensure there's data before creating controls
                pnl_visible_points = st.number_input(
                    "Number of PnL data points to display",
                    min_value=10,
                    max_value=max(10, total_points), # Ensure max_value is at least min_value
                    value=min(50, total_points), # Default to 50 or total_points if less
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
                        end_idx = min(pnl_visible_points_val -1, len(pnl_df) - 1) # -1 because iloc is 0-indexed
                        if end_idx > 0: # Ensure there's a valid range
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
                    value=min(50, inv_total_points),
                    step=10,
                    key="inv_visible_points_input" # Unique key
                )
                # Ensure inv_visible_points is an int for calculations
                inv_visible_points_val = int(inv_visible_points)
                # inv_start_point slider and associated filtering logic removed.

                # Plotly chart using the full inventory_df
                if not inventory_df.empty:
                    fig_inv = px.line(inventory_df, x='time', y='inventory', title="Inventory Over Time")
                    if inv_visible_points_val > 0 and len(inventory_df) > 1:
                        end_idx = min(inv_visible_points_val -1, len(inventory_df) - 1)
                        if end_idx > 0:
                            if inventory_df['time'].iloc[0] != inventory_df['time'].iloc[end_idx]:
                                fig_inv.update_layout(xaxis_range=[inventory_df['time'].iloc[0], inventory_df['time'].iloc[end_idx]])
                    st.plotly_chart(fig_inv, use_container_width=True)
                else:
                    st.info("No Inventory data to display.")
            else:
                st.info("No Inventory data points to plot.")
        else:
            st.warning("Inventory data ('time' or 'inventory' column) not found in trades.")
    # No redundant else here, if 'trades' is empty/None, PnL plot's else covers it.

    # 5. OHLC Chart (New Section)
    st.header("Market Data OHLC")

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
            return ohlc.reset_index() # Reset index to have 'time' as a column for plotting
        except Exception as e:
            st.warning(f"Error resampling market data for OHLC: {e}")
            return pd.DataFrame()

def plot_ohlc_with_trades(ohlc_df: pd.DataFrame, trades_df: pd.DataFrame = None, visible_candles: int = 50, start_index: int = 0):
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
    else: # Should not happen if prepare_ohlc_data is correct, but defensive
        st.error("OHLC data is missing 'time' column or is empty before time conversion.")
        return

    if start_index < 0:
        start_index = 0
    if visible_candles <= 0:
        visible_candles = 50 # Default to 50 if invalid

    end_index = start_index + visible_candles
    ohlc_display_df = ohlc_df.iloc[start_index:end_index]

    if ohlc_display_df.empty:
        st.info("No OHLC data in the selected range.")
        return

    candlestick_trace = go.Candlestick(
        x=ohlc_display_df['time'],
        open=ohlc_display_df['open'],
        high=ohlc_display_df['high'],
        low=ohlc_display_df['low'],
        close=ohlc_display_df['close'],
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
                    trades_df = pd.DataFrame() # Make it empty to skip plotting trades

            # Proceed only if trades_df is still valid (not emptied by error handling) and has time
            if not trades_df.empty and 'time' in trades_df.columns:
                min_time = ohlc_display_df['time'].min()
                max_time = ohlc_display_df['time'].max()
                relevant_trades = trades_df[(trades_df['time'] >= min_time) & (trades_df['time'] <= max_time)]

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
        else: # 'time' column missing in trades_df
            st.warning("Trades data is missing 'time' column, cannot plot trades on OHLC.")


    layout = go.Layout(
        title='OHLC Chart with Trades',
        xaxis_title='Time', yaxis_title='Price',
        xaxis_rangeslider_visible=False  # Use Streamlit slider for navigation
    )
    fig = go.Figure(data=fig_data, layout=layout)
    st.plotly_chart(fig, use_container_width=True)


if market_data is not None and not market_data.empty:
    # Resample frequency selection
    freq_options = {'1 Minute': '1T', '5 Minutes': '5T', '15 Minutes': '15T', '1 Hour': '1H', '4 Hours': '4H', '1 Day': '1D'}
    selected_freq_label = st.selectbox("OHLC Resample Frequency", options=list(freq_options.keys()), index=0)
    resample_freq_code = freq_options[selected_freq_label]

    ohlc_df = prepare_ohlc_data(market_data, resample_freq_code)

    if not ohlc_df.empty:
        st.subheader(f"Market OHLC ({selected_freq_label})")

        total_candles = len(ohlc_df)

        # Sliders for OHLC chart view
        col1_ohlc, col2_ohlc = st.columns(2)
        with col1_ohlc:
            visible_candles_ohlc = st.number_input(
                "Number of OHLC candles to display",
                min_value=10,
                max_value=max(10, total_candles),
                value=min(50, total_candles), # Default to 50 or total_candles if less
                step=10,
                key="ohlc_visible_candles"
            )
        with col2_ohlc:
            # Ensure max_value for slider is non-negative
            max_slider_val = max(0, total_candles - int(visible_candles_ohlc))
            start_index_ohlc = st.slider(
                "OHLC starting candle index",
                min_value=0,
                max_value=max_slider_val,
                value=0,
                step=1, # Or some other reasonable step
                key="ohlc_start_index"
            )

        # Ensure types are correct for the function
        visible_candles_ohlc = int(visible_candles_ohlc)
        start_index_ohlc = int(start_index_ohlc)

        # Get the trades_df if available
        raw_trades_list = backtest_data.get('trades')
        current_trades_df = None
        if raw_trades_list: # Check if list is not None and not empty
            current_trades_df = pd.DataFrame(raw_trades_list)
            if 'time' in current_trades_df.columns:
                 # Time conversion is now handled inside plot_ohlc_with_trades
                 # but ensuring it's a valid datetime type early can be good.
                 # For now, rely on plot_ohlc_with_trades's internal conversion.
                 pass
            else:
                st.warning("Trades data loaded for OHLC plot is missing 'time' column.")
                current_trades_df = None # Invalidate if 'time' column is missing

        plot_ohlc_with_trades(ohlc_df, current_trades_df, visible_candles_ohlc, start_index_ohlc)

    else:
        st.info("OHLC data could not be prepared. Check warnings above.")
    else:
        st.info("No market data available to generate OHLC chart. Ensure 'market_data_path' was in results and the file is valid.")


    # 6. Plot Market Prices and Quotes (was 5)
    st.header("Tick-Level Market and Quote Analysis")
    if 'tick_data' in backtest_data and backtest_data['tick_data']:
        tick_df = pd.DataFrame(backtest_data['tick_data'])
        if 'time' in tick_df.columns:
            tick_df['time'] = pd.to_datetime(tick_df['time'])
            tick_df = tick_df.sort_values(by='time')

            plot_columns = ['market_price']
            # Check if quote columns exist and have non-null data before adding
            if 'bid_quote' in tick_df.columns and tick_df['bid_quote'].notna().any():
                plot_columns.append('bid_quote')
            if 'ask_quote' in tick_df.columns and tick_df['ask_quote'].notna().any():
                plot_columns.append('ask_quote')

            if len(plot_columns) > 1: # Ensure we have at least market_price and one quote type
                st.subheader("Market Price and Strategy Quotes Over Time")

                # Sliders for Market Data chart
                market_total_points = len(tick_df)
                if market_total_points > 0:
                    market_visible_points = st.number_input(
                        "Number of Market data points to display",
                        min_value=10,
                        max_value=max(10, market_total_points),
                        value=min(50, market_total_points),
                        step=10,
                        key="market_visible_points_input" # Unique key
                    )
                    # Ensure market_visible_points is an int for calculations
                    market_visible_points_val = int(market_visible_points)
                    if market_total_points > market_visible_points_val:
                        market_start_point = st.slider(
                            "Market data starting point",
                            min_value=0,
                            max_value=max(0, market_total_points - market_visible_points_val),
                            value=0,
                            step=market_visible_points_val,  # Step by the number of visible points
                            key="market_start_point"  # Unique key
                        )
                    else:
                        market_start_point = 0

                    # Filter tick_df based on sliders first
                    tick_df_filtered = tick_df.iloc[market_start_point : market_start_point + market_visible_points]

                    # Prepare data for Plotly by melting the full tick_df (after initial column availability checks)
                    # 'time' column is already pd.to_datetime from the initial load of tick_df

                    # Ensure 'time' is datetime
                    tick_df_filtered.loc[:, 'time'] = pd.to_datetime(tick_df_filtered.loc[:, 'time'])

                    # Select relevant columns for melting
                    columns_to_melt = ['time'] + [col for col in plot_columns if col in tick_df_filtered.columns]

                    # Ensure plot_columns exist in tick_df_filtered before melting
                    final_plot_columns = [col for col in plot_columns if col in tick_df_filtered.columns]

                    if len(final_plot_columns) > 0:  # only proceed if there are columns to plot
                        # Ensure final_plot_columns are indeed in tick_df_filtered before melting
                        actual_columns_to_melt = [col for col in final_plot_columns if col in tick_df_filtered.columns]

                        if not actual_columns_to_melt: # If no valid columns left after filtering
                            st.warning("No valid data columns (market_price, bid_quote, ask_quote) available for plotting after filtering.")
                        else:
                            melted_df = tick_df_filtered[['time'] + actual_columns_to_melt].melt(
                                id_vars=['time'],
                                value_vars=actual_columns_to_melt, # Use the filtered list of columns
                                var_name='variable',
                                value_name='value'
                            )
                            # Convert 'value' to numeric, coercing errors for potentially mixed types if quotes are missing
                            melted_df['value'] = pd.to_numeric(melted_df['value'], errors='coerce')
                            # Drop rows where conversion to numeric might have failed for 'value'
                            melted_df.dropna(subset=['value'], inplace=True)


                            if not melted_df.empty:
                            fig_market = px.line(melted_df, x='time', y='value', color='variable',
                                                 title="Market Price and Quotes")
                            st.plotly_chart(fig_market, use_container_width=True)
                        else:
                            st.info("No data to display for market prices and quotes after processing.")
                    else:
                        st.warning("Selected columns for market plot are not available in the data.")
                else:
                    st.info("No Market data points to plot.")
            else:
                st.warning("Not enough quote data (bid_quote, ask_quote have no values) found in tick_data to plot alongside market price.")
        else:
            st.warning("Tick data ('time' column) not found.")
    else:
        st.info("No tick data to plot market prices and quotes.")
else:
    st.info("No backtest data to display. Run a backtest to generate `backtest_results.json`.")
