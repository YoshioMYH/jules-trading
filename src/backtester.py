import argparse

import pandas as pd

from src.data_loader import load_trade_data  # For example usage
from src.strategy import MarketMakingStrategy


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

    def run_backtest(self, spread_bps: int, order_size: float):
        """
        Runs the backtest simulation.

        Iterates through the historical data, updating the strategy and simulating trades.

        Args:
            spread_bps: The spread in basis points for the strategy to use.
            order_size: The size of orders the strategy should place.
        """
        self.strategy.quote_size = order_size # Set the order size for the strategy
        self.trades_log = [] # Reset log for new backtest run

        if self.data.empty:
            print("Data is empty, cannot run backtest.")
            return

        for index, tick in self.data.iterrows():
            current_time = tick['time']
            market_price = tick['price']
            # trade_size_from_data = tick['size'] # Size of the trade in the data
            buyer_maker_from_data = tick['buyer_maker'] # Who was the maker in the data's trade

            # Update strategy with current market price
            self.strategy.update_market_price(market_price)

            # Strategy generates new quotes
            bid_quote, ask_quote = self.strategy.generate_quotes(spread_bps=spread_bps)

            # if index < 5 or index > len(self.data) - 6: # Debug print for first/last few ticks
            #     print(f"TICK {index}: Time={current_time}, MarketPrice={market_price:.2f}, BuyerMaker={buyer_maker_from_data}, BidQuote={bid_quote:.2f} AskQuote={ask_quote:.2f}" if bid_quote else f"TICK {index}: MarketPrice={market_price:.2f}, No quotes")

            if bid_quote is None or ask_quote is None:
                # Strategy might not have enough info to quote yet (e.g., at the very start)
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
                    'market_price_at_trade': market_price # Market price that triggered the trade
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
                    'market_price_at_trade': market_price # Market price that triggered the trade
                })

        print(f"Backtest finished. Total PnL: {self.strategy.pnl:.2f}, Final Inventory: {self.strategy.inventory:.4f}")

    def get_results(self) -> list[dict]:
        """
        Returns the log of simulated trades.

        Returns:
            A list of dictionaries, where each dictionary represents a trade execution.
        """
        return self.trades_log

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Market Making Strategy Backtester")
    parser.add_argument('--data_file', type=str, required=True, help='Path to the CSV trade data file.')

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
        backtester_instance.run_backtest(spread_bps=test_spread_bps, order_size=test_order_size)

        # 5. Get and print results
        results = backtester_instance.get_results()
        print(f"\nNumber of trades executed by strategy: {len(results)}")

        if results:
            print("First 5 trades executed by the strategy:")
            for trade in results[:5]:
                print(trade)

        print(f"\nFinal PnL from strategy: {backtester_instance.strategy.pnl:.2f}")
        print(f"Final Inventory from strategy: {backtester_instance.strategy.inventory:.4f}")

        # Example of how one might plot PnL over time (if matplotlib is installed)
        try:
            import matplotlib.pyplot as plt
            pnl_over_time = [trade['pnl'] for trade in results]
            trade_times = [trade['time'] for trade in results]
            if pnl_over_time:
                plt.figure(figsize=(10, 6))
                plt.plot(trade_times, pnl_over_time, marker='o', linestyle='-')
                plt.title('Strategy PnL Over Time')
                plt.xlabel('Time of Trade')
                plt.ylabel('Cumulative PnL')
                plt.grid(True)
                plt.savefig('pnl_over_time.png')
                print("\nSaved PnL plot to pnl_over_time.png")
            else:
                print("\nNo trades to plot.")
        except ImportError:
            print("\nMatplotlib not installed. Skipping PnL plot.")
        except Exception as e:
            print(f"\nError generating plot: {e}")
