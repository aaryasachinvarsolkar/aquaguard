import tensorflow as tf
from tensorflow.keras import layers, models
import os

print("Creating CNN model...")

# Ensure models directory exists
os.makedirs("models", exist_ok=True)

# Define CNN Model
model = models.Sequential([
    
    layers.Input(shape=(128,128,3)),

    layers.Conv2D(32, (3,3), activation='relu'),
    layers.MaxPooling2D(2,2),

    layers.Conv2D(64, (3,3), activation='relu'),
    layers.MaxPooling2D(2,2),

    layers.Conv2D(128, (3,3), activation='relu'),
    layers.MaxPooling2D(2,2),

    layers.Flatten(),

    layers.Dense(128, activation='relu'),
    layers.Dense(1, activation='sigmoid')
])

# Compile model
model.compile(
    optimizer='adam',
    loss='binary_crossentropy',
    metrics=['accuracy']
)

print("Model created successfully\n")

# Show architecture
model.summary()

# Save model
model.save("models/oil_spill_model.keras")

print("\nOil spill CNN model saved successfully.")