import asyncio
import datetime
import os
import sys
import time

import numpy as np
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.streaming import PubSubClient
from dtypes import *
from al.sim import plot_image
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from tensorflow.keras.datasets import mnist


import logging

logger = logging.getLogger(__name__)


class Camera(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()

        f = open("sensor.out", "w")
        f.write("SENSOR MEASUREMENTS ========================= \n")

        # Load the dataset
        _, (test_images, test_labels) = mnist.load_data()

        # Normalize the images to values between 0 and 1
        test_images = test_images / 255.0

        # Convert labels to one-hot encoded format

        target_labels = []
        for num in range(10):
            # start slowly....
            target_labels.append(num)
            mask = np.isin(test_labels, target_labels)
            target = test_images[mask]
            indices = np.random.choice(len(target), size=5)
            for i in range(4):
                img = target[indices][i]
                label = test_labels[mask][indices][i]
                plt.figure()
                plot_image(None, label, img)
                plt.savefig("sensor.png")
                plt.close()
                # request inference of image
                f.write(f"[{datetime.datetime.now()}] Emit an image of {label} \n")
                await ps.publish(CAMERA_DTYPE, {"label": label, "img": img})
                f.flush()
                await asyncio.sleep(2)

        f.close()
