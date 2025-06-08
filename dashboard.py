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
    if 'trades' in data and data['trades']:
        inventory_df = pd.DataFrame(data['trades'])
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
                        melted_df = tick_df_filtered[['time'] + final_plot_columns].melt(
                            id_vars=['time'],
                            value_vars=final_plot_columns_full,
                            var_name='variable',
                            value_name='value'
                        )
                        melted_df_full['value'] = pd.to_numeric(melted_df_full['value'], errors='coerce')

                        # Convert 'value' to numeric, coercing errors for potentially mixed types if quotes are missing
                        melted_df['value'] = pd.to_numeric(melted_df['value'], errors='coerce')

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
    st.info("No data to display. Run a backtest to generate `backtest_results.json`.")
