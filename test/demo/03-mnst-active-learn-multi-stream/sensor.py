import asyncio
import datetime
import os
import sys
import time

import numpy as np
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.streaming import ZMQ_PS_Client, PubSubClient, connect_stream_client
from dtypes import *

from tensorflow.keras.datasets import mnist
from tensorflow.keras.datasets import fashion_mnist

from al.sim import plot_image
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt


import logging

logger = logging.getLogger(__name__)


class NumberCamera(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task(service=True)
        async def task():
            rng = np.random.default_rng(42)

            f = open("number.out", "w")
            f.write("SENSOR MEASUREMENTS ========================= \n")

            pclient = await connect_stream_client("06-multi-agent")

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
                    plt.savefig("number.png")
                    plt.close()
                    # request inference of image
                    f.write(f"[{datetime.datetime.now()}] Emit an image of {label} \n")
                    await pclient.publish(
                        NUMBER_CAMERA_DTYPE, {"label": label, "img": img}
                    )
                    f.flush()
                    await asyncio.sleep(2)

            f.close()

        self.task = task

    async def main_loop(self, runtime, in_data):
        await self.task()


class FashionCamera(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task(service=True)
        async def task():
            rng = np.random.default_rng(42)
            f = open("fashion.out", "w")
            f.write("SENSOR MEASUREMENTS ========================= \n")

            pclient = await connect_stream_client("03-mnst-active-learn-multi-stream")

            # Load the dataset
            _, (test_images, test_labels) = fashion_mnist.load_data()

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
                    plt.savefig("fashion.png")
                    plt.close()
                    # request inference of image
                    f.write(f"[{datetime.datetime.now()}] Emit an image of {label} \n")
                    await pclient.publish(
                        FASHION_CAMERA_DTYPE, {"label": label, "img": img}
                    )
                    f.flush()
                    await asyncio.sleep(2)

            f.close()

        self.task = task

    async def main_loop(self, runtime, in_data):
        await self.task()
