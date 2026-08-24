import asyncio
import datetime
import os
import sys

import numpy as np
from radical.asyncflow import WorkflowEngine
from rose import Learner

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf
from digitaltwin.components import ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI
from al.sim import do_simulation
from al.train import do_train
from al.active import do_active

from al_fashion.sim import do_simulation as f_do_simulation
from al_fashion.train import do_train as f_do_train
from al_fashion.active import do_active as f_do_active

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)
tf.get_logger().setLevel("ERROR")


class HandwritingInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # Learners
        self.acl = Learner(self.flow)

        self.to_update = asyncio.Event()

        f = open("model-inference.out", "w")
        f.write("Model Inference Task ========================= \n")
        f.close()

        f = open("model-learner.out", "w")
        f.write("Model Learner ========================= \n")
        f.close()

        self.trained_labels = [0]

        # Learning tasks..............

        @self.acl.simulation_task(as_executable=False)
        async def simulation(*args):
            return do_simulation(*args)

        @self.acl.training_task(as_executable=False)
        async def training(*args):
            return do_train(*args)

        @self.acl.active_learn_task(as_executable=False)
        async def active_learn(*args):
            return do_active(*args)

        async def pipeline(target_labels, version_start):
            # do sim
            rng = np.random.default_rng(42)
            version = version_start
            while True:
                sample, labels = await simulation(target_labels, 256)
                model_str = training(sample, labels, version)
                active_result = await active_learn(
                    target_labels, 32, version, model_str
                )
                if active_result:
                    break
                version += 1

            return version

        self.pipeline = pipeline

        # inference task

        @self.flow.function_task
        async def do_inference(in_data: TypedData, v_no=0):
            img = np.expand_dims(in_data.data["img"], axis=0)
            model = tf.keras.models.load_model(f"al/mnist_model.v{v_no}.keras")
            prediction = model.predict(img)
            p_label = np.argmax(prediction, axis=1)

            f = open("model-inference.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Received: {in_data.data['label']}. Classify as: {p_label[0]}. Model version: {v_no}.\n"
            )
            f.close()
            return TypedData(DIGIT_DTYPE, p_label)

        self.inference_task = do_inference

    # Callbacks .................

    async def sensor_callback(self, in_data):
        f = open("model-learner.out", "a")
        f.write(
            f"[{datetime.datetime.now()}] Learner received image: {in_data.data['label']} \n"
        )
        f.close()

        if in_data.data["label"] not in self.trained_labels:
            self.trained_labels.append(in_data.data["label"])
            self.to_update.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.sensor_callback)
        runtime.set_inference_task(self.inference_task)

        # lets train on 0
        self.trained_labels = []
        v_no = 0
        while True:
            await self.to_update.wait()
            # I got a new label! train a model
            v_no = await self.pipeline(self.trained_labels, v_no)
            f = open("model-learner.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Learner published new model: {v_no} \n"
            )
            f.close()
            runtime.publish_new_model({"v_no": v_no})
            v_no += 1
            self.to_update.clear()


class FashionInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # Learners
        self.acl = Learner(self.flow)

        self.to_update = asyncio.Event()

        f = open("fashion-inference.out", "w")
        f.write("Model Inference Task ========================= \n")
        f.close()

        f = open("fashion-learner.out", "w")
        f.write("Model Learner ========================= \n")
        f.close()

        self.trained_labels = []

        # Learning tasks..............

        @self.acl.simulation_task(as_executable=False)
        async def simulation(*args):
            return f_do_simulation(*args)

        @self.acl.training_task(as_executable=False)
        async def training(*args):
            return f_do_train(*args)

        @self.acl.active_learn_task(as_executable=False)
        async def active_learn(*args):
            return f_do_active(*args)

        async def pipeline(target_labels, version_start):
            # do sim
            rng = np.random.default_rng(42)
            version = version_start
            while True:
                sample, labels = await simulation(target_labels, 256)
                model_str = training(sample, labels, version)
                active_result = await active_learn(
                    target_labels, 32, version, model_str
                )
                if active_result:
                    break
                version += 1

            return version

        self.pipeline = pipeline

        # inference task

        @self.flow.function_task
        async def do_inference(in_data: TypedData, v_no=0):
            img = np.expand_dims(in_data.data["img"], axis=0)
            model = tf.keras.models.load_model(f"al_fashion/mnist_model.v{v_no}.keras")
            prediction = model.predict(img)
            p_label = np.argmax(prediction, axis=1)

            f = open("fashion-inference.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Received: {in_data.data['label']}. Classify as: {p_label[0]}. Model version: {v_no}.\n"
            )
            f.close()
            return TypedData(FASHION_DTYPE, p_label)

        self.inference_task = do_inference

    # Callbacks .................

    async def sensor_callback(self, in_data):
        f = open("fashion-learner.out", "a")
        f.write(
            f"[{datetime.datetime.now()}] Learner received image: {in_data.data['label']} \n"
        )
        f.close()

        if in_data.data["label"] not in self.trained_labels:
            self.trained_labels.append(in_data.data["label"])
            self.to_update.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.sensor_callback)
        runtime.set_inference_task(self.inference_task)

        # lets train on 0
        self.trained_labels = []
        v_no = 0
        while True:
            await self.to_update.wait()
            # I got a new label! train a model
            v_no = await self.pipeline(self.trained_labels, v_no)
            f = open("fashion-learner.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Learner published new model: {v_no} \n"
            )
            f.close()
            runtime.publish_new_model({"v_no": v_no})
            v_no += 1
            self.to_update.clear()
