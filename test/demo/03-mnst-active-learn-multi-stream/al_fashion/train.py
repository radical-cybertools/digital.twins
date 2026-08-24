import numpy as np
import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf
from tensorflow.keras.datasets import mnist
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Flatten
from tensorflow.keras.utils import to_categorical

# TODO.... Big bug!!
# Currently, the do_train() method is shared as is between the fashion and hand
# digits! This means the same file (model) is being used for both.... this is a
# logic error.
#
#


def do_train(train_images, train_labels, version_no):

    # Convert labels to one-hot encoded format
    # labels are all the same: length

    train_labels = to_categorical(train_labels, num_classes=10)

    if version_no != 0:
        model = tf.keras.models.load_model(
            f"al_fashion/mnist_model.v{version_no - 1}.keras"
        )
    else:

        # Create the neural network model
        model = Sequential(
            [
                Flatten(
                    input_shape=(28, 28)
                ),  # Flatten the 28x28 images into a 1D array
                Dense(128, activation="relu"),  # Fully connected layer with 128 neurons
                Dropout(0.1),  # 10% dropout
                Dense(64, activation="relu"),  # Fully connected layer with 128 neurons
                Dense(
                    10, activation="softmax"
                ),  # Output layer for 10 classes (digits 0-9)
            ]
        )

        # Compile the model
        model.compile(
            optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"]
        )

    # Train the model
    model.fit(train_images, train_labels, epochs=10, batch_size=32)

    # Save the model if needed
    model.save(f"al_fashion/mnist_model.v{version_no}.keras")
    return f"al_fashion/minst_model.keras.v{version_no}"


if __name__ == "__main__":
    from sim import do_simulation

    sample, labels = do_simulation([0], 256)
    do_train(sample, labels, 0)
