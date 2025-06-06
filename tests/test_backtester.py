import pytest
import pandas as pd
import json
from src.strategy import MarketMakingStrategy
from src.backtester import Backtester
from src.utils import DateTimeEncoder # Added import

@pytest.fixture
def sample_market_data():
    """Create a sample market data DataFrame for testing."""
    data = {
        'time': pd.to_datetime([
            '2023-01-01 10:00:00', '2023-01-01 10:00:01', '2023-01-01 10:00:02',
            '2023-01-01 10:00:03', '2023-01-01 10:00:04', '2023-01-01 10:00:05'
        ]),
        'price': [100.0, 100.1, 99.9, 100.0, 100.2, 99.8],
        'size':  [0.1,   0.2,  0.1,  0.3,   0.1,   0.2], # Market trade sizes
        # buyer_maker: False means buyer is TAKER (could hit our ASK)
        # buyer_maker: True means buyer is MAKER (seller is TAKER, could hit our BID)
        'buyer_maker': [False, True, False, True, False, True]
    }
    return pd.DataFrame(data)

@pytest.fixture
def basic_strategy():
    """Return a basic MarketMakingStrategy instance."""
    return MarketMakingStrategy(quote_size=0.1) # Default quote size for strategy

class TestBacktester:

    def test_backtest_initialization(self, sample_market_data, basic_strategy):
        """Test Backtester initialization."""
        backtester = Backtester(data=sample_market_data, strategy=basic_strategy)
        assert backtester.data.equals(sample_market_data)
        assert backtester.strategy == basic_strategy
        assert backtester.trades_log == []

    def test_run_backtest_no_trades(self, sample_market_data, basic_strategy):
        """Test a backtest run where no trades are expected."""
        backtester = Backtester(data=sample_market_data, strategy=basic_strategy)

        # Very wide spread, no trades should occur
        backtester.run_backtest(spread_bps=1000, order_size=0.1) # 10% spread

        results_dict = backtester.get_results()
        assert len(results_dict['trades']) == 0, "Trades log should be empty"
        assert results_dict['summary_stats']['total_trades'] == 0
        assert results_dict['summary_stats']['final_pnl'] == 0.0
        assert results_dict['summary_stats']['final_inventory'] == 0.0
        assert basic_strategy.pnl == 0.0, "Strategy PnL should be 0.0" # Redundant with summary_stats but good for direct check
        assert basic_strategy.inventory == 0.0, "Strategy inventory should be 0.0" # Redundant

    def test_run_backtest_with_sell_trade(self, basic_strategy):
        """Test a backtest run that should result in the strategy selling."""
        # Market: Taker buys at 101, hitting our Ask
        market_data_sell_hit = pd.DataFrame({
            'time': pd.to_datetime(['2023-01-01 10:00:00']),
            'price': [101.0], # Market trade price
            'size': [0.5],    # Market trade size
            'buyer_maker': [False] # Buyer is TAKER
        })

        backtester = Backtester(data=market_data_sell_hit, strategy=basic_strategy)

        # Strategy quotes around 100.5: Bid=100.45, Ask=100.55 (with 10bps)
        # Let's set strategy market price to 100.5, and a 10bps spread
        # Strategy will quote Bid = 100.5 * (1 - 0.0005) = 100.4475
        # Strategy will quote Ask = 100.5 * (1 + 0.0005) = 100.5525
        # For the test: we want market_price (101.0) >= ask_quote
        # So, if strategy market price is 100.9, spread 10bps: Ask = 100.9 * (1+0.0005) = 100.95
        # This should trigger a sell.

        # The backtester loop will call update_market_price(tick['price']).
        # So the strategy's market price will be 101.0 for the first tick.
        # With spread_bps=10: Ask = 101.0 * (1 + 0.0005) = 101.0505
        # Market trade at 101.0 is NOT >= 101.0505. No trade.

        # Let's make spread 0 for simplicity of setting up the condition.
        # Strategy market price will be 101.0 (from tick).
        # With spread_bps=0: Ask = 101.0.
        # Market trade at 101.0, buyer_maker=False. Condition: market_price >= ask_quote => 101.0 >= 101.0 (True)

        strategy_order_size = 0.1 # The size the strategy intends to trade
        backtester.run_backtest(spread_bps=0, order_size=strategy_order_size)

        results_dict = backtester.get_results()
        trades_log = results_dict['trades']
        summary_stats = results_dict['summary_stats']

        assert len(trades_log) == 1, "One trade should be logged"
        trade = trades_log[0]
        assert trade['type'] == 'sell', "Trade type should be 'sell'"
        assert trade['price'] == 101.0, "Trade price should be the strategy's ask price"
        assert trade['size'] == strategy_order_size, "Trade size should be strategy's order size"

        # PnL = price * size = 101.0 * 0.1 = 10.1
        # Inventory = -size = -0.1
        assert summary_stats['final_pnl'] == pytest.approx(10.1)
        assert summary_stats['final_inventory'] == pytest.approx(-0.1)
        assert basic_strategy.pnl == pytest.approx(10.1) # Direct check
        assert basic_strategy.inventory == pytest.approx(-0.1) # Direct check

    def test_run_backtest_with_buy_trade(self, basic_strategy):
        """Test a backtest run that should result in the strategy buying."""
        # Market: Taker sells at 99, hitting our Bid
        market_data_buy_hit = pd.DataFrame({
            'time': pd.to_datetime(['2023-01-01 10:00:00']),
            'price': [99.0],   # Market trade price
            'size': [0.5],     # Market trade size
            'buyer_maker': [True] # Seller is TAKER (buyer is MAKER)
        })

        backtester = Backtester(data=market_data_buy_hit, strategy=basic_strategy)

        # Strategy market price will be 99.0 (from tick).
        # With spread_bps=0: Bid = 99.0.
        # Market trade at 99.0, buyer_maker=True. Condition: market_price <= bid_quote => 99.0 <= 99.0 (True)

        strategy_order_size = 0.1
        backtester.run_backtest(spread_bps=0, order_size=strategy_order_size)

        results_dict = backtester.get_results()
        trades_log = results_dict['trades']
        summary_stats = results_dict['summary_stats']

        assert len(trades_log) == 1, "One trade should be logged"
        trade = trades_log[0]
        assert trade['type'] == 'buy', "Trade type should be 'buy'"
        assert trade['price'] == 99.0, "Trade price should be the strategy's bid price"
        assert trade['size'] == strategy_order_size, "Trade size should be strategy's order size"

        # PnL = - (price * size) = - (99.0 * 0.1) = -9.9
        # Inventory = size = 0.1
        assert summary_stats['final_pnl'] == pytest.approx(-9.9)
        assert summary_stats['final_inventory'] == pytest.approx(0.1)
        assert basic_strategy.pnl == pytest.approx(-9.9) # Direct check
        assert basic_strategy.inventory == pytest.approx(0.1) # Direct check

    def test_run_backtest_multiple_trades_alternating(self, basic_strategy, sample_market_data):
        """Test with alternating buy/sell based on sample_market_data and zero spread."""
        # Using sample_market_data, which has alternating buyer_maker flags.
        # With 0 spread, every tick should result in a trade.
        backtester = Backtester(data=sample_market_data, strategy=basic_strategy)
        strategy_order_size = 0.05 # Let's use a different size for this test

        backtester.run_backtest(spread_bps=0, order_size=strategy_order_size)

        results_dict = backtester.get_results()
        trades_log = results_dict['trades']
        summary_stats = results_dict['summary_stats']

        assert len(trades_log) == len(sample_market_data), "Should trade on every tick with 0 spread"
        assert summary_stats['total_trades'] == len(sample_market_data)

        # Manually calculate expected PnL and inventory
        # Tick 0: price=100.0, buyer_maker=False (SELL) -> PnL += 100.0 * 0.05 = 5.0; Inv -= 0.05
        # Tick 1: price=100.1, buyer_maker=True  (BUY)  -> PnL -= 100.1 * 0.05 = -5.005; Inv += 0.05
        # Tick 2: price=99.9,  buyer_maker=False (SELL) -> PnL += 99.9 * 0.05 = 4.995; Inv -= 0.05
        # Tick 3: price=100.0, buyer_maker=True  (BUY)  -> PnL -= 100.0 * 0.05 = -5.0; Inv += 0.05
        # Tick 4: price=100.2, buyer_maker=False (SELL) -> PnL += 100.2 * 0.05 = 5.01; Inv -= 0.05
        # Tick 5: price=99.8,  buyer_maker=True  (BUY)  -> PnL -= 99.8 * 0.05 = -4.99; Inv += 0.05

        # Expected PnL = 5.0 - 5.005 + 4.995 - 5.0 + 5.01 - 4.99 = 0.01
        # Expected Inventory = -0.05 + 0.05 - 0.05 + 0.05 - 0.05 + 0.05 = 0.0

        assert summary_stats['final_pnl'] == pytest.approx(0.01)
        assert summary_stats['final_inventory'] == pytest.approx(0.0)
        assert basic_strategy.pnl == pytest.approx(0.01) # Direct check
        assert basic_strategy.inventory == pytest.approx(0.0) # Direct check

        assert trades_log[0]['type'] == 'sell'
        assert trades_log[0]['price'] == sample_market_data['price'][0]
        assert trades_log[1]['type'] == 'buy'
        assert trades_log[1]['price'] == sample_market_data['price'][1]
        # ... and so on

    def test_backtest_order_size_respected(self):
        """Test that the order_size parameter in run_backtest correctly sets strategy's quote_size."""
        strategy = MarketMakingStrategy(quote_size=0.99) # Initial dummy size

        # Market data that will cause one trade
        market_data = pd.DataFrame({
            'time': pd.to_datetime(['2023-01-01 10:00:00']),
            'price': [100.0], 'size': [1.0], 'buyer_maker': [False]
        })
        backtester = Backtester(data=market_data, strategy=strategy)

        test_order_size = 0.07
        backtester.run_backtest(spread_bps=0, order_size=test_order_size)

        results_dict = backtester.get_results()
        trades_log = results_dict['trades']
        summary_stats = results_dict['summary_stats']

        assert strategy.quote_size == test_order_size, "Strategy's quote_size not updated by backtester"
        assert len(trades_log) == 1
        assert trades_log[0]['size'] == test_order_size, "Logged trade size incorrect"
        assert summary_stats['final_pnl'] == pytest.approx(100.0 * test_order_size)
        assert summary_stats['final_inventory'] == pytest.approx(-test_order_size)
        assert strategy.pnl == pytest.approx(100.0 * test_order_size) # Direct check
        assert strategy.inventory == pytest.approx(-test_order_size) # Direct check

    def test_get_results_structure_and_new_fields(self, sample_market_data, basic_strategy):
        """Test the structure of get_results and the presence of new fields."""
        test_spread_bps = 20  # e.g., 0.2%
        test_order_size = 0.05

        backtester = Backtester(data=sample_market_data, strategy=basic_strategy)
        # Run with some trades expected to populate logs, non-zero spread
        backtester.run_backtest(spread_bps=test_spread_bps, order_size=test_order_size)

        results = backtester.get_results()

        assert isinstance(results, dict), "get_results should return a dictionary"

        # Check top-level keys
        expected_top_keys = ['parameters', 'trades', 'tick_data', 'summary_stats']
        for key in expected_top_keys:
            assert key in results, f"Missing top-level key '{key}' in results"

        # Check 'parameters'
        assert isinstance(results['parameters'], dict)
        assert 'spread_bps' in results['parameters']
        assert results['parameters']['spread_bps'] == test_spread_bps
        assert 'order_size' in results['parameters']
        assert results['parameters']['order_size'] == test_order_size

        # Check 'summary_stats'
        assert isinstance(results['summary_stats'], dict)
        expected_summary_keys = ['final_pnl', 'total_trades', 'final_inventory']
        for key in expected_summary_keys:
            assert key in results['summary_stats'], f"Missing key '{key}' in summary_stats"
        assert isinstance(results['summary_stats']['final_pnl'], float)
        assert isinstance(results['summary_stats']['total_trades'], int)
        assert isinstance(results['summary_stats']['final_inventory'], float)


        # Check 'trades' list and content of its dictionaries
        assert isinstance(results['trades'], list)
        if results['trades']: # If there are any trades
            first_trade = results['trades'][0]
            assert isinstance(first_trade, dict)
            # Check for essential existing keys and new keys
            expected_trade_keys = ['time', 'type', 'price', 'size', 'pnl', 'inventory',
                                   'market_price_at_trade', 'bid_at_trade', 'ask_at_trade']
            for key in expected_trade_keys:
                assert key in first_trade, f"Trade entry missing key '{key}'"

            assert 'bid_at_trade' in first_trade, "trades log missing 'bid_at_trade'"
            assert 'ask_at_trade' in first_trade, "trades log missing 'ask_at_trade'"
            # Values for bid/ask at trade can be float or None
            assert isinstance(first_trade['bid_at_trade'], (float, type(None)))
            assert isinstance(first_trade['ask_at_trade'], (float, type(None)))

        # Check 'tick_data' list and content of its dictionaries
        assert isinstance(results['tick_data'], list)
        # Tick data should always be present, one entry per input market data tick
        assert len(results['tick_data']) == len(sample_market_data), \
            f"Expected {len(sample_market_data)} tick data entries, got {len(results['tick_data'])}"

        if results['tick_data']:
            first_tick = results['tick_data'][0]
            assert isinstance(first_tick, dict)
            expected_tick_keys = ['time', 'market_price', 'bid_quote', 'ask_quote']
            for key in expected_tick_keys:
                assert key in first_tick, f"Tick data entry missing key '{key}'"

            # Check types of values in tick_data
            assert isinstance(first_tick['market_price'], float)
            # Quotes can be None if strategy doesn't quote (e.g. market price missing at start for strategy)
            assert isinstance(first_tick['bid_quote'], (float, type(None)))
            assert isinstance(first_tick['ask_quote'], (float, type(None)))
            # 'time' is pd.Timestamp from fixture, check if it's still that or string
            assert isinstance(first_tick['time'], pd.Timestamp) # Based on sample_market_data fixture

    def test_results_are_json_serializable(self, sample_market_data, basic_strategy):
        """Test that the results dictionary, after datetime conversion, is JSON serializable."""
        backtester = Backtester(data=sample_market_data, strategy=basic_strategy)
        backtester.run_backtest(spread_bps=10, order_size=0.1) # Run a basic backtest

        results = backtester.get_results()

        # Manual datetime conversion logic removed, DateTimeEncoder should handle it.

        # Attempt to serialize to JSON using DateTimeEncoder
        try:
            json.dumps(results, cls=DateTimeEncoder)
            serializable = True
        except TypeError as e: # Catch the specific error for better debugging
            serializable = False
            print(f"TypeError during JSON serialization in test: {e}") # Optional: print error

        assert serializable, "Backtest results are not JSON serializable using DateTimeEncoder."
