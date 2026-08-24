# given array of inputs,
# return the array of outputs according to the dataset


import numpy as np

from tensorflow.keras.datasets import fashion_mnist
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Flatten
from tensorflow.keras.utils import to_categorical
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

rng = np.random.default_rng(57)


def do_simulation(target_labels, sample_size):
    # return samples of given label and sample size.

    # Load the dataset
    (train_images, train_labels), (test_images, test_labels) = fashion_mnist.load_data()

    # Normalize the images to values between 0 and 1
    train_images = train_images / 255.0
    # test_images = test_images / 255.0

    # Convert labels to one-hot encoded format

    mask = np.isin(train_labels, target_labels)

    target = train_images[mask]
    indices = np.random.choice(len(target), size=sample_size, replace=False)
    sample = target[indices]

    return sample, train_labels[mask][indices]


# Function to plot images and their predictions
def plot_image(p_label, true_label, img):
    plt.grid(False)
    plt.xticks([])
    plt.yticks([])

    plt.imshow(img, cmap=plt.cm.binary)

    if p_label is None:
        plt.xlabel(f"True: {true_label}", color="blue")
        return

    if p_label == true_label:
        color = "blue"
    else:
        color = "red"

    plt.xlabel(f"Predicted: {p_label} (True: {true_label})", color=color)


# plt.figure()
# plot_image(0, [1], [1], do_simulation(1, 2))
# plt.show()
