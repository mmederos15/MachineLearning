# -*- coding: utf-8 -*-
"""ObjectClassification.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1yxu94s7uNlWfJOPecuPOyr-faCA_ZbGW
"""

pip install --upgrade tensorflow keras

from google.colab import drive
drive.mount("/content/drive/")

# Commented out IPython magic to ensure Python compatibility.
# %cd drive/MyDrive/AML_EOS

import gc

gc.collect()

# Load COCO Annotations into Pandas DataFrame

import os
import pandas as pd
import json

# Define dataset path and annotations file paths
base_path = './SkyFusion'
subfolders = ['train', 'valid', 'test']

# Function to load annotations into Pandas DataFrame
def load_annotations(base_path, subfolders):
    dataframes = []
    for folder in subfolders:
        annotations_file = os.path.join(base_path, folder, '_annotations.coco.json')
        if os.path.exists(annotations_file):
            with open(annotations_file, 'r') as f:
                annotations = json.load(f)
                annotations_df = pd.DataFrame(annotations['annotations'])
                images_df = pd.DataFrame(annotations['images'])
                merged_df = pd.merge(
                    annotations_df, images_df[['id', 'file_name']],
                    left_on='image_id', right_on='id', how='left'
                )
                merged_df['image_folder'] = folder
                merged_df.drop(columns=['id_y'], inplace=True)
                merged_df.rename(columns={'id_x': 'annotation_id', 'file_name': 'image_file'}, inplace=True)
                dataframes.append(merged_df)
        else:
            print(f"Annotations file not found in {folder}.")

    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    else:
        return pd.DataFrame()

# Load the annotations into DataFrame
annotations_df = load_annotations(base_path, subfolders)

# Display the first few rows
if not annotations_df.empty:
    print("Loaded annotations:")
    display(annotations_df.head())
else:
    print("No annotations loaded.")

annotations_df

# Load COCO Annotations into Pandas DataFrame and Create DataLoader

import os
import pandas as pd
import json
import numpy as np
import cv2
from tensorflow.keras.utils import Sequence
from tensorflow import keras
from tensorflow.keras import layers, models, applications

# Define dataset path and annotations file paths
base_path = './SkyFusion'
subfolders = ['train', 'valid', 'test']

# Function to load annotations into Pandas DataFrame
def load_annotations(base_path, subfolders):
    dataframes = []
    for folder in subfolders:
        annotations_file = os.path.join(base_path, folder, '_annotations.coco.json')
        if os.path.exists(annotations_file):
            with open(annotations_file, 'r') as f:
                annotations = json.load(f)
                annotations_df = pd.DataFrame(annotations['annotations'])
                images_df = pd.DataFrame(annotations['images'])
                merged_df = pd.merge(
                    annotations_df, images_df[['id', 'file_name']],
                    left_on='image_id', right_on='id', how='left'
                )
                merged_df['image_folder'] = folder
                merged_df.drop(columns=['id_y'], inplace=True)
                merged_df.rename(columns={'id_x': 'annotation_id', 'file_name': 'image_file'}, inplace=True)
                dataframes.append(merged_df)
        else:
            print(f"Annotations file not found in {folder}.")

    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    else:
        return pd.DataFrame()

# Load the annotations into DataFrame
annotations_df = load_annotations(base_path, subfolders)

# Display the first few rows
if not annotations_df.empty:
    print("Loaded annotations:")
    display(annotations_df.head())
else:
    print("No annotations loaded.")

# Define DataLoader Class
class SkyFusionDataLoader(Sequence):
    def __init__(self, annotations_df, base_path, batch_size=16, target_size=(640, 640), grid_size=(10, 10)):
        super().__init__()
        self.annotations_df = annotations_df
        self.base_path = base_path
        self.batch_size = batch_size
        self.target_size = target_size
        self.grid_size = grid_size
        self.image_paths = self.annotations_df[['image_folder', 'image_file']].drop_duplicates().values

    def __len__(self):
        return int(np.ceil(len(self.image_paths) / self.batch_size))

    def __getitem__(self, idx):
        batch_files = self.image_paths[idx * self.batch_size:(idx + 1) * self.batch_size]
        images = []
        bbox_labels = np.zeros((len(batch_files), *self.grid_size, 4))
        class_labels = np.zeros((len(batch_files), *self.grid_size, 80))

        for i, (folder, file_name) in enumerate(batch_files):
            image_path = os.path.join(self.base_path, folder, file_name)
            image = cv2.imread(image_path)
            if image is not None:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                image = cv2.resize(image, self.target_size) / 255.0
                images.append(image)

                # Extract labels from annotations
                image_annotations = self.annotations_df[self.annotations_df['image_file'] == file_name]
                for _, annotation in image_annotations.iterrows():
                    x, y, width, height = annotation['bbox']
                    category_id = int(annotation['category_id'])

                    # Ensure category_id is within bounds
                    if 0 <= category_id < 80:
                        # Normalize bbox coordinates
                        x_center = (x + width / 2) / self.target_size[0]
                        y_center = (y + height / 2) / self.target_size[1]
                        norm_width = width / self.target_size[0]
                        norm_height = height / self.target_size[1]

                        # Map to grid cells
                        grid_x = int(x_center * self.grid_size[1])
                        grid_y = int(y_center * self.grid_size[0])

                        bbox_labels[i, grid_y, grid_x] = [x_center, y_center, norm_width, norm_height]
                        class_labels[i, grid_y, grid_x, category_id] = 1
            else:
                print(f"Warning: Could not load image {image_path}")

        return np.array(images), {"bbox": bbox_labels, "class": class_labels}

# Create DataLoader Instance
train_loader = SkyFusionDataLoader(annotations_df, base_path, batch_size=16, grid_size=(10, 10))

# Define Convolutional Block

def conv_bn_silu(x, filters, kernel_size, strides=1):
    x = layers.Conv2D(filters, kernel_size, strides=strides, padding="same", use_bias=False)(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("swish")(x)
    return x

# Build YOLOv8 Model with EfficientNetV2 Backbone

def build_hybrid_yolov8_model(input_shape=(640, 640, 3), num_classes=80, grid_size=(10, 10)):
    inputs = layers.Input(shape=input_shape)

    # EfficientNetV2 Backbone
    backbone = applications.EfficientNetV2B0(include_top=False, input_tensor=inputs, weights="imagenet")
    x = backbone.output

    # CSPDarknet-Like Head
    x = conv_bn_silu(x, 512, 3, 1)
    x = conv_bn_silu(x, 1024, 3, 2)

    # YOLO Head
    bbox_outputs = layers.Conv2D(4, (1, 1), activation='sigmoid', name='bbox')(x)
    class_outputs = layers.Conv2D(num_classes, (1, 1), activation='softmax', name='class')(x)

    model = models.Model(inputs, [bbox_outputs, class_outputs])
    return model

model = build_hybrid_yolov8_model(grid_size=(10, 10))

model.compile(
    optimizer=keras.optimizers.Adam(learning_rate=3e-4),
    loss={"bbox": keras.losses.Huber(delta=1.0), "class": keras.losses.CategoricalCrossentropy()},
    loss_weights={"bbox": 1.0, "class": 1.0},
    metrics={"bbox": "mse", "class": "accuracy"}
)

# Train the Model
model.fit(
    train_loader,
    epochs=10
)

print("Model training complete!")

# Load COCO Annotations into Pandas DataFrame and Create DataLoader

import os
import pandas as pd
import json
import numpy as np
import cv2
import matplotlib.pyplot as plt
from tensorflow.keras.utils import Sequence
from tensorflow import keras
from tensorflow.keras import layers, models

# Define dataset path and annotations file paths
base_path = './SkyFusion'
subfolders = ['train', 'valid', 'test']

# Function to visualize bounding boxes
def visualize_image_with_boxes(image, annotations, target_size=(640, 640)):
    image = cv2.resize(image, target_size)
    for annotation in annotations:
        x, y, width, height = annotation['bbox']
        category_id = annotation['category_id']
        class_label = str(category_id)

        # Draw bounding box
        top_left = (int(x), int(y))
        bottom_right = (int(x + width), int(y + height))
        image = cv2.rectangle(image, top_left, bottom_right, (255, 0, 0), 2)
        image = cv2.putText(image, class_label, (int(x), int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    plt.figure(figsize=(8, 8))
    plt.imshow(image)
    plt.axis('off')
    plt.show()

# Display Sample Images with Bounding Boxes
def display_samples(annotations_df, base_path, num_samples=5):
    sample_images = annotations_df.sample(n=num_samples)
    for _, row in sample_images.iterrows():
        folder = row['image_folder']
        file_name = row['image_file']
        image_path = os.path.join(base_path, folder, file_name)

        # Load and display image
        image = cv2.imread(image_path)
        if image is not None:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image_annotations = annotations_df[annotations_df['image_file'] == file_name]
            visualize_image_with_boxes(image, image_annotations.to_dict('records'))
        else:
            print(f"Warning: Could not load image {image_path}")

# Display example images with bounding boxes
display_samples(annotations_df, base_path, num_samples=5)