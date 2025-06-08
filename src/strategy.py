import logging

logger = logging.getLogger(__name__)

# MarketMakingStrategy class and its comments have been removed.
# The TODO regarding its __main__ block is also removed as the class is gone.

class SimpleMarketMakerStrategy:
    def __init__(self, exchange, symbol, order_size, price_levels, increment, strategy_id="SMM"):
        """
        Initializes the SimpleMarketMakerStrategy.

        Args:
            exchange: The exchange object to interact with (for backtesting, this will be a mock).
            symbol: The trading symbol (e.g., 'BTC/USD').
            order_size: The size of each buy/sell order.
            price_levels: A list of specific price levels to place buy orders.
            increment: The fixed price increment for sell orders.
            strategy_id: An identifier for this strategy instance.
        """
        self.exchange = exchange # In backtesting, this is the Backtester's mock exchange interface
        self.symbol = symbol
        self.order_size = order_size
        self.price_levels = sorted(price_levels)
        self.increment = increment
        self.inventory = 0.0
        self.active_buy_orders = {}  # price: order_id
        self.active_sell_orders = {} # price: order_id
        self.filled_buy_orders = {} # order_id: {'price': price, 'size': size, 'status': 'filled'}
        self.pnl = 0.0 # Strategy specific PnL tracking
        self.strategy_id = strategy_id

        self.available_balance = 0.0 # Set by backtester via update_balance_and_max_entries
        self.max_entry_points = 0  # Set by backtester via update_balance_and_max_entries

        logger.info(f"SimpleMarketMakerStrategy {self.strategy_id} initialized for {self.symbol}")
        logger.info(f"Order size: {self.order_size}, Price Levels: {self.price_levels}, Increment: {self.increment}")

    def update_balance_and_max_entries(self, balance: float):
        """Called by the backtester to set the current available capital for the strategy."""
        self.available_balance = balance
        self.max_entry_points = self._calculate_max_entry_points_internal()
        logger.info(f"Strategy {self.strategy_id} balance updated to: {self.available_balance}. Max entry points recalculated: {self.max_entry_points}")

    def _calculate_max_entry_points_internal(self) -> int:
        """
        Internal helper to calculate max entry points based on current available_balance.
        """
        if self.order_size <= 0 or self.available_balance <= 0:
            return 0
        if not self.price_levels:
            return 0

        lowest_buy_price = self.price_levels[0]
        if lowest_buy_price <= 0: # Price must be positive
            return 0

        estimated_cost_per_order = lowest_buy_price * self.order_size
        if estimated_cost_per_order <= 0: # Cost must be positive
            return 0
        return int(self.available_balance / estimated_cost_per_order)

    def place_initial_buy_orders(self):
        """
        Places initial buy orders at specified price levels, up to max_entry_points.
        This method is called by the strategy itself (e.g. in run()) or by the backtester.
        """
        logger.info(f"Strategy {self.strategy_id}: Placing initial buy orders. Max entries: {self.max_entry_points}, Current active: {len(self.active_buy_orders)}")
        placed_count = 0
        if self.max_entry_points == 0:
            logger.warning(f"Strategy {self.strategy_id}: Max entry points is 0. Cannot place initial buy orders. Check capital allocation.")
            return

        for price in self.price_levels:
            if len(self.active_buy_orders) >= self.max_entry_points:
                logger.warning(f"Strategy {self.strategy_id}: Reached max active buy orders ({self.max_entry_points}). Cannot place more initial buys.")
                break
            if price not in self.active_buy_orders:
                try:
                    order_id = self.exchange.place_limit_buy_order(
                        symbol=self.symbol,
                        size=self.order_size,
                        price=price,
                        strategy_id=self.strategy_id
                    )
                    if order_id:
                        self.active_buy_orders[price] = order_id
                        placed_count += 1
                        logger.info(f"Strategy {self.strategy_id}: Placed initial BUY order {order_id} for {self.order_size} {self.symbol} at {price}")
                    else:
                        logger.error(f"Strategy {self.strategy_id}: Failed to place initial BUY order at {price} (no ID returned by exchange mock).")
                except Exception as e:
                    logger.error(f"Strategy {self.strategy_id}: Error placing initial BUY order at {price}: {e}")
            else:
                logger.info(f"Strategy {self.strategy_id}: Buy order already active at price {price}. Skipping.")
        logger.info(f"Strategy {self.strategy_id}: Placed {placed_count} initial buy orders.")
        if not self.active_buy_orders and self.price_levels and self.max_entry_points > 0:
             logger.warning(f"Strategy {self.strategy_id}: No buy orders were placed despite available entry points. Check exchange interaction or order placement logic.")

    def handle_filled_order(self, order_id: str, filled_price: float, filled_size: float, fee: float = 0.0) -> str:
        """
        Handles a filled order notification from the backtester.
        Updates inventory, PnL, and places new orders as per strategy logic.
        Returns a string indicating the type of fill handled ("buy_fill", "sell_fill", or "unknown_fill").
        """
        logger.info(f"Strategy {self.strategy_id}: Handling filled order {order_id}. Price: {filled_price}, Size: {filled_size}, Fee: {fee}")

        buy_order_price_key = None
        for price_key, active_id in self.active_buy_orders.items():
            if active_id == order_id:
                buy_order_price_key = price_key
                break

        if buy_order_price_key is not None:
            logger.info(f"Strategy {self.strategy_id}: BUY order {order_id} at price {buy_order_price_key} filled.")
            self.pnl -= (filled_price * filled_size) + fee
            self.inventory += filled_size
            self.filled_buy_orders[order_id] = {'price': filled_price, 'size': filled_size, 'status': 'filled', 'fee': fee}

            del self.active_buy_orders[buy_order_price_key]
            logger.info(f"Strategy {self.strategy_id}: Removed active BUY order {order_id} (price {buy_order_price_key}). PnL: {self.pnl:.4f}, Inv: {self.inventory:.4f}")

            if self.inventory > 0:
                sell_price = filled_price + self.increment
                sell_size = filled_size

                if sell_price in self.active_buy_orders:
                    logger.warning(f"Strategy {self.strategy_id}: Proposed sell price {sell_price} conflicts with an active buy order. Skipping sell.")
                elif sell_price in self.active_sell_orders:
                     logger.warning(f"Strategy {self.strategy_id}: Sell order already active at price {sell_price}. Skipping duplicate sell.")
                else:
                    try:
                        sell_order_id = self.exchange.place_limit_sell_order(
                            symbol=self.symbol,
                            size=sell_size,
                            price=sell_price,
                            strategy_id=self.strategy_id
                        )
                        if sell_order_id:
                            self.active_sell_orders[sell_price] = sell_order_id
                            logger.info(f"Strategy {self.strategy_id}: Placed SELL order {sell_order_id} for {sell_size} {self.symbol} at {sell_price}")
                        else:
                            logger.error(f"Strategy {self.strategy_id}: Failed to place SELL order at {sell_price} (no ID returned).")
                    except Exception as e:
                        logger.error(f"Strategy {self.strategy_id}: Error placing SELL order for BUY fill {order_id}: {e}")
            else: # Should not happen if a buy just filled
                logger.warning(f"Strategy {self.strategy_id}: Inventory is {self.inventory} after BUY fill. Cannot place sell order.")

            self.place_new_buy_order_if_needed()
            return "buy_fill"

        sell_order_price_key = None
        for price_key, active_id in self.active_sell_orders.items():
            if active_id == order_id:
                sell_order_price_key = price_key
                break

        if sell_order_price_key is not None:
            logger.info(f"Strategy {self.strategy_id}: SELL order {order_id} at price {sell_order_price_key} filled.")
            self.pnl += (filled_price * filled_size) - fee
            self.inventory -= filled_size
            del self.active_sell_orders[sell_order_price_key]
            logger.info(f"Strategy {self.strategy_id}: Removed active SELL order {order_id} (price {sell_order_price_key}). PnL: {self.pnl:.4f}, Inv: {self.inventory:.4f}")
            self.place_new_buy_order_if_needed()
            return "sell_fill"

        logger.warning(f"Strategy {self.strategy_id}: Filled order {order_id} not found in active BUY or SELL orders. Ignoring.")
        return "unknown_fill"

    def place_new_buy_order_if_needed(self):
        """
        Checks if new buy orders can be placed based on available slots (max_entry_points) and price levels.
        """
        if self.max_entry_points <= 0:
            return

        available_slots = self.max_entry_points - len(self.active_buy_orders)
        if available_slots <= 0:
            return

        placed_new_count = 0
        for price in self.price_levels:
            if len(self.active_buy_orders) >= self.max_entry_points:
                break

            if price not in self.active_buy_orders:
                try:
                    order_id = self.exchange.place_limit_buy_order(
                        symbol=self.symbol,
                        size=self.order_size,
                        price=price,
                        strategy_id=self.strategy_id
                    )
                    if order_id:
                        self.active_buy_orders[price] = order_id
                        placed_new_count += 1
                        logger.info(f"Strategy {self.strategy_id}: Placed new BUY order {order_id} at {price}.")
                    else:
                        logger.warning(f"Strategy {self.strategy_id}: Failed to place new BUY order at {price} (no ID returned - possibly backtester capital limit).")
                        break
                except Exception as e:
                    logger.error(f"Strategy {self.strategy_id}: Error placing new BUY order at {price}: {e}")

        if placed_new_count > 0:
            logger.info(f"Strategy {self.strategy_id}: Placed {placed_new_count} new buy order(s). Active buys: {len(self.active_buy_orders)}.")

    def cancel_order(self, order_id_to_cancel: str):
        logger.info(f"Strategy {self.strategy_id}: Requesting to cancel order {order_id_to_cancel}")

        price_key_to_remove = None
        order_type = None

        for price, oid in self.active_buy_orders.items():
            if oid == order_id_to_cancel:
                price_key_to_remove = price
                order_type = "BUY"
                break
        if not order_type: # Check sell orders if not found in buys
            for price, oid in self.active_sell_orders.items():
                if oid == order_id_to_cancel:
                    price_key_to_remove = price
                    order_type = "SELL"
                    break

        if not order_type or price_key_to_remove is None:
            logger.warning(f"Strategy {self.strategy_id}: Order {order_id_to_cancel} not found in active buy or sell orders for cancellation.")
            return False

        try:
            if self.exchange.cancel_order(order_id_to_cancel, strategy_id=self.strategy_id):
                logger.info(f"Strategy {self.strategy_id}: Cancellation request for {order_type} order {order_id_to_cancel} acknowledged by exchange mock.")
                if order_type == "BUY":
                    del self.active_buy_orders[price_key_to_remove]
                    self.place_new_buy_order_if_needed() # If a buy was cancelled, try to place another
                elif order_type == "SELL":
                    del self.active_sell_orders[price_key_to_remove]

                logger.info(f"Strategy {self.strategy_id}: Removed {order_type} order {order_id_to_cancel} from active tracking (price {price_key_to_remove}).")
                return True
            else:
                logger.error(f"Strategy {self.strategy_id}: Exchange mock failed to confirm cancellation for order {order_id_to_cancel}.")
                return False
        except Exception as e:
            logger.error(f"Strategy {self.strategy_id}: Error during cancel_order call to exchange mock for {order_id_to_cancel}: {e}")
            return False

    def run(self, initial_capital_allocation: float = None):
        """
        Called by the Backtester to start the strategy logic, like placing initial orders.
        """
        logger.info(f"Strategy {self.strategy_id}: run() called. Symbol: {self.symbol}")
        if initial_capital_allocation is not None:
            self.update_balance_and_max_entries(initial_capital_allocation)
        else:
            # If no specific capital is given, try to use exchange's balance if available, or default.
            try:
                 current_bal = self.exchange.get_balance(strategy_id=self.strategy_id) # Assuming backtester provides this
                 self.update_balance_and_max_entries(current_bal)
            except Exception as e:
                 logger.warning(f"Strategy {self.strategy_id}: Could not get initial balance from exchange for run(). Error: {e}. Max entries may be 0.")
                 self.update_balance_and_max_entries(0.0)


        self.place_initial_buy_orders()
        logger.info(f"Strategy {self.strategy_id}: run() finished. Active buys: {len(self.active_buy_orders)}, Active sells: {len(self.active_sell_orders)}")

    def check_order_statuses(self):
        """
        This method is less critical when the backtester pushes fill/cancellation updates.
        It can be used for internal strategy health checks or handling expiries if applicable.
        """
        logger.info(f"Strategy {self.strategy_id}: check_order_statuses() called. Active buys: {len(self.active_buy_orders)}, Active sells: {len(self.active_sell_orders)}")
        # For this assignment, the backtester will directly call handle_filled_order or update
        # strategy based on its own order status checks. So, this method is mostly a placeholder.

# --- Main execution block for SimpleMarketMakerStrategy (similar to the one drafted before) ---
if __name__ == '__main__':
    # Setup basic logging for console output
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger(__name__) # Logger for this main block

    # --- Mock Exchange for demonstration of SimpleMarketMakerStrategy ---
    class MockExchangeSMM: # Renamed to avoid conflict if running both __main__ blocks
        def __init__(self, initial_balance_map=None): # Takes a map {strategy_id: balance}
            self.balance_map = initial_balance_map if initial_balance_map else {}
            self.orders = {}
            self.order_id_counter = 1
            main_logger.info(f"MockExchangeSMM initialized with balance map: {self.balance_map}")

        def get_balance(self, strategy_id=None): # Strategy asks for its own balance
            balance = self.balance_map.get(strategy_id, 0.0)
            main_logger.info(f"MockExchangeSMM: get_balance(stratID={strategy_id}) called, returning: {balance}")
            return balance

        def place_limit_buy_order(self, symbol, size, price, strategy_id=None):
            order_id = f"buy_smm_{self.order_id_counter}"
            self.order_id_counter += 1
            # Cost calculation can be done here for logging or for a more complex mock
            # For this mock, we assume the backtester (or strategy's allowance) manages funds.
            self.orders[order_id] = {
                'symbol': symbol, 'type': 'buy', 'size': size, 'price': price,
                'status': 'open', 'filled_size': 0, 'filled_price': 0, 'strategy_id': strategy_id
            }
            main_logger.info(f"MockExchangeSMM (StratID {strategy_id}): Placed BUY order {order_id} for {size} {symbol} at {price}.")
            return order_id

        def place_limit_sell_order(self, symbol, size, price, strategy_id=None):
            order_id = f"sell_smm_{self.order_id_counter}"
            self.order_id_counter += 1
            self.orders[order_id] = {
                'symbol': symbol, 'type': 'sell', 'size': size, 'price': price,
                'status': 'open', 'filled_size': 0, 'filled_price': 0, 'strategy_id': strategy_id
            }
            main_logger.info(f"MockExchangeSMM (StratID {strategy_id}): Placed SELL order {order_id} for {size} {symbol} at {price}.")
            return order_id

        def cancel_order(self, order_id, strategy_id=None):
            if order_id in self.orders and self.orders[order_id]['status'] == 'open':
                if self.orders[order_id].get('strategy_id') != strategy_id:
                    main_logger.error(f"MockExchangeSMM (StratID {strategy_id}): Order {order_id} cannot be cancelled. Belongs to {self.orders[order_id].get('strategy_id')}.")
                    return False
                self.orders[order_id]['status'] = 'cancelled'
                main_logger.info(f"MockExchangeSMM (StratID {strategy_id}): Cancelled order {order_id}.")
                return True
            main_logger.error(f"MockExchangeSMM (StratID {strategy_id}): Could not cancel order {order_id} (not found or not open).")
            return False

        def get_order_details(self, order_id): # Used by strategy's check_order_statuses (if ever more developed)
            if order_id in self.orders:
                return dict(self.orders[order_id])
            return None

        # --- Test Simulation Helper ---
        def simulate_fill(self, order_id, fill_price, fill_size): # Simplified for test
            if order_id in self.orders and self.orders[order_id]['status'] == 'open':
                self.orders[order_id]['status'] = 'filled'
                self.orders[order_id]['filled_price'] = fill_price
                self.orders[order_id]['filled_size'] = fill_size
                main_logger.info(f"MockExchangeSMM: Test fill for order {order_id} at {fill_price}, size {fill_size}.")
                return True
            main_logger.error(f"MockExchangeSMM: Test fill failed for order {order_id}.")
            return False

    main_logger.info("\n\n--- Starting SimpleMarketMakerStrategy Example ---")
    strategy_id_main = "SMM_MainTest"
    initial_capital_for_strategy = 2000.0
    mock_exchange_smm = MockExchangeSMM(initial_balance_map={strategy_id_main: initial_capital_for_strategy})

    smm_strategy = SimpleMarketMakerStrategy(
        exchange=mock_exchange_smm, # The mock exchange instance
        symbol='ETH/USD',
        order_size=0.1,
        price_levels=[90, 95, 100.01],
        increment=10,
        strategy_id=strategy_id_main
    )

    # Initialize strategy with capital (mimics backtester action)
    smm_strategy.run(initial_capital_allocation=initial_capital_for_strategy)

    main_logger.info(f"SMM Strategy ({smm_strategy.strategy_id}): Initial PnL: {smm_strategy.pnl:.2f}, Inv: {smm_strategy.inventory:.2f}")
    main_logger.info(f"Max Entry Points: {smm_strategy.max_entry_points}")
    main_logger.info(f"Active Buys: {smm_strategy.active_buy_orders}")
    assert len(smm_strategy.active_buy_orders) == 3 # Based on price_levels and capital

    # Simulate a buy order fill (e.g., order at 95 for 0.1 ETH)
    buy_order_id_at_95 = smm_strategy.active_buy_orders.get(95)
    test_fee = 0.0095 # Example fee: 0.01% of 95 * 0.1
    if buy_order_id_at_95:
        main_logger.info(f"\n--- Simulating BUY fill for {buy_order_id_at_95} (price 95), Fee: {test_fee} ---")
        mock_exchange_smm.simulate_fill(buy_order_id_at_95, 95, smm_strategy.order_size) # Mark as filled in mock
        smm_strategy.handle_filled_order(buy_order_id_at_95, 95, smm_strategy.order_size, fee=test_fee) # Notify strategy

        main_logger.info(f"SMM Strategy: PnL: {smm_strategy.pnl:.4f}, Inv: {smm_strategy.inventory:.2f}")
        # PnL = -(95 * 0.1) - 0.0095 = -9.5 - 0.0095 = -9.5095
        assert abs(smm_strategy.pnl - (-9.5095)) < 1e-9
        assert abs(smm_strategy.inventory - 0.1) < 1e-9
        assert 95 not in smm_strategy.active_buy_orders # Original removed
        assert 105 in smm_strategy.active_sell_orders # New sell placed
        assert 95 in smm_strategy.active_buy_orders   # New buy order at 95 should be placed by place_new_buy_order_if_needed
    else:
        main_logger.error("SMM Test: Could not find active buy order at 95 for fill simulation.")

    # Simulate a sell order fill (the one placed at 105)
    sell_order_id_at_105 = smm_strategy.active_sell_orders.get(105)
    test_sell_fee = 0.0105 # Example fee: 0.01% of 105 * 0.1
    if sell_order_id_at_105:
        main_logger.info(f"\n--- Simulating SELL fill for {sell_order_id_at_105} (price 105), Fee: {test_sell_fee} ---")
        mock_exchange_smm.simulate_fill(sell_order_id_at_105, 105, smm_strategy.order_size)
        smm_strategy.handle_filled_order(sell_order_id_at_105, 105, smm_strategy.order_size, fee=test_sell_fee)

        main_logger.info(f"SMM Strategy: PnL: {smm_strategy.pnl:.4f}, Inv: {smm_strategy.inventory:.2f}")
        # Prev PnL = -9.5095. Sell PnL = (105 * 0.1) - 0.0105 = 10.5 - 0.0105 = 10.4895
        # Total PnL = -9.5095 + 10.4895 = 0.98
        assert abs(smm_strategy.pnl - 0.98) < 1e-9
        assert abs(smm_strategy.inventory - 0.0) < 1e-9 # Inventory back to 0
        assert 105 not in smm_strategy.active_sell_orders
    else:
        main_logger.error("SMM Test: Could not find active sell order at 105 for fill simulation.")

    main_logger.info(f"\nSMM Strategy Final State: PnL: {smm_strategy.pnl:.4f}, Inv: {smm_strategy.inventory:.2f}")
    main_logger.info(f"Active Buys: {smm_strategy.active_buy_orders}")
    main_logger.info(f"Active Sells: {smm_strategy.active_sell_orders}")
    main_logger.info(f"Total orders in mock exchange: {len(mock_exchange_smm.orders)}")
    main_logger.info("SMM Strategy example finished.")

    # TODO: Add __main__ test for MarketMakingStrategy with fees
    # (Original __main__ for MarketMakingStrategy would go here if needed)
```
