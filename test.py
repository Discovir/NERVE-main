import pandas as pd

df = pd.read_csv("emg_data.csv")

print(df['phase'].value_counts())
print()

# Each unique window_id is one rep
clench_windows = df[df['phase'] == 'clench']['window_id'].unique()
print(f"Total clench reps recorded: {len(clench_windows)}")
print()

# How many samples per rep
for i, wid in enumerate(clench_windows, 1):
    n = len(df[df['window_id'] == wid])
    print(f"  Rep {i:>2}  window_id={wid}  →  {n} samples  (~{n/1000:.1f}s)")
