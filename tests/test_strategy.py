import pytest
# MarketMakingStrategy import removed
from src.strategy import SimpleMarketMakerStrategy
from unittest.mock import MagicMock, call
# TestMarketMakingStrategy class and its methods have been removed.

class TestSimpleMarketMakerStrategy:
    @pytest.fixture
    def mock_exchange(self):
        exchange = MagicMock()
        exchange.place_limit_buy_order.side_effect = lambda symbol, size, price, strategy_id: f"buy_order_{price}"
        exchange.place_limit_sell_order.side_effect = lambda symbol, size, price, strategy_id: f"sell_order_{price}"
        exchange.cancel_order.return_value = True
        exchange.get_balance.return_value = 10000 # Default balance for tests
        return exchange

    @pytest.fixture
    def smm_strategy(self, mock_exchange):
        strategy = SimpleMarketMakerStrategy(
            exchange=mock_exchange,
            symbol="TEST/USD",
            order_size=0.1,
            price_levels=[90, 95, 100],
            increment=10,
            strategy_id="SMM_Test"
        )
        # Initialize with some capital for max_entry_points calculation
        strategy.update_balance_and_max_entries(1000) # e.g. 1000 capital -> 1000 / (90*0.1) = 111 entries
        return strategy

    def test_smm_initialization(self, smm_strategy, mock_exchange):
        assert smm_strategy.symbol == "TEST/USD"
        assert smm_strategy.order_size == 0.1
        assert smm_strategy.price_levels == [90, 95, 100]
        assert smm_strategy.increment == 10
        assert smm_strategy.inventory == 0.0
        assert smm_strategy.pnl == 0.0
        assert smm_strategy.strategy_id == "SMM_Test"
        assert len(smm_strategy.active_buy_orders) == 0
        assert len(smm_strategy.active_sell_orders) == 0
        # Check if update_balance_and_max_entries was called correctly by fixture
        assert smm_strategy.available_balance == 1000
        assert smm_strategy.max_entry_points > 0

    def test_smm_update_balance_and_max_entries(self, smm_strategy):
        smm_strategy.update_balance_and_max_entries(balance=180) # 180 / (90 * 0.1) = 180 / 9 = 20 entries
        assert smm_strategy.available_balance == 180
        assert smm_strategy.max_entry_points == 20

        smm_strategy.update_balance_and_max_entries(balance=5) # 5 / 9 = 0 entries
        assert smm_strategy.available_balance == 5
        assert smm_strategy.max_entry_points == 0

        smm_strategy.update_balance_and_max_entries(balance=0)
        assert smm_strategy.max_entry_points == 0

    def test_smm_place_initial_buy_orders(self, smm_strategy, mock_exchange):
        smm_strategy.max_entry_points = 2 # Limit to 2 orders for this test
        smm_strategy.place_initial_buy_orders()

        assert len(smm_strategy.active_buy_orders) == 2
        assert 90 in smm_strategy.active_buy_orders
        assert 95 in smm_strategy.active_buy_orders
        assert 100 not in smm_strategy.active_buy_orders # Due to max_entry_points

        # Check that exchange mock was called correctly
        expected_calls = [
            call(symbol="TEST/USD", size=0.1, price=90, strategy_id="SMM_Test"),
            call(symbol="TEST/USD", size=0.1, price=95, strategy_id="SMM_Test")
        ]
        mock_exchange.place_limit_buy_order.assert_has_calls(expected_calls, any_order=False)
        assert mock_exchange.place_limit_buy_order.call_count == 2

    def test_smm_handle_buy_fill(self, smm_strategy, mock_exchange):
        smm_strategy.max_entry_points = 3 # Allow all price levels initially
        smm_strategy.place_initial_buy_orders() # Places at 90, 95, 100

        buy_order_id = smm_strategy.active_buy_orders[95] # ID of order at 95
        fill_price = 95.0
        fill_size = 0.1
        fee = 0.01

        smm_strategy.handle_filled_order(buy_order_id, fill_price, fill_size, fee)

        assert smm_strategy.inventory == pytest.approx(0.1)
        assert smm_strategy.pnl == pytest.approx(-(fill_price * fill_size) - fee) # -(9.5) - 0.01 = -9.51
        assert 95 not in smm_strategy.active_buy_orders # Original order removed
        assert buy_order_id in smm_strategy.filled_buy_orders

        # Check if sell order was placed
        expected_sell_price = fill_price + smm_strategy.increment # 95 + 10 = 105
        assert expected_sell_price in smm_strategy.active_sell_orders
        mock_exchange.place_limit_sell_order.assert_called_with(
            symbol="TEST/USD", size=fill_size, price=expected_sell_price, strategy_id="SMM_Test"
        )

        # Check if place_new_buy_order_if_needed was called (implicitly tests it tries to replenish)
        # After one fill (95), active orders are at 90, 100. One slot is free.
        # It should try to place an order at 95 again.
        # This requires careful mocking if we want to assert the *exact* call for replenishment.
        # For now, we check that a call was made *after* the sell order placement.
        assert mock_exchange.place_limit_buy_order.call_count > 3 # 3 initial + at least 1 replenishment attempt

    def test_smm_handle_sell_fill(self, smm_strategy, mock_exchange):
        # Setup: simulate a buy fill first to get inventory and an active sell order
        smm_strategy.max_entry_points = 1
        smm_strategy.place_initial_buy_orders() # Places at 90
        buy_order_id = smm_strategy.active_buy_orders[90]
        smm_strategy.handle_filled_order(buy_order_id, 90.0, 0.1, fee=0.009) # PnL = -9.009, Inv = 0.1

        assert smm_strategy.inventory == pytest.approx(0.1)
        sell_price_level = 90.0 + smm_strategy.increment # 100
        assert sell_price_level in smm_strategy.active_sell_orders
        sell_order_id = smm_strategy.active_sell_orders[sell_price_level]

        # Now, simulate the sell fill
        fill_price = sell_price_level
        fill_size = 0.1
        fee = 0.01

        smm_strategy.handle_filled_order(sell_order_id, fill_price, fill_size, fee)

        assert smm_strategy.inventory == pytest.approx(0.0) # Back to zero
        # Prev PnL = -9.009. Sell income = (100 * 0.1) - 0.01 = 10 - 0.01 = 9.99
        # New PnL = -9.009 + 9.99 = 0.981
        assert smm_strategy.pnl == pytest.approx(0.981)
        assert sell_price_level not in smm_strategy.active_sell_orders

    def test_smm_inventory_management_never_short_on_normal_path(self, smm_strategy, mock_exchange):
        smm_strategy.max_entry_points = 1
        smm_strategy.run(initial_capital_allocation=100) # Place order at 90

        buy_order_id = smm_strategy.active_buy_orders[90]
        smm_strategy.handle_filled_order(buy_order_id, 90.0, 0.1, fee=0.0) # Inv = 0.1
        assert smm_strategy.inventory == pytest.approx(0.1)

        sell_order_id = smm_strategy.active_sell_orders[100.0] # 90 + 10
        smm_strategy.handle_filled_order(sell_order_id, 100.0, 0.1, fee=0.0) # Inv = 0.0
        assert smm_strategy.inventory == pytest.approx(0.0)

        # At this point, no more sell orders should be placed if another buy occurs,
        # unless the strategy is designed to build inventory first.
        # The current logic: sell is placed only after a buy fill.
        # So, if another buy comes and fills, inventory becomes positive, and then a sell is placed.
        # This ensures it doesn't initiate a short position.
        mock_exchange.place_limit_buy_order.reset_mock()
        smm_strategy.place_new_buy_order_if_needed() # Should place at 90 again
        assert 90 in smm_strategy.active_buy_orders
        buy_order_id_2 = smm_strategy.active_buy_orders[90]
        smm_strategy.handle_filled_order(buy_order_id_2, 90.0, 0.1, fee=0.0) # Inv = 0.1 again
        assert smm_strategy.inventory == pytest.approx(0.1)


    def test_smm_cancel_buy_order(self, smm_strategy, mock_exchange):
        smm_strategy.max_entry_points = 1
        smm_strategy.place_initial_buy_orders() # Places at 90
        order_id_to_cancel = smm_strategy.active_buy_orders[90]

        smm_strategy.cancel_order(order_id_to_cancel)

        mock_exchange.cancel_order.assert_called_with(order_id_to_cancel, strategy_id="SMM_Test")
        assert 90 not in smm_strategy.active_buy_orders
        # Check if place_new_buy_order_if_needed was called after cancellation
        # This means it tries to place a new order at 90 again
        calls = mock_exchange.place_limit_buy_order.call_args_list
        # Initial call + call from place_new_buy_order_if_needed
        assert mock_exchange.place_limit_buy_order.call_count >= 2
        last_call_args = calls[-1]
        assert last_call_args == call(symbol="TEST/USD", size=0.1, price=90, strategy_id="SMM_Test")

    def test_smm_cancel_sell_order(self, smm_strategy, mock_exchange):
        # Setup: buy fill, then cancel the resulting sell order
        smm_strategy.max_entry_points = 1
        smm_strategy.place_initial_buy_orders()
        buy_order_id = smm_strategy.active_buy_orders[90]
        smm_strategy.handle_filled_order(buy_order_id, 90.0, 0.1, fee=0.0)

        sell_order_id_to_cancel = smm_strategy.active_sell_orders[100.0] # 90 + 10
        smm_strategy.cancel_order(sell_order_id_to_cancel)

        mock_exchange.cancel_order.assert_called_with(sell_order_id_to_cancel, strategy_id="SMM_Test")
        assert 100.0 not in smm_strategy.active_sell_orders

    def test_smm_run_method(self, smm_strategy, mock_exchange):
        smm_strategy.active_buy_orders.clear() # Ensure it's empty before run
        mock_exchange.reset_mock() # Reset call counts etc.

        smm_strategy.run(initial_capital_allocation=200) # Enough for 2 orders: 200 / (90*0.1) = 22.2 -> 2

        # update_balance_and_max_entries should be called
        assert smm_strategy.available_balance == 200
        assert smm_strategy.max_entry_points == 2

        # place_initial_buy_orders should be called
        assert len(smm_strategy.active_buy_orders) == 2
        assert mock_exchange.place_limit_buy_order.call_count == 2
        mock_exchange.place_limit_buy_order.assert_any_call(symbol="TEST/USD", size=0.1, price=90, strategy_id="SMM_Test")
        mock_exchange.place_limit_buy_order.assert_any_call(symbol="TEST/USD", size=0.1, price=95, strategy_id="SMM_Test")

    # Test for MarketMakingStrategy with fees (from previous subtask, ensure it's still here and correct)
    def test_mms_execute_trade_buy_with_fee(self):
        strategy = MarketMakingStrategy(quote_size=0.1)
        trade_price = 100.0
        trade_size = 0.1
        fee = 0.01 # Example fee
        strategy.execute_trade(trade_price=trade_price, trade_size=trade_size, is_buy_order=True, fee=fee)
        expected_pnl = - (trade_price * trade_size) - fee # -10.0 - 0.01 = -10.01
        assert strategy.pnl == pytest.approx(expected_pnl)
        assert strategy.inventory == pytest.approx(trade_size)

    def test_mms_execute_trade_sell_with_fee(self):
        strategy = MarketMakingStrategy(quote_size=0.1)
        trade_price = 102.0
        trade_size = 0.1
        fee = 0.02 # Example fee
        strategy.execute_trade(trade_price=trade_price, trade_size=trade_size, is_buy_order=False, fee=fee)
        expected_pnl = (trade_price * trade_size) - fee # 10.2 - 0.02 = 10.18
        assert strategy.pnl == pytest.approx(expected_pnl)
        assert strategy.inventory == pytest.approx(-trade_size)

# The following two standalone test functions are MMS specific and will be removed.
