import pandas as pd
from sklearn.utils import resample

df = pd.read_csv("data_processed/ocean_master_dataset.csv")

# Feature
df["turbidity"] = df["chlorophyll"] * 0.25

# ✅ Better bloom logic
df["bloom"] = (
    (df["chlorophyll"] > 2.0) &
    (df["temperature"] > 26)
).astype(int)

# ✅ Better risk logic (NOT too aggressive)
df["risk"] = (
    (df["chlorophyll"] > 3.0) |
    (df["temperature"] > 30) |
    (df["turbidity"] > 0.8)
).astype(int)

# ✅ Balance dataset
df_majority = df[df["risk"] == 0]
df_minority = df[df["risk"] == 1]

df_minority_upsampled = resample(
    df_minority,
    replace=True,
    n_samples=len(df_majority),
    random_state=42
)

df = pd.concat([df_majority, df_minority_upsampled])

print(df["risk"].value_counts())

df.to_csv("data_processed/training_dataset.csv", index=False)

print("✅ Training dataset created successfully")