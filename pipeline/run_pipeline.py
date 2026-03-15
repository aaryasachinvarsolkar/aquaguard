import os

print("Running feature engineering...")

os.system("python pipeline/feature_engineering.py")

print("Running prediction pipeline...")

os.system("python pipeline/prediction_pipeline.py")

print("Pipeline completed.")