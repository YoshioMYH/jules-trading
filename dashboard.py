import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from bokeh.core.enums import TooltipFieldFormatter
from bokeh.models import ColumnDataSource, HoverTool, DatetimeTickFormatter
from bokeh.palettes import Category10
from bokeh.plotting import figure
from streamlit_bokeh import streamlit_bokeh

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


def prepare_ohlc_data(market_data_df: pd.DataFrame, resample_freq: str = '1min') -> pd.DataFrame:
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

    ohlc_display_df = ohlc_df.iloc[0:visible_candles]

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
                    trades_df = pd.DataFrame()  # Make it empty to skip plotting trades

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
        else:  # 'time' column missing in trades_df
            st.warning("Trades data is missing 'time' column, cannot plot trades on OHLC.")

    # Bokeh plot
    # source = ColumnDataSource(ohlc_display_df)

    # Determine candle width (e.g., 80% of the median time difference)
    # Ensure 'time' is sorted for correct diff calculation
    ohlc_display_df = ohlc_display_df.sort_values(by='time')
    time_diffs = ohlc_display_df['time'].diff().dt.total_seconds() * 1000  # milliseconds
    # Use a default width if only one candle or time_diffs is empty/NaN
    candle_width_ms = time_diffs.median() * 0.8 if len(time_diffs) > 1 and not time_diffs.iloc[
                                                                               1:].isnull().all() else 86400000 * 0.8  # Default to 80% of a day

    # Ensure candle_width_ms is a float and not NaN, otherwise Bokeh might error
    if pd.isna(candle_width_ms):
        candle_width_ms = 86400000 * 0.8  # Fallback default width

    p = figure(
        x_axis_type="datetime",
        tools="xpan,xwheel_zoom,ywheel_zoom,reset,save,box_zoom",  # Added box_zoom for better zoom control
        active_drag="xpan",
        active_scroll="xwheel_zoom",
        title=f"OHLC Chart (Candle width: {candle_width_ms:.2f}ms)"  # Debug title
    )
    p.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M",
        days="%d %b",
        months="%b %Y",
        years="%Y",
    )
    p.xaxis.major_label_orientation = 0.8  # Radians, approx 45 degrees

    # Candlestick colors
    inc = ohlc_display_df.close > ohlc_display_df.open
    dec = ohlc_display_df.open > ohlc_display_df.close
    equal = ohlc_display_df.open == ohlc_display_df.close  # Handle cases where open == close

    # Wicks
    p.segment(ohlc_display_df.time, ohlc_display_df.high, ohlc_display_df.time, ohlc_display_df.low, color="black")

    # Candle bodies
    # Green for increasing
    p.vbar(ohlc_display_df.time[inc], candle_width_ms, ohlc_display_df.open[inc], ohlc_display_df.close[inc],
           fill_color=Category10[3][0], line_color="black")
    # Red for decreasing
    p.vbar(ohlc_display_df.time[dec], candle_width_ms, ohlc_display_df.open[dec], ohlc_display_df.close[dec],
           fill_color=Category10[3][1], line_color="black")
    # Blue or Gray for equal open/close (optional, could also use previous close to determine color)
    p.vbar(ohlc_display_df.time[equal], candle_width_ms, ohlc_display_df.open[equal], ohlc_display_df.close[equal],
           fill_color=Category10[3][2], line_color="black")

    hover_tooltips = [
        ("Time", "@time{%F %T}"),
        ("Open", "@open{0,0.00}"),
        ("High", "@high{0,0.00}"),
        ("Low", "@low{0,0.00}"),
        ("Close", "@close{0,0.00}")
    ]
    hover_formatters = {
        '@time': TooltipFieldFormatter.datetime,
    }

    if trades_df is not None and not trades_df.empty:
        if 'time' in trades_df.columns and 'price' in trades_df.columns and 'type' in trades_df.columns:
            # Ensure 'time' column is datetime for trades as well
            if not pd.api.types.is_datetime64_any_dtype(trades_df['time']):
                try:
                    trades_df['time'] = pd.to_datetime(trades_df['time'])
                except Exception as e:
                    st.error(f"Error converting 'time' in trades_df for Bokeh plot: {e}")
                    trades_df = pd.DataFrame()  # Empty to skip

            if not trades_df.empty:
                min_time_ohlc = ohlc_display_df['time'].min()
                max_time_ohlc = ohlc_display_df['time'].max()
                relevant_trades_bokeh = trades_df[
                    (trades_df['time'] >= min_time_ohlc) & (trades_df['time'] <= max_time_ohlc)
                    ]

                if not relevant_trades_bokeh.empty:
                    buy_trades_bokeh = relevant_trades_bokeh[relevant_trades_bokeh['type'] == 'buy']
                    sell_trades_bokeh = relevant_trades_bokeh[relevant_trades_bokeh['type'] == 'sell']

                    if not buy_trades_bokeh.empty:
                        buy_source = ColumnDataSource(buy_trades_bokeh)
                        p.scatter(
                            x='time', y='price', source=buy_source,
                            marker='triangle', size=10, color=Category10[4][1], legend_label='Buy Trades'
                            # Brighter green
                        )
                        # Add separate hover for buys if needed, or ensure main hover tool catches them
                        # For simplicity, the main hover tool might not show trade-specific info unless configured

                    if not sell_trades_bokeh.empty:
                        sell_source = ColumnDataSource(sell_trades_bokeh)
                        p.scatter(
                            x='time', y='price', source=sell_source,
                            marker='inverted_triangle', size=10, color=Category10[4][0], legend_label='Sell Trades'
                            # Brighter red
                        )
        else:
            st.warning("Trades data is missing required columns ('time', 'price', 'type') for Bokeh plot.")

    # Add a generic hover tool for OHLC data (can be customized further)
    # Tooltip for trades can be added by creating separate renderers and hover tools for them if needed
    p.add_tools(HoverTool(tooltips=hover_tooltips, formatters=hover_formatters, mode='vline'))

    p.legend.location = "top_left"
    p.legend.click_policy = "hide"  # "mute" also an option

    streamlit_bokeh(p, use_container_width=True)


def plot_line_chart_bokeh(df: pd.DataFrame, x_column: str, y_column: str, title: str, visible_points: int):
    """Plots a line chart using Bokeh."""
    if df is None or df.empty:
        st.info(f"No data available to plot {title}.")
        return

    if x_column not in df.columns or y_column not in df.columns:
        st.warning(f"Data for {title} is missing required columns: '{x_column}' or '{y_column}'.")
        return

    # Ensure x_column is datetime
    if not pd.api.types.is_datetime64_any_dtype(df[x_column]):
        try:
            df[x_column] = pd.to_datetime(df[x_column])
        except Exception as e:
            st.error(f"Error converting '{x_column}' to datetime for {title}: {e}")
            return

    # Slice the DataFrame
    if visible_points < len(df):
        plot_df = df.iloc[-visible_points:]
    else:
        plot_df = df

    if plot_df.empty:
        st.info(f"No data in the selected range for {title}.")
        return

    source = ColumnDataSource(plot_df)

    p = figure(
        x_axis_type="datetime",
        title=title,
        tools="xpan,xwheel_zoom,ywheel_zoom,reset,save,hover",
        active_drag="xpan",
        active_scroll="xwheel_zoom"
    )

    p.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M",
        days="%d %b",
        months="%b %Y",
        years="%Y"
    )
    p.xaxis.major_label_orientation = 0.8  # Radians, approx 45 degrees

    p.line(x=x_column, y=y_column, source=source, line_width=2)

    hover_tool = HoverTool(
        tooltips=[
            ("Time", f"@{x_column}{{%F %T}}"),
            (title.split(" ")[0], f"@{y_column}{{0,0.00}}")
        ],
        formatters={
            f"@{x_column}": "datetime"
        },
        mode='vline'  # Show tooltip for all points on the same x-coordinate
    )
    p.add_tools(hover_tool)

    streamlit_bokeh(p, use_container_width=True)


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

            # Number input for PnL chart
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

                # Bokeh chart using the potentially sliced pnl_df
                if not pnl_df.empty:
                    plot_line_chart_bokeh(pnl_df, 'time', 'pnl', "PnL Over Time", pnl_visible_points_val)
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

                # Bokeh chart using the potentially sliced inventory_df
                if not inventory_df.empty:
                    plot_line_chart_bokeh(inventory_df, 'time', 'inventory', "Inventory Over Time", inv_visible_points_val)
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
    freq_options = {'1 Second': '1s', '10 Second': '10s', '1 Minute': '1min', '30 Minutes': '30min', '1 Hour': '1h',
                    '12 Hours': '12H',
                    '1 Day': '1D', '1 Week': '1W', '1 Month': '1ME'}
    selected_freq_label = st.selectbox("OHLC Resample Frequency", options=list(freq_options.keys()), index=2)
    resample_freq_code = freq_options[selected_freq_label]

    ohlc_df = prepare_ohlc_data(market_data, resample_freq_code)

    if not ohlc_df.empty:
        st.subheader(f"Market OHLC ({selected_freq_label})")

        total_candles = len(ohlc_df)

        visible_candles_ohlc = st.number_input(
            "Number of OHLC candles to display",
            min_value=1,
            max_value=total_candles,
            value=total_candles,
            step=1,
            key="ohlc_visible_candles"
        )

        # Ensure types are correct for the function
        visible_candles_ohlc = int(visible_candles_ohlc)

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

        plot_ohlc_with_trades(ohlc_df, current_trades_df, visible_candles_ohlc)

    else:
        st.info("OHLC data could not be prepared. Check warnings above.")
else:
    st.info(
        "No market data available to generate OHLC chart. Ensure 'market_data_path' was in results and the file is valid."
    )
