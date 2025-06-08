import pytest
import pandas as pd
import json
from src.strategy import SimpleMarketMakerStrategy # MarketMakingStrategy import removed
from src.backtester import Backtester
from src.utils import DateTimeEncoder
from unittest.mock import MagicMock

@pytest.fixture
def sample_market_data():
    """Create a sample market data DataFrame for testing."""
    data = {
        'time': pd.to_datetime([
            '2023-01-01 10:00:00', '2023-01-01 10:00:01', '2023-01-01 10:00:02',
            '2023-01-01 10:00:03', '2023-01-01 10:00:04', '2023-01-01 10:00:05',
            '2023-01-01 10:00:06', '2023-01-01 10:00:07', # Added more data for SMM
        ]),
        'price': [100.0, 100.1, 99.9, 100.0, 100.2, 99.8, 95.0, 105.0],
        'size':  [0.1,   0.2,  0.1,  0.3,   0.1,   0.2, 0.5, 0.5], # Market trade sizes
        # buyer_maker: False means buyer is TAKER (could hit our ASK for MMS)
        # buyer_maker: True means buyer is MAKER (seller is TAKER, could hit our BID for MMS)
        # For SMM, this field is not directly used by backtester fill logic, but part of data.
        'buyer_maker': [False, True, False, True, False, True, True, False]
    }
    return pd.DataFrame(data)

# mms_strategy_fixture removed

@pytest.fixture
def smm_strategy_fixture():
    """Return a basic SimpleMarketMakerStrategy instance."""
    # SMM needs a mock exchange during its own instantiation if we were to call its methods directly.
    # However, when used with Backtester, the Backtester itself becomes the exchange.
    # So, for fixture used purely by Backtester, `exchange=None` is fine initially.
    return SimpleMarketMakerStrategy(
        exchange=None, # Will be replaced by Backtester instance
        symbol="TEST/USD",
        order_size=0.1,
        price_levels=[90.0, 95.0, 98.0], # SMM specific
        increment=5.0,                  # SMM specific
        strategy_id="SMM_BT_Test"
    )

# TestBacktesterWithMMS class removed

class TestBacktesterWithSMM: # Renamed from TestBacktesterWithSMM to be the main test class
    def test_smm_initialization_with_backtester(self, sample_market_data, smm_strategy_fixture):
        initial_cap = 5000.0
        fee_bps = 5
        backtester = Backtester(data=sample_market_data, strategy=smm_strategy_fixture, fee_bps=fee_bps, initial_capital=initial_cap)

        assert backtester.strategy == smm_strategy_fixture
        assert backtester.fee_bps == fee_bps
        assert backtester.initial_capital == initial_cap
        # Strategy's exchange is set by the backtester during run_backtest

    def test_run_backtest_smm_simple_fill_and_fee_check(self, sample_market_data, smm_strategy_fixture):
        """ Test SMM gets a single buy order filled, then a single sell. """
        # Market data: price drops to 90 (SMM buy), then rises to 95 (SMM sell for 90+5)
        smm_market_data = pd.DataFrame({
            'time': pd.to_datetime(['2023-01-01 10:00:00', '2023-01-01 10:00:01', '2023-01-01 10:00:02']),
            'price': [92.0, 90.0, 95.0], # Initial, Buy Fill at 90, Sell Fill at 95
            'size':  [0.1, 0.5, 0.5],   # Market trade sizes
            'buyer_maker': [False, True, False] # Not directly used by SMM fill logic in backtester
        })

        smm_strategy_fixture.price_levels = [90.0] # Focus on one level
        smm_strategy_fixture.increment = 5.0       # Sell at 90+5=95
        smm_strategy_fixture.order_size = 0.1

        initial_capital = 100.0 # Enough for one order: 90 * 0.1 = 9
        fee_rate_bps = 10 # 0.1%

        backtester = Backtester(data=smm_market_data, strategy=smm_strategy_fixture, fee_bps=fee_rate_bps, initial_capital=initial_capital)
        backtester.run_backtest(data_file_path="test_smm_run.csv")

        results = backtester.get_results()
        trades = results['trades']
        summary = results['summary_stats']

        assert len(trades) == 2

        # Trade 1: Buy at 90
        buy_trade = trades[0]
        assert buy_trade['type'] == 'buy'
        assert buy_trade['price'] == 90.0
        assert buy_trade['size'] == 0.1
        buy_fee = 90.0 * 0.1 * (fee_rate_bps / 10000.0)
        assert buy_trade['fee'] == pytest.approx(buy_fee) # 9.0 * 0.001 = 0.009

        # Trade 2: Sell at 95
        sell_trade = trades[1]
        assert sell_trade['type'] == 'sell'
        assert sell_trade['price'] == 95.0
        assert sell_trade['size'] == 0.1
        sell_fee = 95.0 * 0.1 * (fee_rate_bps / 10000.0)
        assert sell_trade['fee'] == pytest.approx(sell_fee) # 9.5 * 0.001 = 0.0095

        expected_pnl = (-(90.0 * 0.1) - buy_fee) + ((95.0 * 0.1) - sell_fee)
        # PnL = (-9.0 - 0.009) + (9.5 - 0.0095) = -9.009 + 9.4905 = 0.4815
        assert summary['final_pnl'] == pytest.approx(expected_pnl)
        assert summary['final_inventory'] == pytest.approx(0.0)

        # Check strategy's internal state
        assert smm_strategy_fixture.pnl == pytest.approx(expected_pnl)
        assert smm_strategy_fixture.inventory == pytest.approx(0.0)
        assert len(smm_strategy_fixture.active_buy_orders) == 1
        assert len(smm_strategy_fixture.active_sell_orders) == 0

    def test_smm_max_entry_points_respected_in_backtest(self, sample_market_data, smm_strategy_fixture):
        smm_strategy_fixture.price_levels = [90, 92, 95]
        smm_strategy_fixture.order_size = 0.1
        # Capital for 1 order at 90 (cost 9). initial_capital = 10 should allow 1 order.
        initial_capital = 10.0

        backtester = Backtester(data=sample_market_data.iloc[:1], strategy=smm_strategy_fixture, initial_capital=initial_capital)
        backtester.run_backtest()

        # Strategy's max_entry_points is updated inside its run() method, which is called by backtester.
        assert smm_strategy_fixture.max_entry_points == 1
        assert len(smm_strategy_fixture.active_buy_orders) == 1 # Only one order should be placed
        assert 90.0 in smm_strategy_fixture.active_buy_orders

    def test_smm_results_structure_and_serialization(self, sample_market_data, smm_strategy_fixture):
        """Test SMM results structure and JSON serializability."""
        fee_bps_test = 15
        initial_capital_test = 1200.0
        backtester = Backtester(data=sample_market_data, strategy=smm_strategy_fixture, fee_bps=fee_bps_test, initial_capital=initial_capital_test)
        backtester.run_backtest(data_file_path="dummy_path.csv") # Provide a path for parameters check
        results = backtester.get_results()

        assert 'parameters' in results
        params = results['parameters']
        assert params['strategy_type'] == 'SimpleMarketMakerStrategy'
        assert params['smm_order_size'] == smm_strategy_fixture.order_size
        assert params['fee_bps'] == fee_bps_test
        assert params['initial_capital'] == initial_capital_test
        assert params['market_data_path'] == "dummy_path.csv"

        assert 'summary_stats' in results
        assert 'final_pnl' in results['summary_stats']
        assert 'total_trades' in results['summary_stats']
        assert 'final_inventory' in results['summary_stats']


        if results['trades']:
            first_trade = results['trades'][0]
            assert 'fee' in first_trade
            assert 'order_id' in first_trade

        if results['tick_data']:
            first_tick = results['tick_data'][0]
            assert 'active_buys' in first_tick
            assert 'active_sells' in first_tick
            assert 'pnl' in first_tick # SMM tick data now logs strategy PnL per tick
            assert 'inventory' in first_tick

        # Test JSON serialization
        try:
            json.dumps(results, cls=DateTimeEncoder)
        except Exception as e:
            pytest.fail(f"SMM results not JSON serializable: {e}")
