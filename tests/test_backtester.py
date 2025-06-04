import pytest
import pandas as pd
from src.strategy import MarketMakingStrategy
from src.backtester import Backtester

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

        assert len(backtester.get_results()) == 0, "Trades log should be empty"
        assert basic_strategy.pnl == 0.0, "Strategy PnL should be 0.0"
        assert basic_strategy.inventory == 0.0, "Strategy inventory should be 0.0"

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

        results = backtester.get_results()
        assert len(results) == 1, "One trade should be logged"
        trade = results[0]
        assert trade['type'] == 'sell', "Trade type should be 'sell'"
        assert trade['price'] == 101.0, "Trade price should be the strategy's ask price"
        assert trade['size'] == strategy_order_size, "Trade size should be strategy's order size"

        # PnL = price * size = 101.0 * 0.1 = 10.1
        # Inventory = -size = -0.1
        assert basic_strategy.pnl == pytest.approx(10.1)
        assert basic_strategy.inventory == pytest.approx(-0.1)

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

        results = backtester.get_results()
        assert len(results) == 1, "One trade should be logged"
        trade = results[0]
        assert trade['type'] == 'buy', "Trade type should be 'buy'"
        assert trade['price'] == 99.0, "Trade price should be the strategy's bid price"
        assert trade['size'] == strategy_order_size, "Trade size should be strategy's order size"

        # PnL = - (price * size) = - (99.0 * 0.1) = -9.9
        # Inventory = size = 0.1
        assert basic_strategy.pnl == pytest.approx(-9.9)
        assert basic_strategy.inventory == pytest.approx(0.1)

    def test_run_backtest_multiple_trades_alternating(self, basic_strategy, sample_market_data):
        """Test with alternating buy/sell based on sample_market_data and zero spread."""
        # Using sample_market_data, which has alternating buyer_maker flags.
        # With 0 spread, every tick should result in a trade.
        backtester = Backtester(data=sample_market_data, strategy=basic_strategy)
        strategy_order_size = 0.05 # Let's use a different size for this test

        backtester.run_backtest(spread_bps=0, order_size=strategy_order_size)

        results = backtester.get_results()
        assert len(results) == len(sample_market_data), "Should trade on every tick with 0 spread"

        expected_pnl = 0
        expected_inventory = 0

        # Manually calculate expected PnL and inventory
        # Tick 0: price=100.0, buyer_maker=False (SELL) -> PnL += 100.0 * 0.05 = 5.0; Inv -= 0.05
        # Tick 1: price=100.1, buyer_maker=True  (BUY)  -> PnL -= 100.1 * 0.05 = -5.005; Inv += 0.05
        # Tick 2: price=99.9,  buyer_maker=False (SELL) -> PnL += 99.9 * 0.05 = 4.995; Inv -= 0.05
        # Tick 3: price=100.0, buyer_maker=True  (BUY)  -> PnL -= 100.0 * 0.05 = -5.0; Inv += 0.05
        # Tick 4: price=100.2, buyer_maker=False (SELL) -> PnL += 100.2 * 0.05 = 5.01; Inv -= 0.05
        # Tick 5: price=99.8,  buyer_maker=True  (BUY)  -> PnL -= 99.8 * 0.05 = -4.99; Inv += 0.05

        # Expected PnL = 5.0 - 5.005 + 4.995 - 5.0 + 5.01 - 4.99 = 0.01
        # Expected Inventory = -0.05 + 0.05 - 0.05 + 0.05 - 0.05 + 0.05 = 0.0

        assert basic_strategy.pnl == pytest.approx(0.01)
        assert basic_strategy.inventory == pytest.approx(0.0)

        assert results[0]['type'] == 'sell'
        assert results[0]['price'] == sample_market_data['price'][0]
        assert results[1]['type'] == 'buy'
        assert results[1]['price'] == sample_market_data['price'][1]
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

        assert strategy.quote_size == test_order_size, "Strategy's quote_size not updated by backtester"
        assert len(backtester.get_results()) == 1
        assert backtester.get_results()[0]['size'] == test_order_size, "Logged trade size incorrect"
        assert strategy.pnl == pytest.approx(100.0 * test_order_size)
        assert strategy.inventory == pytest.approx(-test_order_size)
