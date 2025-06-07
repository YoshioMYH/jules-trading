import streamlit as st
import json
import pandas as pd
import plotly.express as px
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
                if total_points > pnl_visible_points_val:
                    pnl_start_point = st.slider(
                        "PnL data starting point",
                        min_value=0,
                        max_value=max(0, total_points - pnl_visible_points_val),
                        value=0,
                        step=pnl_visible_points_val, # Step by the number of visible points
                        key="pnl_start_point"
                    )
                else:
                    pnl_start_point = 0 # No need for a start slider if all points are visible

                # Filter data based on sliders
                pnl_df_filtered = pnl_df.iloc[pnl_start_point : pnl_start_point + pnl_visible_points]

                # Plotly chart
                if not pnl_df_filtered.empty:
                    fig = px.line(pnl_df_filtered, x='time', y='pnl', title="PnL Over Time")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No data to display for the selected PnL range.")
            else:
                st.info("No PnL data points to plot.")
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

            # Sliders for Inventory chart
            inv_total_points = len(inventory_df)
            if inv_total_points > 0: # Ensure there's data before creating controls
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
                if inv_total_points > inv_visible_points_val:
                    inv_start_point = st.slider(
                        "Inventory data starting point",
                        min_value=0,
                        max_value=max(0, inv_total_points - inv_visible_points_val),
                        value=0,
                        step=inv_visible_points_val, # Step by the number of visible points
                        key="inv_start_point" # Unique key
                    )
                else:
                    inv_start_point = 0 # No need for a start slider if all points are visible

                # Filter data based on sliders
                inv_df_filtered = inventory_df.iloc[inv_start_point : inv_start_point + inv_visible_points]

                # Plotly chart
                if not inv_df_filtered.empty:
                    fig_inv = px.line(inv_df_filtered, x='time', y='inventory', title="Inventory Over Time")
                    st.plotly_chart(fig_inv, use_container_width=True)
                else:
                    st.info("No data to display for the selected Inventory range.")
            else:
                st.info("No Inventory data points to plot.")
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
                            step=market_visible_points_val, # Step by the number of visible points
                            key="market_start_point" # Unique key
                        )
                    else:
                        market_start_point = 0

                    # Filter tick_df based on sliders first
                    tick_df_filtered = tick_df.iloc[market_start_point : market_start_point + market_visible_points]

                    # Prepare data for Plotly by melting
                    # Reset index to bring 'time' back as a column if it was set as index
                    # However, tick_df['time'] is already a column, so no need to reset_index if we directly use tick_df_filtered

                    # Ensure 'time' is datetime
                    tick_df_filtered['time'] = pd.to_datetime(tick_df_filtered['time'])

                    # Select relevant columns for melting
                    columns_to_melt = ['time'] + [col for col in plot_columns if col in tick_df_filtered.columns]

                    # Ensure plot_columns exist in tick_df_filtered before melting
                    final_plot_columns = [col for col in plot_columns if col in tick_df_filtered.columns]

                    if len(final_plot_columns) > 0 : # only proceed if there are columns to plot
                        melted_df = tick_df_filtered[['time'] + final_plot_columns].melt(
                            id_vars=['time'],
                            value_vars=final_plot_columns,
                            var_name='variable',
                            value_name='value'
                        )

                        # Convert 'value' to numeric, coercing errors for potentially mixed types if quotes are missing
                        melted_df['value'] = pd.to_numeric(melted_df['value'], errors='coerce')

                        if not melted_df.empty:
                            fig_market = px.line(melted_df, x='time', y='value', color='variable', title="Market Price and Quotes")
                            st.plotly_chart(fig_market, use_container_width=True)
                        else:
                            st.info("No data to display for the selected market data range after filtering/melting.")
                    else:
                        st.warning("Selected columns for market plot are not available in the filtered data.")

                else:
                    st.info("No Market data points to plot.")
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
