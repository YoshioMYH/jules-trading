import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np # For np.arange

from src.data_loader import load_trade_data
from src.strategy import MarketMakingStrategy
from src.utils import permute_trade_data # Import for permutation
from src.backtester import Backtester

def main():
    parser = argparse.ArgumentParser(description="Market Making Strategy Backtester with Optimization")
    parser.add_argument('--data_file', type=str, required=True, help='Path to the CSV trade data file.')
    parser.add_argument('--order_size', type=float, required=True, help='Order size for the strategy.')
    parser.add_argument('--spread_min_bps', type=float, required=True, help='Minimum spread in basis points for optimization.')
    parser.add_argument('--spread_max_bps', type=float, required=True, help='Maximum spread in basis points for optimization.')
    parser.add_argument('--spread_step_bps', type=float, required=True, help='Step size for spread in basis points during optimization.')
    parser.add_argument('--output_plot_prefix', type=str, default='optimization_plot', help='Prefix for output plot filenames.')
    parser.add_argument('--permute_data', action='store_true', help='If set, run backtest on data with shuffled prices.')

    args = parser.parse_args()

    print(f"Loading data from: {args.data_file}")
    trade_df = load_trade_data(args.data_file)

    if trade_df.empty:
        print(f"Error: No data loaded from {args.data_file}. Exiting.")
        return

    if args.permute_data:
        print("\nINFO: Running backtest on PERMUTED data (shuffled 'price' column).\n")
        trade_df = permute_trade_data(trade_df, column_to_shuffle='price')
        if trade_df.empty: # Should not happen with current permute_trade_data logic unless original df was empty
            print("Error: Permutation resulted in an empty DataFrame. Exiting.")
            return


    spread_values_bps = np.arange(args.spread_min_bps, args.spread_max_bps + args.spread_step_bps, args.spread_step_bps)

    if len(spread_values_bps) == 0 or args.spread_step_bps <= 0:
        print("Error: Spread range or step is invalid. Ensure spread_max_bps >= spread_min_bps and spread_step_bps > 0.")
        return

    print(f"Optimizing for spread_bps from {args.spread_min_bps} to {args.spread_max_bps} with step {args.spread_step_bps}.")
    print(f"Order size for all runs: {args.order_size}")

    all_results = []

    for current_spread_bps in spread_values_bps:
        print(f"\nRunning backtest for spread_bps: {current_spread_bps:.2f}...")

        # Re-initialize strategy and backtester for each run to ensure no state leakage
        strategy = MarketMakingStrategy(quote_size=args.order_size)
        backtester = Backtester(data=trade_df.copy(), strategy=strategy) # Use a copy of df if it's modified by backtester (it shouldn't be)

        backtester.run_backtest(spread_bps=current_spread_bps, order_size=args.order_size)

        final_pnl = strategy.pnl
        num_trades = len(backtester.get_results())
        final_inventory = strategy.inventory

        all_results.append({
            'spread_bps': current_spread_bps,
            'final_pnl': final_pnl,
            'num_trades': num_trades,
            'final_inventory': final_inventory
        })
        print(f"Spread: {current_spread_bps:.2f} bps => PnL: {final_pnl:.4f}, Trades: {num_trades}, Inventory: {final_inventory:.4f}")

    print("\n--- Optimization Summary ---")
    if not all_results:
        print("No backtest runs were completed.")
        return

    results_df = pd.DataFrame(all_results)
    print(results_df.to_string(index=False))

    best_run = results_df.loc[results_df['final_pnl'].idxmax()]

    print("\n--- Best Parameters ---")
    print(f"Best Spread: {best_run['spread_bps']:.2f} bps")
    print(f"Corresponding PnL: {best_run['final_pnl']:.4f}")
    print(f"Corresponding Trades: {best_run['num_trades']}")
    print(f"Corresponding Final Inventory: {best_run['final_inventory']:.4f}")

    # Generate Summary Plots
    if not results_df.empty:
        try:
            # Plot PnL vs. Spread
            plt.figure(figsize=(10, 6))
            plt.plot(results_df['spread_bps'], results_df['final_pnl'], marker='o', linestyle='-')
            plt.title('Final PnL vs. Spread (bps)')
            plt.xlabel('Spread (bps)')
            plt.ylabel('Final PnL')
            plt.grid(True)
            pnl_plot_filename = f"{args.output_plot_prefix}_pnl_vs_spread.png"
            plt.savefig(pnl_plot_filename)
            print(f"\nPnL vs. Spread plot saved to: {pnl_plot_filename}")
            plt.close()

            # Plot Number of Trades vs. Spread
            plt.figure(figsize=(10, 6))
            plt.plot(results_df['spread_bps'], results_df['num_trades'], marker='o', linestyle='-')
            plt.title('Number of Trades vs. Spread (bps)')
            plt.xlabel('Spread (bps)')
            plt.ylabel('Number of Trades')
            plt.grid(True)
            trades_plot_filename = f"{args.output_plot_prefix}_trades_vs_spread.png"
            plt.savefig(trades_plot_filename)
            print(f"Trades vs. Spread plot saved to: {trades_plot_filename}")
            plt.close()

        except Exception as e:
            print(f"Error generating summary plots: {e}")
    else:
        print("No results to plot.")

if __name__ == '__main__':
    main()
