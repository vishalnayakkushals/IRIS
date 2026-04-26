import os
import shutil
from pathlib import Path

def generate_mock_data():
    base_dir = Path("C:/Users/Kushals.DESKTOP-D51MT8S/Desktop/Github/IRIS/data/stores")
    
    stores = [f"TEST_STORE_MOCK_{i}" for i in range(1, 7)] # 6 stores
    cameras = ["CAM01", "CAM02"] # 2 cameras
    images_per_camera = 100 # Simulating an hour's worth per run context instead of 103k real ones for disk space

    # create a dummy image
    dummy_img_path = Path("dummy.jpg")
    if not dummy_img_path.exists():
        with open(dummy_img_path, "wb") as f:
            f.write(b"MOCK_IMAGE_DATA")

    for store in stores:
        store_path = base_dir / store
        store_path.mkdir(parents=True, exist_ok=True)
        
        print(f"Generating mock data for {store}...")
        for cam in cameras:
            for i in range(images_per_camera):
                # Format: HH-MM-SS_CAM-N.jpg
                filename = f"12-00-{i:02d}_{cam}-1.jpg"
                dest = store_path / filename
                if not dest.exists():
                    shutil.copy(dummy_img_path, dest)
                    
    print("Mock generation complete.")

if __name__ == "__main__":
    generate_mock_data()
