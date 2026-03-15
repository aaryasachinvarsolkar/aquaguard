import time
import os

while True:

    print("Running automated pipeline...")

    os.system("python pipeline/run_pipeline.py")

    print("Waiting 5 days...")

    time.sleep(60 * 60 * 24 * 5)