import streamlit as st
import json
import pandas as pd
import os

# Set page config for wider layout
st.set_page_config(layout="wide")

st.title("Backtest Visualization Dashboard")

# Define the expected path for the results file
RESULTS_FILE = "backtest_results.json"

@st.cache_data # Cache the data loading
def load_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError:
            st.error(f"Error decoding JSON from {file_path}. Ensure it's a valid JSON file.")
            return None
        except Exception as e:
            st.error(f"An unexpected error occurred while loading {file_path}: {e}")
            return None
    else:
        st.warning(f"Results file not found at {file_path}. Please run a backtest first using `main.py` or `src/backtester.py`.")
        return None

data = load_data(RESULTS_FILE)

if data:
    st.success(f"Successfully loaded data from {RESULTS_FILE}")

    # 1. Display Parameters and Summary Statistics
    st.header("Backtest Configuration & Summary")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Parameters")
        if 'parameters' in data and data['parameters'] is not None:
            st.json(data['parameters'])
        else:
            st.warning("Parameters not found or are null in data.")
    with col2:
        st.subheader("Summary Statistics")
        if 'summary_stats' in data and data['summary_stats'] is not None:
            st.json(data['summary_stats'])
        else:
            st.warning("Summary statistics not found or are null in data.")

    # 2. Display Trades Table
    st.header("Trade Log")
    if 'trades' in data and data['trades']:
        trades_df = pd.DataFrame(data['trades'])
        # Convert time to datetime if it's not already (it should be string from JSON)
        if 'time' in trades_df.columns:
            trades_df['time'] = pd.to_datetime(trades_df['time'])
        st.dataframe(trades_df, height=300, use_container_width=True) # Added height parameter
    else:
        st.info("No trades to display.")

    # 3. Plot PnL Over Time
    st.header("Performance Analysis") # Changed header to group performance plots
    if 'trades' in data and data['trades']:
        pnl_df = pd.DataFrame(data['trades'])
        if 'time' in pnl_df.columns and 'pnl' in pnl_df.columns:
            pnl_df['time'] = pd.to_datetime(pnl_df['time'])
            pnl_df = pnl_df.sort_values(by='time')
            st.subheader("PnL Over Time")
            st.line_chart(pnl_df.set_index('time')['pnl'], use_container_width=True)
        else:
            st.warning("PnL data ('time' or 'pnl' column) not found in trades.")
    else:
        st.info("No trade data to plot PnL.") # This else might be redundant if the one above catches it.
                                            # However, data['trades'] could exist but be empty or lack columns.

    # 4. Plot Inventory Over Time
    if 'trades' in data and data['trades']: # Assumes it's under the same "Performance Analysis" header
        inventory_df = pd.DataFrame(data['trades'])
        if 'time' in inventory_df.columns and 'inventory' in inventory_df.columns:
            inventory_df['time'] = pd.to_datetime(inventory_df['time'])
            inventory_df = inventory_df.sort_values(by='time')
            st.subheader("Inventory Over Time")
            st.line_chart(inventory_df.set_index('time')['inventory'], use_container_width=True)
        else:
            st.warning("Inventory data ('time' or 'inventory' column) not found in trades.")
    # No redundant else here, if 'trades' is empty/None, PnL plot's else covers it.

    # 5. Plot Market Prices and Quotes
    st.header("Market and Quote Analysis")
    if 'tick_data' in data and data['tick_data']:
        tick_df = pd.DataFrame(data['tick_data'])
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
                # Ensure selected columns are numeric, fillna for plotting if necessary
                # ffill/bfill might be too aggressive if quotes are sparse; consider .interpolate() or just plot raw
                chart_data = tick_df.set_index('time')[plot_columns].astype(float) # Plot directly, NaNs will cause breaks
                st.line_chart(chart_data, use_container_width=True)
            else:
                st.warning("Not enough quote data (bid_quote, ask_quote have no values) found in tick_data to plot alongside market price.")
        else:
            st.warning("Tick data ('time' column) not found.")
    else:
        st.info("No tick data to plot market prices and quotes.")
else:
    st.info("No data to display. Run a backtest to generate `backtest_results.json`.")

# Add a note about running the backtester
st.sidebar.header("Instructions")
st.sidebar.info(
    "1. Ensure you have run a backtest using `python src/backtester.py --data-file data/your_trade_data.csv` "
    " (replace `your_trade_data.csv` with your actual data file, e.g., `sample_trades.csv`). "
    "This will generate the `backtest_results.json` file."
    "\n\n"
    "2. This dashboard will then visualize the contents of `backtest_results.json`."
    "\n\n"
    "3. To run this dashboard, open your terminal in the project root directory and execute:\n"
    "`streamlit run dashboard.py`"
)
