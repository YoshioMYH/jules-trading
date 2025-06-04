import pandas as pd
import numpy as np

def permute_trade_data(df: pd.DataFrame, column_to_shuffle: str = 'price') -> pd.DataFrame:
    """
    Permutes (shuffles) a specified column in a pandas DataFrame.

    Args:
        df: The input pandas DataFrame.
        column_to_shuffle: The name of the column to shuffle. Defaults to 'price'.

    Returns:
        A new DataFrame with the specified column shuffled.
        Returns an empty DataFrame if the column to shuffle does not exist.
    """
    if column_to_shuffle not in df.columns:
        print(f"Error: Column '{column_to_shuffle}' not found in DataFrame. Returning original DataFrame.")
        return df # Or raise an error, or return df.copy()

    df_copy = df.copy()

    # Shuffle the specified column.
    # .values is important to ensure proper assignment when index is not 0-based or has gaps.
    shuffled_values = df_copy[column_to_shuffle].sample(frac=1, random_state=np.random.RandomState()).values
    df_copy[column_to_shuffle] = shuffled_values

    return df_copy

if __name__ == '__main__':
    # Example Usage
    data = {
        'time': pd.to_datetime(['2023-01-01 10:00:00', '2023-01-01 10:00:01', '2023-01-01 10:00:02', '2023-01-01 10:00:03']),
        'price': [100.0, 101.0, 100.5, 102.0],
        'size': [1, 0.5, 0.8, 1.2]
    }
    sample_df = pd.DataFrame(data)

    print("Original DataFrame:")
    print(sample_df)

    shuffled_df_price = permute_trade_data(sample_df, 'price')
    print("\nDataFrame with 'price' column shuffled:")
    print(shuffled_df_price)

    # Verify original is not modified
    print("\nOriginal DataFrame (should be unchanged):")
    print(sample_df)

    shuffled_df_size = permute_trade_data(sample_df, 'size')
    print("\nDataFrame with 'size' column shuffled:")
    print(shuffled_df_size)

    # Test with a non-existent column
    shuffled_df_error = permute_trade_data(sample_df, 'non_existent_column')
    print("\nDataFrame with non-existent column shuffle attempt:")
    print(shuffled_df_error)
