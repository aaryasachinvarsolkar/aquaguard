from PIL import Image
import os

input_folder="../../data_raw/satellite_images/"
output_folder="../../data_processed/satellite_images/"

os.makedirs(output_folder,exist_ok=True)

for file in os.listdir(input_folder):

    img = Image.open(input_folder+file)

    img = img.resize((256,256))

    img.save(output_folder+file)

print("Satellite images processed")