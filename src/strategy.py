class MarketMakingStrategy:
    """
    A simple market making strategy that places bid and ask quotes around a current market price.
    It also tracks Profit and Loss (PnL) and inventory.
    """

    def __init__(self, quote_size: float):
        """
        Initializes the MarketMakingStrategy.

        Args:
            quote_size: The amount of base asset to be used for each quote.
                        This is the amount the strategy is willing to buy or sell at its quoted prices.
        """
        self.current_market_price: float | None = None
        self.pnl: float = 0.0
        self.inventory: float = 0.0  # Amount of base asset held
        self.quote_size: float = quote_size
        self.last_bid_quote: float | None = None
        self.last_ask_quote: float | None = None

    def update_market_price(self, current_price: float):
        """
        Updates the current market price observed by the strategy.

        Args:
            current_price: The latest market price.
        """
        self.current_market_price = current_price

    def generate_quotes(self, spread_bps: int) -> tuple[float | None, float | None]:
        """
        Generates bid and ask quotes based on the current market price and a given spread.

        Args:
            spread_bps: The desired spread in basis points (1 bps = 0.01%).
                        The bid and ask prices will be set symmetrically around the current market price.

        Returns:
            A tuple (bid_price, ask_price). Returns (None, None) if the current market price is not available.
        """
        if self.current_market_price is None:
            self.last_bid_quote = None
            self.last_ask_quote = None
            return None, None

        half_spread_multiplier = spread_bps / 10000 / 2
        bid_price = self.current_market_price * (1 - half_spread_multiplier)
        ask_price = self.current_market_price * (1 + half_spread_multiplier)

        self.last_bid_quote = bid_price
        self.last_ask_quote = ask_price

        return bid_price, ask_price

    def execute_trade(self, trade_price: float, trade_size: float, is_buy_order: bool):
        """
        Records a trade execution, updating PnL and inventory.

        This method is called by the backtester when one of the strategy's quotes is hit.

        Args:
            trade_price: The price at which the trade was executed.
            trade_size: The amount of asset traded.
            is_buy_order: True if the strategy's buy quote was hit (strategy buys),
                          False if the strategy's sell quote was hit (strategy sells).
        """
        if is_buy_order:
            # Strategy buys the base asset
            self.pnl -= trade_price * trade_size  # Cash decreases
            self.inventory += trade_size         # Base asset increases
        else:
            # Strategy sells the base asset
            self.pnl += trade_price * trade_size  # Cash increases
            self.inventory -= trade_size         # Base asset decreases

if __name__ == '__main__':
    # Example Usage
    strategy = MarketMakingStrategy(quote_size=0.1) # Strategy will quote for 0.1 units of base asset

    # Simulate updating market price
    strategy.update_market_price(100.0)
    print(f"Initial PnL: {strategy.pnl}, Inventory: {strategy.inventory}")

    # Generate quotes
    bid, ask = strategy.generate_quotes(spread_bps=20) # 20 bps spread (0.2%)
    print(f"Generated quotes: Bid = {bid}, Ask = {ask} for size {strategy.quote_size}")

    if bid and ask:
        # Simulate a scenario where our ask quote is hit (strategy sells)
        print(f"\nSimulating our Ask quote being hit (strategy sells {strategy.quote_size} base asset at {ask})")
        strategy.execute_trade(trade_price=ask, trade_size=strategy.quote_size, is_buy_order=False)
        print(f"PnL after selling: {strategy.pnl:.2f}, Inventory: {strategy.inventory:.2f}")

        # Simulate a new market price
        strategy.update_market_price(99.0)
        new_bid, new_ask = strategy.generate_quotes(spread_bps=20)
        print(f"\nNew market price: 99.0. Generated quotes: Bid = {new_bid}, Ask = {new_ask}")

        # Simulate a scenario where our bid quote is hit (strategy buys)
        if new_bid:
            print(f"\nSimulating our Bid quote being hit (strategy buys {strategy.quote_size} base asset at {new_bid})")
            strategy.execute_trade(trade_price=new_bid, trade_size=strategy.quote_size, is_buy_order=True)
            print(f"PnL after buying: {strategy.pnl:.2f}, Inventory: {strategy.inventory:.2f}")

    # Test case: no market price
    strategy_no_price = MarketMakingStrategy(quote_size=0.1)
    bid_no_price, ask_no_price = strategy_no_price.generate_quotes(spread_bps=20)
    print(f"\nQuotes with no market price: Bid = {bid_no_price}, Ask = {ask_no_price}")

    # Test PnL and inventory calculations carefully
    strategy_test = MarketMakingStrategy(quote_size=1.0) # 1 unit of base asset
    strategy_test.update_market_price(100)
    test_bid, test_ask = strategy_test.generate_quotes(spread_bps=100) # 1% spread -> Bid 99.5, Ask 100.5

    print(f"\nTest Strategy: Initial PnL: {strategy_test.pnl}, Inventory: {strategy_test.inventory}")
    print(f"Test Quotes: Bid={test_bid}, Ask={test_ask} for size {strategy_test.quote_size}")

    # Sell 1 unit at ask price 100.5
    strategy_test.execute_trade(trade_price=100.5, trade_size=1.0, is_buy_order=False)
    print(f"After selling 1 unit at 100.5: PnL={strategy_test.pnl}, Inventory={strategy_test.inventory}") # PnL = 100.5, Inv = -1

    # Buy 1 unit at bid price 99.5 (assume market moved and our new bid is hit)
    # For this test, let's assume the bid we placed (99.5) got hit.
    strategy_test.execute_trade(trade_price=99.5, trade_size=1.0, is_buy_order=True)
    print(f"After buying 1 unit at 99.5: PnL={strategy_test.pnl}, Inventory={strategy_test.inventory}") # PnL = 100.5 - 99.5 = 1, Inv = 0

    # Sell 0.5 unit at 101
    strategy_test.execute_trade(trade_price=101, trade_size=0.5, is_buy_order=False)
    print(f"After selling 0.5 unit at 101: PnL={strategy_test.pnl}, Inventory={strategy_test.inventory}") # PnL = 1 + 0.5*101 = 51.5, Inv = -0.5

    # Buy 0.2 unit at 98
    strategy_test.execute_trade(trade_price=98, trade_size=0.2, is_buy_order=True)
    # PnL = 51.5 - (98 * 0.2) = 51.5 - 19.6 = 31.9
    # Inv = -0.5 + 0.2 = -0.3
    print(f"After buying 0.2 unit at 98: PnL={strategy_test.pnl:.2f}, Inventory={strategy_test.inventory:.2f}")
