import argparse
import json

import pandas as pd
from tqdm import tqdm

from src.data_loader import load_trade_data  # For example usage
from src.strategy import MarketMakingStrategy
from src.utils import DateTimeEncoder # Added import


class Backtester:
    """
    Simulates a market making strategy against historical trade data.
    """

    def __init__(self, data: pd.DataFrame, strategy: MarketMakingStrategy):
        """
        Initializes the Backtester.

        Args:
            data: A pandas DataFrame containing historical trade data (e.g., from data_loader).
                  Expected columns: 'time', 'price', 'size', 'buyer_maker'.
            strategy: An instance of a trading strategy (e.g., MarketMakingStrategy).
        """
        self.data = data
        self.strategy = strategy
        self.trades_log = []
        self.tick_data_log = []
        self.current_spread_bps: int | None = None
        self.current_order_size: float | None = None
        self.data_file_path = None

    def run_backtest(self, spread_bps: int, order_size: float, data_file_path: str = None):
        """
        Runs the backtest simulation.

        Iterates through the historical data, updating the strategy and simulating trades.

        Args:
            spread_bps: The spread in basis points for the strategy to use.
            order_size: The size of orders the strategy should place.
            data_file_path: The path to the market data file.
        """
        self.current_spread_bps = spread_bps
        self.current_order_size = order_size
        self.data_file_path = data_file_path
        self.strategy.quote_size = order_size # Set the order size for the strategy
        self.trades_log = [] # Reset log for new backtest run
        self.tick_data_log = [] # Reset tick data log for new backtest run

        if self.data.empty:
            print("Data is empty, cannot run backtest.")
            return

        # Extract columns as NumPy arrays for performance
        times = self.data['time'].to_numpy()
        prices = self.data['price'].to_numpy()
        buyer_makers = self.data['buyer_maker'].to_numpy()

        total_ticks = len(self.data)
        # Iterate using zip over NumPy arrays
        for current_time, market_price, buyer_maker_from_data in tqdm(zip(times, prices, buyer_makers), total=total_ticks, desc="Running backtest"):
            # Update strategy with current market price
            self.strategy.update_market_price(market_price)

            # Strategy generates new quotes
            bid_quote, ask_quote = self.strategy.generate_quotes(spread_bps=spread_bps)

            # Log tick data
            self.tick_data_log.append({
                'time': current_time,
                'market_price': market_price,
                'bid_quote': self.strategy.last_bid_quote,
                'ask_quote': self.strategy.last_ask_quote
            })

            # if index < 5 or index > len(self.data) - 6: # Debug print for first/last few ticks
            #     print(f"TICK {index}: Time={current_time}, MarketPrice={market_price:.2f}, BuyerMaker={buyer_maker_from_data}, BidQuote={bid_quote:.2f} AskQuote={ask_quote:.2f}" if bid_quote else f"TICK {index}: MarketPrice={market_price:.2f}, No quotes")

            if bid_quote is None or ask_quote is None:
                # Strategy might not have enough info to quote yet (e.g., at the very start)
                # or decided not to quote based on its logic (although current strategy always quotes if market price is available)
                continue

            # Trade Logic:
            # Our strategy always acts as a maker.
            # We check if the current trade from the data (taker) would fill our resting orders.

            # Check if our ASK (strategy's sell order) is hit:
            # This happens if a TAKER BUYS in the market at a price at or above our ask.
            # In the data, a taker buy means buyer_maker is False.
            if not buyer_maker_from_data and market_price >= ask_quote:
                # Our sell order is hit
                self.strategy.execute_trade(trade_price=ask_quote,
                                            trade_size=self.strategy.quote_size,
                                            is_buy_order=False) # Strategy sells
                self.trades_log.append({
                    'time': current_time,
                    'type': 'sell',
                    'price': ask_quote,
                    'size': self.strategy.quote_size,
                    'pnl': self.strategy.pnl,
                    'inventory': self.strategy.inventory,
                    'market_price_at_trade': market_price, # Market price that triggered the trade
                    'bid_at_trade': self.strategy.last_bid_quote,
                    'ask_at_trade': self.strategy.last_ask_quote
                })

            # Check if our BID (strategy's buy order) is hit:
            # This happens if a TAKER SELLS in the market at a price at or below our bid.
            # In the data, a taker sell means buyer_maker is True (buyer was maker, so seller was taker).
            elif buyer_maker_from_data and market_price <= bid_quote:
                # Our buy order is hit
                self.strategy.execute_trade(trade_price=bid_quote,
                                            trade_size=self.strategy.quote_size,
                                            is_buy_order=True) # Strategy buys
                self.trades_log.append({
                    'time': current_time,
                    'type': 'buy',
                    'price': bid_quote,
                    'size': self.strategy.quote_size,
                    'pnl': self.strategy.pnl,
                    'inventory': self.strategy.inventory,
                    'market_price_at_trade': market_price, # Market price that triggered the trade
                    'bid_at_trade': self.strategy.last_bid_quote,
                    'ask_at_trade': self.strategy.last_ask_quote
                })

        print(f"Backtest finished. Total PnL: {self.strategy.pnl:.2f}, Final Inventory: {self.strategy.inventory:.4f}")

    def get_results(self) -> dict:
        """
        Returns the results of the backtest.

        Returns:
            A dictionary containing parameters, trades log, tick data log, and summary statistics.
        """
        return {
            'parameters': {
                'spread_bps': self.current_spread_bps,
                'order_size': self.current_order_size,
                'market_data_path': self.data_file_path,
            },
            'trades': self.trades_log,
            'tick_data': self.tick_data_log,
            'summary_stats': {
                'final_pnl': self.strategy.pnl,
                'total_trades': len(self.trades_log),
                'final_inventory': self.strategy.inventory,
            }
        }

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Market Making Strategy Backtester")
    parser.add_argument('--data-file', type=str, required=True, help='Path to the CSV trade data file.')

    args = parser.parse_args()

    # Example Usage
    print("Running Backtester Example...")

    # 1. Load sample data
    data_file = args.data_file
    trade_data_df = load_trade_data(data_file)

    if trade_data_df.empty:
        print(f"Failed to load data from {data_file}. Exiting example.")
    else:
        print(f"Loaded {len(trade_data_df)} trades from {data_file}")

        # 2. Initialize the MarketMakingStrategy
        # The initial quote_size here is just a placeholder, run_backtest will set it.
        strategy_instance = MarketMakingStrategy(quote_size=0.01)

        # 3. Initialize the Backtester
        backtester_instance = Backtester(data=trade_data_df, strategy=strategy_instance)

        # 4. Run the backtest
        # Parameters for the backtest run:
        test_spread_bps = 0  # Zero spread to test execution logic
        test_order_size = 0.01 # Strategy will trade 0.01 units of base asset per trade

        print(f"\nRunning backtest with spread_bps={test_spread_bps} and order_size={test_order_size}...")
        backtester_instance.run_backtest(spread_bps=test_spread_bps, order_size=test_order_size, data_file_path=data_file)

        # 5. Get and print results
        results = backtester_instance.get_results()
        trades_log = results['trades']
        tick_data_log = results['tick_data']
        summary_stats = results['summary_stats']
        parameters = results['parameters']

        print(f"\n--- Backtest Results ---")
        print(f"Parameters: {parameters}")
        print(f"Summary Stats: {summary_stats}")

        if tick_data_log:
            print("\nFirst 5 entries from Tick Data Log:")
            for tick_entry in tick_data_log[:5]:
                print(tick_entry)
        else:
            print("\nTick Data Log is empty.")

        if trades_log:
            print("\nFirst 5 trades executed by the strategy:")
            for trade in trades_log[:5]:
                print(trade)
        else:
            print("\nNo trades were executed by the strategy.")

        # 6. Save full results to JSON
        # Manual datetime conversion loops removed. DateTimeEncoder will handle it.

        results_file_name = "backtest_results.json"
        try:
            with open(results_file_name, 'w') as f:
                json.dump(results, f, indent=4, default=str)
            print(f"\nFull backtest results saved to {results_file_name}")
        except Exception as e:
            print(f"\nError saving results to JSON: {e}")

        # 7. Example of how one might plot PnL over time (if matplotlib is installed)
        try:
            import matplotlib.pyplot as plt
            if trades_log:
                pnl_over_time = [trade['pnl'] for trade in trades_log]
                trade_times = [trade['time'] for trade in trades_log] # Assuming time is suitable for plotting
                plt.figure(figsize=(10, 6))
                plt.plot(trade_times, pnl_over_time, marker='o', linestyle='-')
                plt.title('Strategy PnL Over Time')
                plt.xlabel('Time of Trade')
                plt.ylabel('Cumulative PnL')
                plt.grid(True)
                plt.savefig('pnl_over_time.png')
                print("\nSaved PnL plot to pnl_over_time.png")
            else:
                print("\nNo trades to plot PnL.")
        except ImportError:
            print("\nMatplotlib not installed. Skipping PnL plot.")
        except Exception as e:
            print(f"\nError generating plot: {e}")
