import pytest
from src.grid_strategy import GridTradingStrategy

# Helper rounding functions for tests
def round_to_2_decimals(price):
    return round(price, 2)

def round_to_0_50(price):
    # Standard "round half up" for .5 cases, more predictable for tests
    # For example, 2.5 -> 3, 3.5 -> 4
    # For rounding to nearest 0.50:
    # 1.24 -> 1.0, 1.25 -> 1.5, 1.75 -> 2.0
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(price * 2)).quantize(Decimal('1'), rounding=ROUND_HALF_UP) / Decimal('2'))

def round_to_whole(price):
    return round(price)

class TestGridTradingStrategy:

    def test_strategy_initialization_basic(self):
        """Test basic strategy initialization with new parameters."""
        initial_balance = 1000.0
        strategy = GridTradingStrategy(
            quote_size=0.1,
            grid_levels=5,
            grid_spacing=0.5,
            price_rounding_rule=round_to_2_decimals,
            fees_bps=10,
            initial_balance=initial_balance
        )
        assert strategy.quote_size == 0.1
        assert strategy.grid_levels == 5
        assert strategy.grid_spacing == 0.5
        assert strategy.fees_bps == 10
        assert strategy.initial_balance == initial_balance
        assert strategy.current_balance == initial_balance
        assert strategy.pnl == 0.0
        assert strategy.inventory == 0.0
        assert strategy.current_market_price is None
        assert strategy.active_buy_orders == []
        assert strategy.pending_sell_orders == []

    def test_update_market_price(self):
        """Test updating market price."""
        strategy = GridTradingStrategy(0.1, 5, 0.5, round_to_2_decimals, 10, initial_balance=1000.0)
        strategy.update_market_price(100.0)
        assert strategy.current_market_price == 100.0

    def test_initial_buy_order_placement(self):
        """Test initial placement of buy orders."""
        strategy = GridTradingStrategy(
            quote_size=0.1,
            grid_levels=3,
            grid_spacing=1.0,
            price_rounding_rule=round_to_2_decimals,
            fees_bps=0,
            initial_balance=1000.0
        )
        strategy.update_market_price(100.0)

        # Initial call to generate_quotes should place buy orders
        active_buy_prices, active_sell_prices = strategy.generate_quotes()

        assert len(strategy.active_buy_orders) == 3, "Should place 3 buy orders"
        assert len(active_buy_prices) == 3, "Should return 3 buy prices"
        assert active_sell_prices == [], "No sell orders should be active initially"
        assert strategy.pending_sell_orders == [], "No sell orders should be pending initially"

        expected_buy_prices = [
            round_to_2_decimals(100.0 - 1 * 1.0),  # 99.00
            round_to_2_decimals(100.0 - 2 * 1.0),  # 98.00
            round_to_2_decimals(100.0 - 3 * 1.0)   # 97.00
        ]

        actual_placed_buy_prices = [order['price'] for order in strategy.active_buy_orders]
        assert actual_placed_buy_prices == expected_buy_prices
        assert active_buy_prices == expected_buy_prices

        for i, order in enumerate(strategy.active_buy_orders):
            assert order['size'] == 0.1
            assert order['status'] == 'active'
            assert order['id'] == f'buy_level_{i}_{100.0}' # Check ID format

        # Calling again without inventory change should not change orders
        next_buy_prices, next_sell_prices = strategy.generate_quotes()
        assert len(strategy.active_buy_orders) == 3
        assert [o['price'] for o in strategy.active_buy_orders] == expected_buy_prices
        assert next_buy_prices == expected_buy_prices
        assert next_sell_prices == []


    def test_sell_order_after_buy_execution(self):
        """Test that a sell order is created in pending_sell_orders after a buy order is executed."""
        strategy = GridTradingStrategy(
            quote_size=0.1,
            grid_levels=3,
            grid_spacing=1.0,
            price_rounding_rule=round_to_2_decimals,
            fees_bps=0,
            initial_balance=1000.0
        )
        strategy.update_market_price(100.0)
        strategy.generate_quotes() # Place initial buy orders

        assert len(strategy.active_buy_orders) == 3
        buy_order_to_execute = strategy.active_buy_orders[0] # Let's say the top one (99.00)

        # Execute this buy order
        strategy.execute_trade(trade_price=buy_order_to_execute['price'], trade_size=buy_order_to_execute['size'], is_buy_order=True)

        # Check buy order status
        assert buy_order_to_execute['status'] == 'executed', "Buy order status should be 'executed'"

        # Check pending sell orders
        assert len(strategy.pending_sell_orders) == 1, "One sell order should be pending"
        pending_sell_order = strategy.pending_sell_orders[0]

        expected_sell_price = round_to_2_decimals(buy_order_to_execute['price'] + strategy.grid_spacing) # 99.00 + 1.0 = 100.00
        assert pending_sell_order['price'] == expected_sell_price
        assert pending_sell_order['size'] == buy_order_to_execute['size']
        assert pending_sell_order['status'] == 'pending_sell'
        assert pending_sell_order['buy_price'] == buy_order_to_execute['price']
        assert pending_sell_order['id'] == f"sell_for_{buy_order_to_execute['id']}"

    def test_sell_order_activation(self):
        """Test that a pending sell order becomes active after calling generate_quotes."""
        strategy = GridTradingStrategy(
            quote_size=0.1,
            grid_levels=3,
            grid_spacing=1.0,
            price_rounding_rule=round_to_2_decimals,
            fees_bps=0,
            initial_balance=1000.0
        )
        strategy.update_market_price(100.0)
        strategy.generate_quotes() # Initial buy orders

        buy_order_to_execute = strategy.active_buy_orders[0]
        strategy.execute_trade(trade_price=buy_order_to_execute['price'], trade_size=buy_order_to_execute['size'], is_buy_order=True)

        assert len(strategy.pending_sell_orders) == 1
        assert strategy.pending_sell_orders[0]['status'] == 'pending_sell'

        # Calling generate_quotes again should activate the sell order
        active_buy_prices, active_sell_prices = strategy.generate_quotes()

        assert strategy.pending_sell_orders[0]['status'] == 'active_sell', "Sell order should be 'active_sell'"
        assert len(active_sell_prices) == 1, "One active sell price should be returned"
        assert active_sell_prices[0] == strategy.pending_sell_orders[0]['price']

        # Active buy orders (excluding the executed one if it were removed, but it's just status change)
        # The generate_quotes method returns prices of 'active' buy orders.
        expected_active_buy_prices = [o['price'] for o in strategy.active_buy_orders if o['status'] == 'active']
        assert active_buy_prices == expected_active_buy_prices
        assert len(active_buy_prices) == 2 # One was executed

    def test_pnl_and_inventory_after_trades_with_fees(self):
        """Test PnL and inventory calculations including fees."""
        fees_bps = 50 # 0.5%
        initial_balance = 10000.0
        strategy = GridTradingStrategy(
            quote_size=0.1,
            grid_levels=1, # Simple 1 level grid
            grid_spacing=1.0,
            price_rounding_rule=round_to_2_decimals,
            fees_bps=fees_bps,
            initial_balance=initial_balance
        )
        strategy.update_market_price(100.0)

        # Place and get buy orders
        strategy.generate_quotes()
        buy_order = strategy.active_buy_orders[0]
        buy_price = buy_order['price'] # Expected: 100 - 1 = 99.0
        trade_size = buy_order['size'] # 0.1

        # Execute buy order
        strategy.execute_trade(trade_price=buy_price, trade_size=trade_size, is_buy_order=True)
        assert strategy.inventory == pytest.approx(trade_size)
        buy_cost = buy_price * trade_size
        buy_fee = buy_cost * (fees_bps / 10000)
        expected_pnl_after_buy = -(buy_cost + buy_fee)
        assert strategy.pnl == pytest.approx(expected_pnl_after_buy)
        assert strategy.current_balance == pytest.approx(initial_balance + expected_pnl_after_buy)

        # Activate and get sell order
        strategy.generate_quotes()
        assert len(strategy.pending_sell_orders) == 1
        sell_order = strategy.pending_sell_orders[0]
        assert sell_order['status'] == 'active_sell'
        sell_price = sell_order['price'] # Expected: 99.0 + 1.0 = 100.0

        # Execute sell order
        strategy.execute_trade(trade_price=sell_price, trade_size=trade_size, is_buy_order=False)
        assert strategy.inventory == pytest.approx(0.0)
        sell_revenue = sell_price * trade_size
        sell_fee = sell_revenue * (fees_bps / 10000)
        expected_pnl_after_sell = expected_pnl_after_buy + (sell_revenue - sell_fee)
        # Example: buy_price=99, sell_price=100, size=0.1, fees_bps=50 (0.5%)
        # Buy cost = 99*0.1 = 9.9. Buy fee = 9.9 * 0.005 = 0.0495. PnL = -9.9495
        # Sell rev = 100*0.1 = 10. Sell fee = 10 * 0.005 = 0.05. PnL = -9.9495 + (10 - 0.05) = -9.9495 + 9.95 = 0.0005
        assert strategy.pnl == pytest.approx(expected_pnl_after_sell)
        assert strategy.current_balance == pytest.approx(initial_balance + expected_pnl_after_sell)

    def test_no_short_selling(self, capsys):
        """Test that strategy does not allow selling if inventory is insufficient."""
        strategy = GridTradingStrategy(0.1, 1, 1.0, round_to_2_decimals, 0, initial_balance=100.0)
        strategy.update_market_price(100.0)
        # No initial inventory
        assert strategy.inventory == 0

        # Attempt to execute a sell order (e.g. a manual one, or if a pending_sell existed somehow)
        # To make this test robust, let's assume a pending_sell order somehow exists,
        # but inventory is 0.
        # For this test, we directly call execute_trade for a sell.
        strategy.execute_trade(trade_price=101.0, trade_size=0.1, is_buy_order=False)

        captured = capsys.readouterr()
        assert "Error: Attempted to sell" in captured.out # Check for error message
        assert strategy.inventory == 0 # Inventory should not change
        assert strategy.pnl == 0 # PnL should not change

        # Execute a buy to get some inventory
        strategy.generate_quotes() # This will place buy orders since inventory is 0
        buy_order = strategy.active_buy_orders[0]
        strategy.execute_trade(trade_price=buy_order['price'], trade_size=buy_order['size'], is_buy_order=True)
        assert strategy.inventory > 0

        # Attempt to sell more than available inventory
        original_inventory = strategy.inventory
        original_pnl = strategy.pnl
        strategy.execute_trade(trade_price=101.0, trade_size=original_inventory + 0.1, is_buy_order=False)

        captured = capsys.readouterr()
        assert "Error: Attempted to sell" in captured.out
        assert strategy.inventory == original_inventory # Inventory should not change
        assert strategy.pnl == original_pnl # PnL should not change

    def test_price_rounding_rules(self):
        """Test that order prices are correctly rounded based on the provided rule."""
        # Test with round_to_0_50
        strategy_half_round = GridTradingStrategy(0.1, 1, 0.75, round_to_0_50, 0, initial_balance=1000.0)
        strategy_half_round.update_market_price(100.25) # Market price

        # Expected buy price: 100.25 - (1 * 0.75) = 99.5. Rounded to 0.50 is 99.50
        strategy_half_round.generate_quotes()
        assert len(strategy_half_round.active_buy_orders) == 1
        buy_order = strategy_half_round.active_buy_orders[0]
        assert buy_order['price'] == 99.50

        # Execute buy, check sell price rounding
        strategy_half_round.execute_trade(buy_order['price'], buy_order['size'], True)
        assert len(strategy_half_round.pending_sell_orders) == 1
        sell_order = strategy_half_round.pending_sell_orders[0]
        # Expected sell price: 99.50 + 0.75 = 100.25. Rounded to 0.50 is 100.00 (or 100.50 depending on exact half behavior)
        # round(100.25 * 2) / 2 = round(200.5) / 2 = 201 / 2 = 100.5
        assert sell_order['price'] == 100.50

        # Test with round_to_whole
        strategy_whole_round = GridTradingStrategy(0.1, 1, 0.75, round_to_whole, 0, initial_balance=1000.0)
        strategy_whole_round.update_market_price(100.25)
        strategy_whole_round.generate_quotes()
        # Expected buy: 100.25 - 0.75 = 99.5. Rounded to whole is 100.0
        assert strategy_whole_round.active_buy_orders[0]['price'] == 100.0

        strategy_whole_round.execute_trade(100.0, 0.1, True)
        # Expected sell: 100.0 + 0.75 = 100.75. Rounded to whole is 101.0
        assert strategy_whole_round.pending_sell_orders[0]['price'] == 101.0

    def test_generate_new_grid_after_cycle(self):
        """Test that a new grid of buy orders is generated after a full cycle and inventory is zero."""
        strategy = GridTradingStrategy(
            quote_size=0.1,
            grid_levels=1, # Keep it simple
            grid_spacing=1.0,
            price_rounding_rule=round_to_2_decimals,
            fees_bps=0,
            initial_balance=1000.0
        )
        # --- First Cycle ---
        strategy.update_market_price(100.0)
        buy_prices, sell_prices = strategy.generate_quotes()
        assert len(buy_prices) == 1
        assert sell_prices == []
        first_buy_order_price = buy_prices[0] # Expected 99.0

        # Execute the buy
        strategy.execute_trade(trade_price=first_buy_order_price, trade_size=0.1, is_buy_order=True)
        assert strategy.inventory == 0.1
        assert strategy.active_buy_orders[0]['status'] == 'executed'

        # Activate the sell
        buy_prices, sell_prices = strategy.generate_quotes()
        assert len(sell_prices) == 1
        assert strategy.pending_sell_orders[0]['status'] == 'active_sell'
        first_sell_order_price = sell_prices[0] # Expected 100.0

        # Execute the sell
        strategy.execute_trade(trade_price=first_sell_order_price, trade_size=0.1, is_buy_order=False)
        assert strategy.inventory == 0.0
        assert strategy.pending_sell_orders[0]['status'] == 'executed_sell'

        # At this point, inventory is 0. active_buy_orders has one 'executed' order.
        # pending_sell_orders has one 'executed_sell' order.
        # The condition for new grid in generate_quotes is:
        # self.inventory == 0 and not has_active_buy_orders and not has_pending_or_active_sell_orders
        # where has_active_buy_orders checks for status 'active'
        # and has_pending_or_active_sell_orders checks for status 'pending_sell' or 'active_sell'.
        # So, the conditions *should* be met for a new grid.

        # --- Second Cycle ---
        strategy.update_market_price(105.0) # New market price
        new_buy_prices, new_sell_prices = strategy.generate_quotes()

        assert len(strategy.active_buy_orders) > 0 # Should have new buy orders
        # Check if the new buy orders are 'active' and based on the new market price
        # The old 'executed' buy order should have been cleared by the list comprehension
        # in generate_quotes if the new grid condition was met.

        # Let's verify the active_buy_orders list only contains new active orders.
        # The generate_quotes method itself filters to return only active prices.
        # The internal list self.active_buy_orders is cleared IF the conditions for new grid are met.

        assert len(new_buy_prices) == 1, "Should generate a new set of buy orders"
        assert new_sell_prices == [], "No sell orders should be active with a new grid"

        expected_new_buy_price = round_to_2_decimals(105.0 - 1 * 1.0) # 104.0
        assert new_buy_prices[0] == expected_new_buy_price

        # Verify the internal lists are clean
        active_orders_in_list = [o for o in strategy.active_buy_orders if o['status'] == 'active']
        assert len(active_orders_in_list) == 1
        assert active_orders_in_list[0]['price'] == expected_new_buy_price

        pending_or_active_sell_in_list = [
            o for o in strategy.pending_sell_orders if o['status'] in ('pending_sell', 'active_sell')
        ]
        assert len(pending_or_active_sell_in_list) == 0

    def test_generate_quotes_no_market_price(self):
        """Test generate_quotes when market price is None."""
        strategy = GridTradingStrategy(0.1, 3, 1.0, round_to_2_decimals, 0, initial_balance=100.0)
        # strategy.current_market_price is None by default
        buy_prices, sell_prices = strategy.generate_quotes()
        assert buy_prices == []
        assert sell_prices == []
        assert strategy.active_buy_orders == []
        assert strategy.pending_sell_orders == []
