import argparse
import json

import pandas as pd
from tqdm import tqdm
import logging
from typing import Any # Simplified Union

from src.data_loader import load_trade_data
from src.strategy import SimpleMarketMakerStrategy # MarketMakingStrategy removed
from src.utils import DateTimeEncoder

logger = logging.getLogger(__name__)


class Backtester:
    """
    Simulates a market making strategy against historical trade data.
    Simulates a SimpleMarketMakerStrategy against historical trade data.
    Supports trading fees.
    """

    def __init__(self, data: pd.DataFrame, strategy: SimpleMarketMakerStrategy, fee_bps: int = 0, initial_capital: float = 10000.0):
        """
        Initializes the Backtester.

        Args:
            data: A pandas DataFrame containing historical trade data.
                  Expected columns: 'time', 'price', 'size'. 'buyer_maker' is optional.
            strategy: An instance of SimpleMarketMakerStrategy.
            fee_bps: Trading fee in basis points (e.g., 10 bps = 0.1%).
            initial_capital: Initial capital available to the strategy.
        """
        self.data = data
        self.strategy = strategy # Should be SimpleMarketMakerStrategy instance
        self.fee_bps = fee_bps
        self.initial_capital = initial_capital
        self.trades_log = []
        self.tick_data_log = [] # Log for SMM state per tick
        self.data_file_path: str | None = None

        # Mock exchange interface for the strategy
        self.mock_exchange_orders = {} # Stores orders placed by SMM: {order_id: details}
        self.mock_exchange_order_id_counter = 1

        # Strategy specific PnL if not tracked by strategy itself (e.g. for SMM if we chose to track PnL here)
        # self.strategy_pnl = 0.0 # Strategy tracks its own PnL
        # self.strategy_inventory = 0.0 # Strategy tracks its own inventory


    # --- Mock Exchange Interface for SimpleMarketMakerStrategy ---
    # These methods are called by the SimpleMarketMakerStrategy instance (self.strategy)
    def get_balance(self, strategy_id: str = None):
        logger.debug(f"Backtester.get_balance called by StratID {strategy_id if strategy_id else 'N/A'}, returning {self.initial_capital}")
        return self.initial_capital

    def place_limit_buy_order(self, symbol: str, size: float, price: float, strategy_id: str = None):
        order_id = f"bt_buy_{self.mock_exchange_order_id_counter}"
        self.mock_exchange_order_id_counter += 1
        self.mock_exchange_orders[order_id] = {
            'symbol': symbol, 'type': 'buy', 'size': size, 'price': price,
            'status': 'open', 'strategy_id': strategy_id if strategy_id else self.strategy.strategy_id
        }
        logger.info(f"Backtester (StratID {strategy_id if strategy_id else self.strategy.strategy_id}): Placed mock BUY order {order_id} for {size} {symbol} at {price}")
        return order_id

    def place_limit_sell_order(self, symbol: str, size: float, price: float, strategy_id: str = None):
        order_id = f"bt_sell_{self.mock_exchange_order_id_counter}"
        self.mock_exchange_order_id_counter += 1
        self.mock_exchange_orders[order_id] = {
            'symbol': symbol, 'type': 'sell', 'size': size, 'price': price,
            'status': 'open', 'strategy_id': strategy_id if strategy_id else self.strategy.strategy_id
        }
        logger.info(f"Backtester (StratID {strategy_id if strategy_id else self.strategy.strategy_id}): Placed mock SELL order {order_id} for {size} {symbol} at {price}")
        return order_id

    def cancel_order(self, order_id: str, strategy_id: str = None):
        strategy_id_to_check = strategy_id if strategy_id else self.strategy.strategy_id
        if order_id in self.mock_exchange_orders:
            if self.mock_exchange_orders[order_id]['strategy_id'] == strategy_id_to_check and \
               self.mock_exchange_orders[order_id]['status'] == 'open':
                self.mock_exchange_orders[order_id]['status'] = 'cancelled'
                logger.info(f"Backtester (StratID {strategy_id_to_check}): Cancelled mock order {order_id}")
                return True
            else:
                logger.warning(f"Backtester (StratID {strategy_id_to_check}): Failed to cancel mock order {order_id} (wrong strat_id or not open).")
                return False
        logger.warning(f"Backtester (StratID {strategy_id_to_check}): Mock order {order_id} not found for cancellation.")
        return False
    # --- End Mock Exchange Interface ---

    def run_backtest(self, data_file_path: str = None):
        """
        Runs the backtest simulation for SimpleMarketMakerStrategy.
        """
        if not isinstance(self.strategy, SimpleMarketMakerStrategy):
            raise ValueError("Backtester currently only supports SimpleMarketMakerStrategy.")

        self.data_file_path = data_file_path
        self.trades_log = []
        self.tick_data_log = []
        self.mock_exchange_orders = {}
        self.mock_exchange_order_id_counter = 1

        if self.data.empty:
            logger.error("Data is empty, cannot run backtest.")
            return

        logger.info(f"Running backtest for SimpleMarketMakerStrategy with fees {self.fee_bps}bps and initial capital {self.initial_capital}")
        self.strategy.exchange = self  # Strategy uses the backtester as its exchange interface
        self.strategy.run(initial_capital_allocation=self.initial_capital)

        times = self.data['time'].to_numpy()
        prices = self.data['price'].to_numpy()
        sizes = self.data['size'].to_numpy()

        for current_time, market_price, market_trade_size in tqdm(
            zip(times, prices, sizes), total=len(times), desc="Running SMM backtest"
        ):
            # Check active BUY orders
            for order_price, order_id in list(self.strategy.active_buy_orders.items()):
                if market_price <= order_price:
                    order_details = self.mock_exchange_orders.get(order_id)
                    if order_details and order_details['status'] == 'open':
                        actual_fill_size = order_details['size']
                        fee = order_price * actual_fill_size * (self.fee_bps / 10000.0)
                        logger.info(f"Backtester: Simulating SMM BUY fill for {order_id} at {order_price}, size {actual_fill_size}, fee {fee:.4f}")

                        self.mock_exchange_orders[order_id]['status'] = 'filled'
                        fill_type = self.strategy.handle_filled_order(order_id, order_price, actual_fill_size, fee)

                        if fill_type == "buy_fill":
                            self.trades_log.append({
                                'time': current_time, 'type': 'buy', 'price': order_price,
                                'size': actual_fill_size, 'pnl': self.strategy.pnl,
                                'inventory': self.strategy.inventory, 'fee': fee,
                                'market_price_at_trade': market_price, 'order_id': order_id
                            })
                        market_trade_size -= actual_fill_size
                        if market_trade_size <= 0: break

            # Check active SELL orders
            for order_price, order_id in list(self.strategy.active_sell_orders.items()):
                if market_price >= order_price:
                    order_details = self.mock_exchange_orders.get(order_id)
                    if order_details and order_details['status'] == 'open':
                        actual_fill_size = order_details['size']
                        fee = order_price * actual_fill_size * (self.fee_bps / 10000.0)
                        logger.info(f"Backtester: Simulating SMM SELL fill for {order_id} at {order_price}, size {actual_fill_size}, fee {fee:.4f}")

                        self.mock_exchange_orders[order_id]['status'] = 'filled'
                        fill_type = self.strategy.handle_filled_order(order_id, order_price, actual_fill_size, fee)

                        if fill_type == "sell_fill":
                            self.trades_log.append({
                                'time': current_time, 'type': 'sell', 'price': order_price,
                                'size': actual_fill_size, 'pnl': self.strategy.pnl,
                                'inventory': self.strategy.inventory, 'fee': fee,
                                'market_price_at_trade': market_price, 'order_id': order_id
                            })
                        market_trade_size -= actual_fill_size
                        if market_trade_size <= 0: break

            self.tick_data_log.append({
                'time': current_time, 'market_price': market_price,
                'pnl': self.strategy.pnl, 'inventory': self.strategy.inventory,
                'active_buys': len(self.strategy.active_buy_orders),
                'active_sells': len(self.strategy.active_sell_orders)
            })

        final_pnl = getattr(self.strategy, 'pnl', 0.0)
        final_inventory = getattr(self.strategy, 'inventory', 0.0)
        logger.info(f"SimpleMarketMakerStrategy backtest finished. Total PnL: {final_pnl:.4f}, Final Inventory: {final_inventory:.4f}")


    def get_results(self) -> dict:
        """
        Returns the results of the backtest.
        """
        params = {
            'market_data_path': self.data_file_path,
            'fee_bps': self.fee_bps,
            'strategy_type': 'SimpleMarketMakerStrategy', # Hardcoded as it's the only one now
            'smm_order_size': self.strategy.order_size,
            'smm_price_levels': self.strategy.price_levels,
            'smm_increment': self.strategy.increment,
            'initial_capital': self.initial_capital
        }

        final_pnl = getattr(self.strategy, 'pnl', 0.0)
        final_inventory = getattr(self.strategy, 'inventory', 0.0)
        if isinstance(final_pnl, float): final_pnl = round(final_pnl, 4)
        if isinstance(final_inventory, float): final_inventory = round(final_inventory, 6)

        return {
            'parameters': params,
            'trades': self.trades_log,
            'tick_data': self.tick_data_log,
            'summary_stats': {
                'final_pnl': final_pnl,
                'total_trades': len(self.trades_log),
                'final_inventory': final_inventory,
            }
        }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="SimpleMarketMakerStrategy Backtester")
    parser.add_argument('--data-file', type=str, required=True, help='Path to the CSV trade data file.')
    parser.add_argument('--fee-bps', type=int, default=10, help='Trading fee in basis points (e.g., 10 for 0.1%)')
    parser.add_argument('--initial-capital', type=float, default=10000.0, help='Initial capital for the strategy.')
    parser.add_argument('--order-size', type=float, default=0.1, help='Order size for the strategy.')
    parser.add_argument('--price-levels', type=str, default="90,95,100,105,110", help='Comma-separated price levels for buy orders (e.g., "90,95,100").')
    parser.add_argument('--increment', type=float, default=10.0, help='Price increment for sell orders.')
    parser.add_argument('--results-file', type=str, default="smm_backtest_results.json", help='Filename for saving detailed results.')
    parser.add_argument('--plot-file', type=str, default="smm_pnl_over_time.png", help='Filename for saving PnL plot.')

    args = parser.parse_args()

    logger.info("Running SimpleMarketMakerStrategy Backtester CLI...")

    trade_data_df = load_trade_data(args.data_file)

    if trade_data_df.empty:
        logger.error(f"Failed to load data from {args.data_file}. Exiting.")
    else:
        logger.info(f"Loaded {len(trade_data_df)} trades from {args.data_file}")

        price_levels = [float(p.strip()) for p in args.price_levels.split(',')]

        strategy_instance = SimpleMarketMakerStrategy(
            exchange=None, # Will be set by backtester
            symbol="TEST/USD", # Example symbol, could be an arg
            order_size=args.order_size,
            price_levels=price_levels,
            increment=args.increment,
            strategy_id="SMM_CLI_Run"
        )

        backtester_instance = Backtester(
            data=trade_data_df,
            strategy=strategy_instance,
            fee_bps=args.fee_bps,
            initial_capital=args.initial_capital
        )

        logger.info(f"\nRunning SMM backtest with order_size={args.order_size}, levels={price_levels}, increment={args.increment}, fee_bps={args.fee_bps}, capital={args.initial_capital}...")
        backtester_instance.run_backtest(data_file_path=args.data_file)

        results = backtester_instance.get_results()
        trades_log = results['trades']
        summary_stats = results['summary_stats']
        parameters = results['parameters']

        logger.info(f"\n--- Backtest Results ---")
        logger.info(f"Parameters: {json.dumps(parameters, indent=2)}")
        logger.info(f"Summary Stats: {json.dumps(summary_stats, indent=2)}")

        if results['tick_data']: # Changed from tick_data_log
            logger.info("\nFirst 5 entries from Tick Data Log:")
            for tick_entry in results['tick_data'][:5]: # Changed from tick_data_log
                logger.info(tick_entry)

        if trades_log:
            logger.info("\nFirst 5 trades executed by the strategy:")
            for trade in trades_log[:5]:
                logger.info(trade)
        else:
            logger.info("\nNo trades were executed by the strategy.")

        try:
            with open(args.results_file, 'w') as f:
                json.dump(results, f, indent=4, cls=DateTimeEncoder)
            logger.info(f"\nFull backtest results saved to {args.results_file}")
        except Exception as e:
            logger.error(f"\nError saving results to JSON: {e}")

        if trades_log:
            try:
                import matplotlib.pyplot as plt
                pnl_over_time = [trade['pnl'] for trade in trades_log]
                trade_times = pd.to_datetime([trade['time'] for trade in trades_log])

                plt.figure(figsize=(12, 7))
                plt.plot(trade_times, pnl_over_time, marker='o', linestyle='-', markersize=4)
                plt.title(f'SMM PnL Over Time - Fees: {args.fee_bps}bps')
                plt.xlabel('Time of Trade')
                plt.ylabel('Cumulative PnL')
                plt.grid(True)
                plt.xticks(rotation=45)
                plt.tight_layout()
                plt.savefig(args.plot_file)
                logger.info(f"\nSaved PnL plot to {args.plot_file}")
            except ImportError:
                logger.warning("\nMatplotlib not installed. Skipping PnL plot.")
            except Exception as e:
                logger.error(f"\nError generating PnL plot: {e}")
        else:
            logger.info("\nNo trades to plot PnL for.")
