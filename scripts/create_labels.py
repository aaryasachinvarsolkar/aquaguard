# Bloom conditions (realistic)
df["bloom"] = (
    (df["chlorophyll"] > 1.5) &
    (df["temperature"] > 25)
).astype(int)

# Risk conditions (combined factors)
df["risk"] = (
    (df["chlorophyll"] > 2.0) |
    (df["temperature"] > 28) |
    (df["turbidity"] > 0.5)
).astype(int)

from sklearn.utils import resample

# Separate classes
df_majority = df[df["risk"] == 0]
df_minority = df[df["risk"] == 1]

# Upsample minority
df_minority_upsampled = resample(
    df_minority,
    replace=True,
    n_samples=len(df_majority),
    random_state=42
)

df_balanced = pd.concat([df_majority, df_minority_upsampled])