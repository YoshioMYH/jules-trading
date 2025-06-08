import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import json # For saving detailed results
import logging # For better logging

from src.backtester import Backtester
from src.data_loader import load_trade_data
from src.strategy import SimpleMarketMakerStrategy # MarketMakingStrategy removed
from src.utils import permute_trade_data, DateTimeEncoder

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="SimpleMarketMakerStrategy Backtester")
    parser.add_argument('--data-file', type=str, required=True, help='Path to the CSV trade data file.')
    parser.add_argument('--fee-bps', type=int, default=10, help='Trading fee in basis points (e.g., 10 for 0.1%)')
    parser.add_argument('--output-prefix', type=str, default='smm_backtest_run', help='Prefix for output plot and results filenames.')
    parser.add_argument('--permute-data', action='store_true', help='If set, run backtest on data with shuffled prices.')

    # SMM specific arguments (renamed for clarity as this is SMM only now)
    parser.add_argument('--initial-capital', type=float, default=10000.0, help='Initial capital for SimpleMarketMakerStrategy.')
    parser.add_argument('--order-size', type=float, default=0.1, help='Order size for SimpleMarketMakerStrategy.')
    parser.add_argument('--price-levels', type=str, default="90,95,100,105,110", help='Comma-separated price levels for SMM buy orders (e.g., "90,95,100").')
    parser.add_argument('--increment', type=float, default=10.0, help='Price increment for SMM sell orders.')
    parser.add_argument('--symbol', type=str, default="TEST/USD", help="Trading symbol for the strategy.")
    parser.add_argument('--strategy-id', type=str, default="SMM_MainRun", help="Identifier for the strategy instance.")


    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info(f"Loading data from: {args.data_file}")
    trade_df = load_trade_data(args.data_file)

    if trade_df.empty:
        logger.error(f"Error: No data loaded from {args.data_file}. Exiting.")
        return

    if args.permute_data:
        logger.info("\nINFO: Running backtest on PERMUTED data (shuffled 'price' column).\n")
        trade_df = permute_trade_data(trade_df, column_to_shuffle='price')
        if trade_df.empty:
            logger.error("Error: Permutation resulted in an empty DataFrame. Exiting.")
            return

    logger.info("Running SimpleMarketMakerStrategy...")
    smm_price_levels = [float(p.strip()) for p in args.price_levels.split(',')]
    logger.info(f"SMM Params: Initial Capital: {args.initial_capital}, Order Size: {args.order_size}, "
                f"Price Levels: {smm_price_levels}, Increment: {args.increment}, Fee: {args.fee_bps} bps, "
                f"Symbol: {args.symbol}, Strategy ID: {args.strategy_id}")

    strategy = SimpleMarketMakerStrategy(
        exchange=None, # Backtester will set this
        symbol=args.symbol,
        order_size=args.order_size,
        price_levels=smm_price_levels,
        increment=args.increment,
        strategy_id=args.strategy_id
    )
    backtester = Backtester(
        data=trade_df.copy(),
        strategy=strategy,
        fee_bps=args.fee_bps,
        initial_capital=args.initial_capital
    )

    backtester.run_backtest(data_file_path=args.data_file)

    results = backtester.get_results()
    summary = results['summary_stats']

    logger.info(f"\n--- SMM Run Summary ---")
    logger.info(f"Parameters: {json.dumps(results['parameters'], indent=2)}")
    logger.info(f"PnL: {summary['final_pnl']:.4f}, Trades: {summary['total_trades']}, Final Inventory: {summary['final_inventory']:.4f}")

    detailed_results_filename = f"{args.output_prefix}_details.json"
    try:
        with open(detailed_results_filename, 'w') as f:
            json.dump(results, f, indent=4, cls=DateTimeEncoder)
        logger.info(f"Detailed SMM results saved to {detailed_results_filename}")
    except Exception as e:
        logger.error(f"Error saving detailed SMM results: {e}")

    # Plotting PnL over time for SMM run
    smm_trades_log = results.get('trades', [])
    if smm_trades_log:
        try:
            plt.figure(figsize=(12, 7))
            smm_pnl_over_time = [trade['pnl'] for trade in smm_trades_log]
            smm_trade_times = pd.to_datetime([trade['time'] for trade in smm_trades_log])
            plt.plot(smm_trade_times, smm_pnl_over_time, marker='o', linestyle='-', markersize=4)
            plt.title(f'SMM PnL Over Time - Fee: {args.fee_bps}bps')
            plt.xlabel('Time of Trade')
            plt.ylabel('Cumulative PnL')
            plt.grid(True)
            plt.xticks(rotation=45)
            plt.tight_layout()
            smm_pnl_plot_filename = f"{args.output_prefix}_pnl_over_time.png"
            plt.savefig(smm_pnl_plot_filename)
            logger.info(f"\nSMM PnL over time plot saved to: {smm_pnl_plot_filename}")
            plt.close()
        except Exception as e:
            logger.error(f"Error generating SMM PnL plot: {e}")
    else:
        logger.info("No trades in SMM run to plot PnL over time.")

if __name__ == '__main__':
    main()
