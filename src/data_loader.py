import os

import pandas as pd

DATA_DIR = '..\\data'
DEFAULT_NAMES = ['trade_id', 'price', 'size', 'quote_size', 'time', 'buyer_maker', 'best_match']

def load_trade_data(file_path: str) -> pd.DataFrame:
    """
    Loads trade data from a CSV file, performs type conversions, and returns a pandas DataFrame.

    Args:
        file_path: The path to the CSV file.

    Returns:
        A pandas DataFrame with the loaded and processed trade data.
        Returns an empty DataFrame if an error occurs.
    """
    try:
        full_path = os.path.join(DATA_DIR, file_path)
        df = pd.read_csv(full_path, names=DEFAULT_NAMES)

        # Convert numeric columns
        for col in ['price', 'size', 'quote_size']:
            df[col] = pd.to_numeric(df[col])

        # Convert time column
        df['time'] = pd.to_datetime(df['time'], unit='ms')

        # Convert boolean columns
        bool_map = {
            'True': True, 'true': True, 'TRUE': True, '1': True, 1: True,
            'False': False, 'false': False, 'FALSE': False, '0': False, 0: False
        }
        for col in ['buyer_maker', 'best_match']:
            # If pandas didn't infer bool, and it's object type (likely strings)
            if df[col].dtype == 'object':
                df[col] = df[col].map(bool_map)
            # Ensure final type is bool, handling cases where it might be int (0,1) or already bool
            df[col] = df[col].astype(bool)

        return df
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return pd.DataFrame()
    except pd.errors.ParserError:
        print(f"Error: Could not parse CSV file at {file_path}")
        return pd.DataFrame()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return pd.DataFrame()

if __name__ == '__main__':
    # Example usage:
    sample_file = 'data/sample_trades.csv' # Path when running from project root
    trade_df = load_trade_data(sample_file)
    if not trade_df.empty:
        print("Trade data loaded successfully:")
        print(trade_df.head())
        print("\nData types:")
        print(trade_df.dtypes)
