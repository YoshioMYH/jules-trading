import pytest
import pandas as pd
from io import StringIO
import os

from src.data_loader import load_trade_data

@pytest.fixture
def temp_csv_file(tmp_path):
    """Create a temporary CSV file for testing."""
    csv_content = (
        "trade_id,price,size,quote_size,time,buyer_maker,best_match\n"
        "40622813,580925.0,0.00007,40.66475,1733011200869,False,True\n"
        "40622814,580915.0,0.00021,121.99215,1733011210217,True,True\n"
        "40622815,580924.0,0.00017,98.75708,1733011217407,false,true\n" # Test lowercase bools
    )
    file_path = tmp_path / "sample_trades.csv"
    file_path.write_text(csv_content)
    return str(file_path)

class TestDataLoader:

    def test_successful_loading_and_types(self, temp_csv_file):
        """Test successful loading of a CSV and correct type conversions."""
        df = load_trade_data(temp_csv_file)

        assert isinstance(df, pd.DataFrame), "Should return a pandas DataFrame"
        assert not df.empty, "DataFrame should not be empty"

        expected_columns = ['trade_id', 'price', 'size', 'quote_size', 'time', 'buyer_maker', 'best_match']
        assert list(df.columns) == expected_columns, "DataFrame columns are incorrect"

        assert df['price'].dtype == float, "Price column should be float"
        assert df['size'].dtype == float, "Size column should be float"
        assert df['quote_size'].dtype == float, "Quote_size column should be float"
        assert pd.api.types.is_datetime64_any_dtype(df['time']), "Time column should be datetime"
        assert df['buyer_maker'].dtype == bool, "buyer_maker column should be boolean"
        assert df['best_match'].dtype == bool, "best_match column should be boolean"

        # Check a specific value conversion for boolean
        assert df.loc[df['trade_id'] == 40622815, 'buyer_maker'].iloc[0] == False, "Lowercase 'false' not converted to bool"

    def test_file_not_found(self):
        """Test handling of a non-existent file."""
        # The function currently prints an error and returns an empty DataFrame.
        # It doesn't raise FileNotFoundError itself, pandas.read_csv does if not handled.
        # Let's check for the empty DataFrame return.
        non_existent_file = "non_existent_test_file.csv"
        # Ensure file does not exist, to avoid flakey tests
        if os.path.exists(non_existent_file):
            os.remove(non_existent_file)

        df = load_trade_data(non_existent_file)
        assert df.empty, "Should return an empty DataFrame for a non-existent file"

    def test_malformed_csv(self, tmp_path):
        """Test handling of a malformed CSV file."""
        malformed_csv_content = (
            "trade_id,price,size\n"
            "1,100.0,0.1,extra_column\n"  # Extra value
            "2,200.0\n"                   # Missing value
        )
        file_path = tmp_path / "malformed.csv"
        file_path.write_text(malformed_csv_content)

        # Based on current implementation, load_trade_data catches pd.errors.ParserError
        # and returns an empty DataFrame.
        df = load_trade_data(str(file_path))
        assert df.empty, "Should return an empty DataFrame for a malformed CSV"

    def test_empty_csv(self, tmp_path):
        """Test handling of an empty CSV file (only headers)."""
        empty_csv_content = "trade_id,price,size,quote_size,time,buyer_maker,best_match\n"
        file_path = tmp_path / "empty.csv"
        file_path.write_text(empty_csv_content)

        df = load_trade_data(str(file_path))
        assert df.empty, "Should return an empty DataFrame for an empty CSV"

    def test_csv_with_only_headers(self, tmp_path):
        """Test handling of a CSV file that only contains the header row."""
        header_only_content = "trade_id,price,size,quote_size,time,buyer_maker,best_match\n"
        file_path = tmp_path / "header_only.csv"
        file_path.write_text(header_only_content)
        df = load_trade_data(str(file_path))
        assert df.empty
        # Additionally, check columns if an empty df with columns is returned
        if not df.empty: # Should be empty based on current pandas behavior with empty CSVs
             expected_columns = ['trade_id', 'price', 'size', 'quote_size', 'time', 'buyer_maker', 'best_match']
             assert list(df.columns) == expected_columns

    def test_csv_with_mixed_boolean_representations(self, tmp_path):
        """Test boolean conversion for various representations like True/False, true/false, 1/0."""
        csv_content = (
            "trade_id,price,size,quote_size,time,buyer_maker,best_match\n"
            "1,100,1,100,1733011200000,True,true\n"
            "2,200,2,200,1733011200001,FALSE,FALSE\n"
            # Pandas by default doesn't convert '1'/'0' to bool directly with read_csv unless specific converters are used.
            # The current load_trade_data uses .astype(bool) which converts non-empty strings/non-zero numbers to True.
            # This test will reflect the current behavior.
            "3,300,3,300,1733011200002,1,0\n" # '1' -> True, '0' -> True (as non-empty string before astype)
        )
        file_path = tmp_path / "bool_test.csv"
        file_path.write_text(csv_content)
        df = load_trade_data(str(file_path))

        assert df.loc[df['trade_id'] == 1, 'buyer_maker'].iloc[0] == True
        assert df.loc[df['trade_id'] == 1, 'best_match'].iloc[0] == True
        assert df.loc[df['trade_id'] == 2, 'buyer_maker'].iloc[0] == False
        assert df.loc[df['trade_id'] == 2, 'best_match'].iloc[0] == False

        # Current astype(bool) behavior for strings '1' and '0':
        # String '1' becomes True, String '0' becomes True.
        # If they were numeric 1/0, they would be True/False.
        # This depends on how read_csv initially interprets them.
        # If read_csv interprets '1' as int 1, then .astype(bool) -> True
        # If read_csv interprets '0' as int 0, then .astype(bool) -> False
        # It seems read_csv by default will try to infer types. If a column is mixed (e.g. "True", "0"), it might keep as object.
        # Let's assume they are read as strings if mixed with True/False strings.
        assert df.loc[df['trade_id'] == 3, 'buyer_maker'].iloc[0] == True # '1' should map to True
        assert df.loc[df['trade_id'] == 3, 'best_match'].iloc[0] == False # '0' should map to False with the new bool_map
                                                                        # If the column was purely 1s and 0s, pandas might make it int, then bool conversion works as expected.
                                                                        # Given the mix, it likely stays as object/string before .astype(bool).
                                                                        # To fix this, a more explicit mapping for boolean columns would be needed in load_trade_data.
                                                                        # For now, the test reflects current behavior.

    # Acknowledging the boolean conversion nuance for '0' string.
    # If the requirement is that string '0' should be False, load_trade_data needs adjustment.
    # Example: df[col] = df[col].replace({'True': True, 'False': False, 'true': True, 'false': False, '1': True, '0': False}).astype(bool)
    # For now, this test documents the current state.
    def test_boolean_string_zero_behavior(self, tmp_path):
        """Test that load_trade_data correctly converts string '0' to False."""
        # Using column names that load_trade_data expects for boolean conversion
        csv_content = "trade_id,price,size,quote_size,time,buyer_maker,best_match\n1,100,1,1,1,0,0"
        file_path = tmp_path / "string_zero_for_loader.csv"
        file_path.write_text(csv_content)

        df = load_trade_data(str(file_path))

        assert df.loc[df['trade_id'] == 1, 'buyer_maker'].iloc[0] == False, "String '0' in buyer_maker should be False after load_trade_data"
        assert df.loc[df['trade_id'] == 1, 'best_match'].iloc[0] == False, "String '0' in best_match should be False after load_trade_data"

# To make the boolean test for '0' more robust within load_trade_data context:
# We need to ensure 'buyer_maker'/'best_match' are read as strings if they contain '0'/'1' mixed with 'True'/'False'
# The current load_trade_data directly calls read_csv then astype.
# The test `test_csv_with_mixed_boolean_representations` covers this as part of a larger CSV.
# The `test_boolean_string_zero_behavior` fixture is more of a unit test for `astype(bool)` on a string column.
# The above refined test now correctly tests load_trade_data's behavior.
