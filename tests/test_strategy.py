import pytest
from src.strategy import MarketMakingStrategy

class TestMarketMakingStrategy:

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = MarketMakingStrategy(quote_size=0.1)
        assert strategy.pnl == 0.0, "Initial PnL should be 0.0"
        assert strategy.inventory == 0.0, "Initial inventory should be 0.0"
        assert strategy.current_market_price is None, "Initial market price should be None"
        assert strategy.quote_size == 0.1, "Quote size not set correctly"

    def test_update_market_price(self):
        """Test updating market price."""
        strategy = MarketMakingStrategy(quote_size=0.1)
        strategy.update_market_price(100.0)
        assert strategy.current_market_price == 100.0

    def test_quote_generation_valid_price(self):
        """Test quote generation when market price is available."""
        strategy = MarketMakingStrategy(quote_size=0.1)
        strategy.update_market_price(100.0)

        spread_bps = 10  # 0.1% total spread, so 0.05% on each side
        expected_bid = 100.0 * (1 - (spread_bps / 10000 / 2)) # 100 * (1 - 0.0005) = 100 * 0.9995 = 99.95
        expected_ask = 100.0 * (1 + (spread_bps / 10000 / 2)) # 100 * (1 + 0.0005) = 100 * 1.0005 = 100.05

        bid_quote, ask_quote = strategy.generate_quotes(spread_bps=spread_bps)

        assert bid_quote == pytest.approx(expected_bid), "Bid price calculation incorrect"
        assert ask_quote == pytest.approx(expected_ask), "Ask price calculation incorrect"

    def test_quote_generation_no_price(self):
        """Test quote generation when market price is None."""
        strategy = MarketMakingStrategy(quote_size=0.1)
        # current_market_price is None by default
        bid_quote, ask_quote = strategy.generate_quotes(spread_bps=10)
        assert bid_quote is None, "Bid should be None if market price is not set"
        assert ask_quote is None, "Ask should be None if market price is not set"

    def test_execute_trade_buy(self):
        """Test trade execution logic for a buy order."""
        strategy = MarketMakingStrategy(quote_size=0.1)
        trade_price = 100.0
        trade_size = 0.1 # This is the actual executed size, could be different from quote_size in reality
                         # but for this test, let's assume it's the same as the intended quote_size.

        strategy.execute_trade(trade_price=trade_price, trade_size=trade_size, is_buy_order=True)

        expected_pnl = - (trade_price * trade_size) # - (100.0 * 0.1) = -10.0
        expected_inventory = trade_size             # 0.1

        assert strategy.pnl == pytest.approx(expected_pnl), "PnL calculation incorrect for buy trade"
        assert strategy.inventory == pytest.approx(expected_inventory), "Inventory calculation incorrect for buy trade"

    def test_execute_trade_sell(self):
        """Test trade execution logic for a sell order."""
        strategy = MarketMakingStrategy(quote_size=0.1)
        trade_price = 102.0
        trade_size = 0.1 # Actual executed size

        strategy.execute_trade(trade_price=trade_price, trade_size=trade_size, is_buy_order=False)

        expected_pnl = trade_price * trade_size  # 102.0 * 0.1 = 10.2
        expected_inventory = -trade_size         # -0.1

        assert strategy.pnl == pytest.approx(expected_pnl), "PnL calculation incorrect for sell trade"
        assert strategy.inventory == pytest.approx(expected_inventory), "Inventory calculation incorrect for sell trade"

    def test_pnl_inventory_multiple_trades(self):
        """Test PnL and inventory tracking over multiple trades."""
        strategy = MarketMakingStrategy(quote_size=0.05) # quote_size here is for strategy's own reference
                                                        # execute_trade takes actual traded size.

        # 1. Buy 0.1 at 100
        strategy.execute_trade(trade_price=100.0, trade_size=0.1, is_buy_order=True)
        assert strategy.pnl == pytest.approx(-10.0)
        assert strategy.inventory == pytest.approx(0.1)

        # 2. Sell 0.05 at 102 (partial sell of inventory)
        strategy.execute_trade(trade_price=102.0, trade_size=0.05, is_buy_order=False)
        # PnL = -10.0 + (102.0 * 0.05) = -10.0 + 5.1 = -4.9
        # Inventory = 0.1 - 0.05 = 0.05
        assert strategy.pnl == pytest.approx(-4.9)
        assert strategy.inventory == pytest.approx(0.05)

        # 3. Sell 0.05 at 103 (sell remaining inventory)
        strategy.execute_trade(trade_price=103.0, trade_size=0.05, is_buy_order=False)
        # PnL = -4.9 + (103.0 * 0.05) = -4.9 + 5.15 = 0.25
        # Inventory = 0.05 - 0.05 = 0.0
        assert strategy.pnl == pytest.approx(0.25)
        assert strategy.inventory == pytest.approx(0.0)

        # 4. Sell 0.1 at 105 (go short)
        strategy.execute_trade(trade_price=105.0, trade_size=0.1, is_buy_order=False)
        # PnL = 0.25 + (105.0 * 0.1) = 0.25 + 10.5 = 10.75
        # Inventory = 0.0 - 0.1 = -0.1
        assert strategy.pnl == pytest.approx(10.75)
        assert strategy.inventory == pytest.approx(-0.1)

        # 5. Buy 0.1 at 104 (cover short)
        strategy.execute_trade(trade_price=104.0, trade_size=0.1, is_buy_order=True)
        # PnL = 10.75 - (104.0 * 0.1) = 10.75 - 10.4 = 0.35
        # Inventory = -0.1 + 0.1 = 0.0
        assert strategy.pnl == pytest.approx(0.35)
        assert strategy.inventory == pytest.approx(0.0)
