import numpy as np
import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf
from tensorflow.keras.datasets import fashion_mnist
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Flatten
from tensorflow.keras.utils import to_categorical

tf.get_logger().setLevel("ERROR")


def do_active(target_labels, sample_size, version_no, *args):

    # Load the dataset
    _, (test_images, test_labels) = fashion_mnist.load_data()

    # Normalize the images to values between 0 and 1
    test_images = test_images / 255.0

    # Convert labels to one-hot encoded format

    mask = np.isin(test_labels, target_labels)
    target = test_images[mask]
    indices = np.random.choice(len(target), size=sample_size, replace=False)
    sample = target[indices]
    label_sample = test_labels[mask][indices]

    # Convert labels to one-hot encoded format
    test_labels = to_categorical(label_sample, num_classes=10)

    model = tf.keras.models.load_model(f"al_fashion/mnist_model.v{version_no}.keras")

    # Evaluate the model
    loss, acc = model.evaluate(sample, test_labels)

    if acc > 0.85:
        # good!
        return True

    return acc > 0.85
