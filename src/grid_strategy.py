class GridTradingStrategy:
    """
    A simple market making strategy that places bid and ask quotes around a current market price.
    It also tracks Profit and Loss (PnL) and inventory.
    """

    def __init__(self, quote_size: float, grid_levels: int, grid_spacing: float, price_rounding_rule: callable, fees_bps: int, initial_balance: float):
        """
        Initializes the GridTradingStrategy.

        Args:
            quote_size: The amount of base asset to be used for each quote.
            grid_levels: The number of buy/sell levels in the grid.
            grid_spacing: The spacing between grid levels (e.g., as a percentage or absolute value).
            price_rounding_rule: A function to round calculated order prices.
            fees_bps: Trading fees in basis points.
            initial_balance: The starting balance of the quote currency.
        """
        self.current_market_price: float | None = None
        self.pnl: float = 0.0
        self.inventory: float = 0.0  # Amount of base asset held
        self.quote_size: float = quote_size
        self.grid_levels: int = grid_levels
        self.grid_spacing: float = grid_spacing
        self.price_rounding_rule: callable = price_rounding_rule
        self.fees_bps: int = fees_bps
        self.initial_balance: float = initial_balance
        self.current_balance: float = initial_balance

        self.active_buy_orders = []
        self.pending_sell_orders = []


    def update_market_price(self, current_price: float):
        """
        Updates the current market price observed by the strategy.

        Args:
            current_price: The latest market price.
        """
        self.current_market_price = current_price

    def generate_quotes(self) -> tuple[list[float], list[float]]:
        """
        Generates new buy orders if conditions are met (e.g., zero inventory and no active grid).
        Activates pending sell orders.
        Returns lists of active buy and sell prices.

        Returns:
            A tuple (list_of_active_buy_prices, list_of_active_sell_prices).
            Returns ([], []) if market price is unavailable.
        """
        if self.current_market_price is None:
            return [], []

        # Condition for generating a new grid of buy orders:
        # - Inventory is zero.
        # - No buy orders are currently 'active'.
        # - No sell orders are currently 'pending_sell' or 'active_sell'.
        has_active_buy_orders = any(order['status'] == 'active' for order in self.active_buy_orders)
        has_pending_or_active_sell_orders = any(
            order['status'] in ('pending_sell', 'active_sell') for order in self.pending_sell_orders
        )

        if self.inventory == 0 and not has_active_buy_orders and not has_pending_or_active_sell_orders:
            # Clear out any old 'executed' or 'cancelled' orders before creating a new grid
            self.active_buy_orders = [o for o in self.active_buy_orders if o['status'] == 'active'] # Should be empty by condition anyway
            self.pending_sell_orders = [o for o in self.pending_sell_orders if o['status'] in ('pending_sell', 'active_sell')] # Should be empty

            for i in range(self.grid_levels):
                buy_price_raw = self.current_market_price - (i + 1) * self.grid_spacing
                rounded_buy_price = self.price_rounding_rule(buy_price_raw)
                if rounded_buy_price > 0:
                    order = {
                        'id': f'buy_level_{i}_{self.current_market_price}', # Add market price to id for uniqueness if grids regenerate
                        'price': rounded_buy_price,
                        'size': self.quote_size,
                        'status': 'active'
                    }
                    self.active_buy_orders.append(order)

        # Activate pending sell orders
        for order in self.pending_sell_orders:
            if order['status'] == 'pending_sell':
                order['status'] = 'active_sell'

        active_buy_prices = [order['price'] for order in self.active_buy_orders if order['status'] == 'active']
        active_sell_prices = [order['price'] for order in self.pending_sell_orders if order['status'] == 'active_sell']

        return active_buy_prices, active_sell_prices

    def execute_trade(self, trade_price: float, trade_size: float, is_buy_order: bool):
        """
        Records a trade execution, updating PnL, inventory, and order states.
        If a buy order is filled, it generates a corresponding pending sell order.

        Args:
            trade_price: The price at which the trade was executed.
            trade_size: The amount of asset traded.
            is_buy_order: True if the strategy's buy quote was hit (strategy buys),
                          False if the strategy's sell quote was hit (strategy sells).
        """
        if is_buy_order:
            # --- Buy Order Execution ---
            executed_order = None
            for order in self.active_buy_orders:
                # Assuming trade_price will exactly match one of the active buy order prices
                # Add tolerance for float comparison if necessary in a real system
                if order['price'] == trade_price and order['status'] == 'active':
                    executed_order = order
                    break

            if executed_order:
                executed_order['status'] = 'executed'
                # Note: The order remains in active_buy_orders but status changes.
                # Consider moving it to a separate list like `self.executed_buy_orders` if needed.

                # Generate a corresponding sell order
                sell_price_raw = trade_price + self.grid_spacing
                rounded_sell_price = self.price_rounding_rule(sell_price_raw)

                # Ensure the sell price is valid (e.g., > 0 and perhaps > buy_price after fees)
                if rounded_sell_price > 0:
                    sell_order = {
                        'id': f'sell_for_{executed_order["id"]}', # Link sell to the buy order id
                        'buy_price': trade_price, # Store original buy price for reference
                        'price': rounded_sell_price,
                        'size': executed_order['size'], # Sell the same size that was bought
                        'status': 'pending_sell'
                    }
                    self.pending_sell_orders.append(sell_order)
                # else:
                    # print(f"Warning: Calculated sell price {rounded_sell_price} for buy order {executed_order['id']} is not valid. Sell order not created.")

            # else:
                # This case implies a buy occurred that didn't match an active strategy order.
                # This might happen if the backtester logic allows fills outside strategy's explicit orders,
                # or if trade_price doesn't exactly match. For now, we assume exact match.
                # print(f"Warning: Buy trade at {trade_price} did not match any active buy order.")

            # PnL and inventory update for the buy trade, including fees
            fee = trade_price * trade_size * (self.fees_bps / 10000)
            self.pnl -= (trade_price * trade_size + fee) # Cost of asset + fee
            self.current_balance = self.initial_balance + self.pnl
            self.inventory += trade_size         # Base asset increases

        else:
            # --- Sell Order Execution ---
            # Safeguard: Ensure sufficient inventory to sell
            if self.inventory < trade_size:
                print(f"Error: Attempted to sell {trade_size} but inventory is {self.inventory}. Sell order at {trade_price} not executed.")
                return # Or raise an exception

            executed_sell_order = None
            for order in self.pending_sell_orders:
                # Sell orders are marked 'active_sell' by generate_quotes before execution
                if order['price'] == trade_price and order['status'] == 'active_sell':
                    executed_sell_order = order
                    break

            if executed_sell_order:
                executed_sell_order['status'] = 'executed_sell'
                # Note: Order remains in pending_sell_orders with changed status.
                # Consider moving to `self.executed_sell_orders` or removing if preferred.
            # else:
                # print(f"Warning: Sell trade at {trade_price} did not match any pending sell order.")
                # This could be a manually executed sell or a different type of sell order not managed by this grid logic.


            # PnL and inventory update for the sell trade, including fees
            fee = trade_price * trade_size * (self.fees_bps / 10000)
            self.pnl += (trade_price * trade_size - fee) # Revenue from sale - fee
            self.current_balance = self.initial_balance + self.pnl
            self.inventory -= trade_size         # Base asset decreases

if __name__ == '__main__':
    # Example Usage
    # Define a simple rounding rule for the example
    def round_to_2_decimals(price):
        return round(price, 2)

    strategy = GridTradingStrategy(
        quote_size=0.1,
        grid_levels=5,
        grid_spacing=0.5,  # Example: 0.5 price units spacing
        price_rounding_rule=round_to_2_decimals,
        fees_bps=50, # Example: 50 bps = 0.5% fees, to make them visible
        initial_balance=1000.0
    )

    # Simulate updating market price
    strategy.update_market_price(100.0)
    print(f"Initial PnL: {strategy.pnl:.4f}, Inventory: {strategy.inventory:.4f}, Initial Balance: {strategy.initial_balance:.2f}, Current Balance: {strategy.current_balance:.2f}")
    print(f"Strategy params: QS={strategy.quote_size}, Levels={strategy.grid_levels}, Spacing={strategy.grid_spacing}, Fees={strategy.fees_bps}bps")

    # Generate initial quotes
    active_buy_prices, active_sell_prices = strategy.generate_quotes()
    print(f"\nInitial active buy prices: {active_buy_prices}, Active sell prices: {active_sell_prices}")
    # print(f"Full active_buy_orders list: {strategy.active_buy_orders}")

    # Simulate a buy order fill
    if strategy.active_buy_orders and any(o['status'] == 'active' for o in strategy.active_buy_orders):
        buy_order_to_fill = next(o for o in strategy.active_buy_orders if o['status'] == 'active') # Get first active one

        print(f"\n--- Simulating BUY order execution ---")
        print(f"Executing BUY: ID={buy_order_to_fill['id']}, Price={buy_order_to_fill['price']}, Size={buy_order_to_fill['size']}")
        # Example buy: price=99.5, size=0.1. Cost = 9.95. Fee = 9.95 * 0.005 = 0.04975. PnL -= 9.99975
        strategy.execute_trade(trade_price=buy_order_to_fill['price'], trade_size=buy_order_to_fill['size'], is_buy_order=True)
        print(f"PnL after BUY: {strategy.pnl:.4f}, Inventory: {strategy.inventory:.4f}")
        # print(f"Active buy orders: {strategy.active_buy_orders}")
        # print(f"Pending sell orders: {strategy.pending_sell_orders}")

        # Call generate_quotes to activate the pending sell order
        print("\n--- Calling generate_quotes() to activate sell orders ---")
        active_buy_prices, active_sell_prices = strategy.generate_quotes()
        print(f"Active buy prices: {active_buy_prices}, Active sell prices: {active_sell_prices}")
        # print(f"Pending sell orders (should be 'active_sell' now): {strategy.pending_sell_orders}")

        # Simulate the corresponding sell order getting hit
        if any(o['status'] == 'active_sell' for o in strategy.pending_sell_orders):
            sell_order_to_fill = next(o for o in strategy.pending_sell_orders if o['status'] == 'active_sell')
            print(f"\n--- Simulating SELL order execution ---")
            print(f"Executing SELL: ID={sell_order_to_fill['id']}, Price={sell_order_to_fill['price']}, Size={sell_order_to_fill['size']}")
            # Example sell: price=100.0 (buy_price 99.5 + spacing 0.5), size=0.1. Revenue = 10.0. Fee = 10.0 * 0.005 = 0.05. PnL += (10.0 - 0.05) = 9.95
            # Expected PnL = -9.99975 (from buy) + 9.95 (from sell) = -0.04975
            if strategy.inventory >= sell_order_to_fill['size']:
                 strategy.execute_trade(trade_price=sell_order_to_fill['price'], trade_size=sell_order_to_fill['size'], is_buy_order=False)
                 print(f"PnL after SELL: {strategy.pnl:.4f}, Inventory: {strategy.inventory:.4f}")
                 # print(f"Pending sell orders: {strategy.pending_sell_orders}")
            else:
                print(f"Error: Not enough inventory ({strategy.inventory:.4f}) to fill sell order of size {sell_order_to_fill['size']:.4f}")

        # Clean up executed orders for the test of regenerating the grid
        strategy.active_buy_orders = [o for o in strategy.active_buy_orders if o['status'] == 'active']
        strategy.pending_sell_orders = [o for o in strategy.pending_sell_orders if o['status'] in ('pending_sell', 'active_sell')]

        print(f"\n--- After clearing executed orders ---")
        print(f"Inventory: {strategy.inventory:.4f}, Active buy orders: {len(strategy.active_buy_orders)}, Pending/Active sell orders: {len(strategy.pending_sell_orders)}")

        print("\n--- Calling generate_quotes() again (expecting new buy grid) ---")
        strategy.update_market_price(101.0) # Simulate market movement
        active_buy_prices, active_sell_prices = strategy.generate_quotes()
        print(f"New active buy prices: {active_buy_prices}, New active sell prices: {active_sell_prices}")
        # print(f"Current active_buy_orders: {strategy.active_buy_orders}")


    # --- Test case: no market price ---
    print("\n\n--- Test Case: No Market Price ---")
    strategy_no_price = GridTradingStrategy(
        quote_size=0.1, grid_levels=3, grid_spacing=0.2,
        price_rounding_rule=round_to_2_decimals, fees_bps=5, # 0.05% fee
        initial_balance=100.0
    )
    buys, sells = strategy_no_price.generate_quotes() # market_price is None
    print(f"Quotes with no market price: Buys={buys}, Sells={sells}")

    # --- Test PnL and inventory calculations carefully (with zero fees) ---
    print("\n\n--- Test Case: PnL and Inventory (Zero Fees) ---")
    strategy_test_zero_fees = GridTradingStrategy(
        quote_size=1.0, grid_levels=10, grid_spacing=0.1,
        price_rounding_rule=round_to_2_decimals, fees_bps=0, # Zero fees
        initial_balance=10000.0
    )
    strategy_test_zero_fees.update_market_price(100)
    print(f"Initial PnL (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}, Initial Balance: {strategy_test_zero_fees.initial_balance:.2f}")

    # Generate initial buy orders
    test_buy_prices, _ = strategy_test_zero_fees.generate_quotes()
    print(f"Test initial buy prices (Zero Fees): {test_buy_prices}")
    # print(f"Test active_buy_orders (Zero Fees): {strategy_test_zero_fees.active_buy_orders}")

    # Simulate a buy for strategy_test_zero_fees
    if strategy_test_zero_fees.active_buy_orders and any(o['status'] == 'active' for o in strategy_test_zero_fees.active_buy_orders):
        first_buy = strategy_test_zero_fees.active_buy_orders[0]
        print(f"\nSimulating BUY for strategy_test_zero_fees: Price={first_buy['price']}, Size={first_buy['size']}")
        strategy_test_zero_fees.execute_trade(trade_price=first_buy['price'], trade_size=first_buy['size'], is_buy_order=True)
        print(f"PnL after BUY (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}")

        # Activate its sell order
        _, test_sell_prices = strategy_test_zero_fees.generate_quotes()
        print(f"Active sell prices for strategy_test_zero_fees: {test_sell_prices}")

        # Simulate a sell for strategy_test_zero_fees
        if strategy_test_zero_fees.pending_sell_orders and any(o['status'] == 'active_sell' for o in strategy_test_zero_fees.pending_sell_orders):
            first_sell = strategy_test_zero_fees.pending_sell_orders[0]
            print(f"\nSimulating SELL for strategy_test_zero_fees: Price={first_sell['price']}, Size={first_sell['size']}")
            strategy_test_zero_fees.execute_trade(trade_price=first_sell['price'], trade_size=first_sell['size'], is_buy_order=False)
            print(f"PnL after SELL (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}")

    # --- Legacy manual PnL tests (can be removed or adapted if covered by above) ---
    # These tests directly call execute_trade without using generate_quotes, so they are simpler PnL checks.
    # Ensure they also use a strategy instance with specific fees if we want to test fees here.
    print("\n\n--- Legacy Manual PnL Tests (Zero Fees on strategy_test_zero_fees) ---")
    # Test with strategy_test_zero_fees which has 0 fees_bps
    print(f"Initial PnL for manual tests (Zero Fees): {strategy_test_zero_fees.pnl:.4f}")

    print("\nSimulating a manual sell for PnL test (Zero Fees)...")
    strategy_test_zero_fees.execute_trade(trade_price=100.5, trade_size=1.0, is_buy_order=False) # Sell before inventory is positive
    print(f"PnL after selling 1 unit at 100.5 (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}")

    print("\nSimulating a manual buy for PnL test (Zero Fees)...")
    strategy_test_zero_fees.execute_trade(trade_price=99.5, trade_size=1.0, is_buy_order=True)
    print(f"PnL after buying 1 unit at 99.5 (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}")

    strategy_test_zero_fees.execute_trade(trade_price=101, trade_size=0.5, is_buy_order=False)
    print(f"PnL after selling 0.5 unit at 101 (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}")

    strategy_test_zero_fees.execute_trade(trade_price=98, trade_size=0.2, is_buy_order=True)
    print(f"PnL after buying 0.2 unit at 98 (Zero Fees): {strategy_test_zero_fees.pnl:.4f}, Inventory: {strategy_test_zero_fees.inventory:.4f}")
