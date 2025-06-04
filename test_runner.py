import sys
import os
from main import main as main_function

# Sample data provided by the user
sample_data = '''40622813,580925.00000000,0.00007000,40.66475000,1733011200869,False,True
40622814,580915.00000000,0.00021000,121.99215000,1733011210217,True,True
40622815,580924.00000000,0.00017000,98.75708000,1733011217407,False,True
40622816,580902.00000000,0.00004000,23.23608000,1733011217507,True,True
40622817,580863.00000000,0.00002000,11.61726000,1733011217507,True,True
40622818,580857.00000000,0.01094000,6354.57558000,1733011219554,False,True
40622819,580856.00000000,0.02185000,12691.70360000,1733011230400,True,True
40622820,580801.00000000,0.00002000,11.61602000,1733011230695,False,True
40622821,580800.00000000,0.00300000,1742.40000000,1733011232686,True,True
40622822,580801.00000000,0.00034000,197.47234000,1733011234789,False,True
40622823,580801.00000000,0.00004000,23.23204000,1733011239821,False,True
40622824,580801.00000000,0.00017000,98.73617000,1733011241481,False,True
40622825,580800.00000000,0.00054000,313.63200000,1733011245119,True,True
40622826,580801.00000000,0.00086000,499.48886000,1733011247889,False,True
40622827,580800.00000000,0.00035000,203.28000000,1733011254387,True,True
40622828,580800.00000000,0.00860000,4994.88000000,1733011254387,True,True
40622829,580750.00000000,0.02390000,13879.92500000,1733011254393,True,True
40622830,580750.00000000,0.01630000,9466.22500000,1733011254399,True,True
40622831,580750.00000000,0.01280000,7433.60000000,1733011254399,True,True
40622832,580751.00000000,0.00006000,34.84506000,1733011265676,False,True'''

data_file_path = 'data/sample_trades.csv'

# Create the data directory if it doesn't exist
os.makedirs(os.path.dirname(data_file_path), exist_ok=True)

# Write the sample data to the file
with open(data_file_path, 'w') as f:
    f.write(sample_data)

print(f"Created {data_file_path} with sample data.")

# Simulate command line arguments for main.py
sys.argv = [
    'main.py',
    '--data_file', data_file_path,
    '--order_size', '0.01',
    '--spread_min_bps', '0',
    '--spread_max_bps', '10',
    '--spread_step_bps', '2'
]

print(f"Running main_function with args: {sys.argv}")
try:
    main_function()
    print("Main function executed successfully.")
except Exception as e:
    print(f"Error running main_function: {e}")
    raise # Re-raise the exception to fail the subtask if needed

# Check if plot files were created (optional, as main_function prints their names)
expected_plots = ['optimization_plot_pnl_vs_spread.png', 'optimization_plot_trades_vs_spread.png']
for plot_file in expected_plots:
    if os.path.exists(plot_file):
        print(f"Plot file {plot_file} created.")
    else:
        print(f"Warning: Plot file {plot_file} was not found.")

print("Test runner script finished.")
