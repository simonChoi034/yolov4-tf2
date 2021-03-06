from typing import Tuple

import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Layer, Concatenate

from model.backbone.CSPDarknet53 import CSPDarknet53
from model.layer import MyConv2D, SpatialPyramidPooling, SpatialAttention, DownSampling, UpSampling


# *** small scale = stride 32 output; medium scale = stride 16 output; large scale = stride 8 output


class PANet(Layer):
    def __init__(self, name: str = "PANet", **kwargs):
        super(PANet, self).__init__(name=name, **kwargs)

        self.concat = Concatenate()

        self.block_1 = Sequential([
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="pa_net_block1_conv1"),
            MyConv2D(filters=1024, kernel_size=3, apply_dropblock=True, name="pa_net_block1_conv2"),
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="pa_net_block1_conv3")
        ])
        self.ssp = SpatialPyramidPooling()

        self.block_2 = Sequential([
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="pa_net_block2_conv1"),
            MyConv2D(filters=1024, kernel_size=3, apply_dropblock=True, name="pa_net_block2_conv2"),
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="pa_net_block2_conv3")
        ])

        self.up_sampling_1 = UpSampling(filters=256, apply_dropblock=True)
        self.medium_entry_conv = MyConv2D(filters=256, kernel_size=1, apply_dropblock=True)

        self.block_3 = Sequential([
            MyConv2D(filters=256, kernel_size=1, apply_dropblock=True, name="pa_net_block3_conv1"),
            MyConv2D(filters=512, kernel_size=3, apply_dropblock=True, name="pa_net_block3_conv2"),
            MyConv2D(filters=256, kernel_size=1, apply_dropblock=True, name="pa_net_block3_conv3"),
            MyConv2D(filters=512, kernel_size=3, apply_dropblock=True, name="pa_net_block3_conv4"),
            MyConv2D(filters=256, kernel_size=1, apply_dropblock=True, name="pa_net_block3_conv5")
        ])

        self.up_sampling_2 = UpSampling(filters=128, apply_dropblock=True)
        self.large_entry_conv = MyConv2D(filters=128, kernel_size=1, apply_dropblock=True)

        self.block_4 = Sequential([
            MyConv2D(filters=128, kernel_size=1, apply_dropblock=True, name="pa_net_block4_conv1"),
            MyConv2D(filters=256, kernel_size=3, apply_dropblock=True, name="pa_net_block4_conv2"),
            MyConv2D(filters=128, kernel_size=1, apply_dropblock=True, name="pa_net_block4_conv3"),
            MyConv2D(filters=256, kernel_size=3, apply_dropblock=True, name="pa_net_block4_conv4"),
            MyConv2D(filters=128, kernel_size=1, apply_dropblock=True, name="pa_net_block4_conv5")
        ])

        self.attentions = [SpatialAttention() for _ in range(3)]

    def call(self, inputs: tf.Tensor, training: bool = False, **kwargs) -> Tuple[tf.Tensor, tf.Tensor, tf.Tensor]:
        output_small, output_medium, output_large = inputs

        # small scale path
        output_small = self.block_1(output_small, training=training)
        output_small = self.ssp(output_small, training=training)
        output_small = self.block_2(output_small, training=training)

        # upsample concat
        shortcut_small = self.up_sampling_1(output_small, training=training)
        output_medium = self.medium_entry_conv(output_medium, training=training)
        output_medium = self.concat([output_medium, shortcut_small])

        # medium scale path
        output_medium = self.block_3(output_medium, training=training)

        # upsaple concat
        shortcut_medium = self.up_sampling_2(output_medium, training=training)
        output_large = self.large_entry_conv(output_large, training=training)
        output_large = self.concat([output_large, shortcut_medium])

        # large scale path
        output_large = self.block_4(output_large, training=training)

        # apply attention to each output
        output_small = self.attentions[0](output_small)
        output_medium = self.attentions[1](output_medium)
        output_large = self.attentions[2](output_large)

        return output_small, output_medium, output_large


class YOLOv4Head(Layer):
    def __init__(self, num_class: int, name="yolov4_head", **kwargs):
        super(YOLOv4Head, self).__init__(name=name, **kwargs)
        self.num_class = num_class

        #  [small, medium, large] output conv
        self.output_convs = [Sequential([
            MyConv2D(filters=filters, kernel_size=3),
            MyConv2D(
                filters=3 * (self.num_class + 5),
                kernel_size=1,
                activation="linear",
                apply_batchnorm=False,
                apply_dropblock=False,
                name="output_conv"
            )
        ]) for filters in [1024, 512, 256]]

        # concat conv 1
        self.down_sample_1 = DownSampling(filters=256, apply_dropblock=True)

        # block 1
        self.conv_block_1 = Sequential([
            MyConv2D(filters=256, kernel_size=1, apply_dropblock=True, name="head_block_1_conv1"),
            MyConv2D(filters=512, kernel_size=3, apply_dropblock=True, name="head_block_1_conv2"),
            MyConv2D(filters=256, kernel_size=1, apply_dropblock=True, name="head_block_1_conv3"),
            MyConv2D(filters=512, kernel_size=3, apply_dropblock=True, name="head_block_1_conv4"),
            MyConv2D(filters=256, kernel_size=1, apply_dropblock=True, name="head_block_1_conv5")
        ])

        # concat conv 2
        self.down_sample_2 = DownSampling(filters=512, apply_dropblock=True)

        # block 2
        self.conv_block_2 = Sequential([
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="head_block_2_conv1"),
            MyConv2D(filters=1024, kernel_size=3, apply_dropblock=True, name="head_block_2_conv2"),
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="head_block_2_conv3"),
            MyConv2D(filters=1024, kernel_size=3, apply_dropblock=True, name="head_block_2_conv4"),
            MyConv2D(filters=512, kernel_size=1, apply_dropblock=True, name="head_block_2_conv5")
        ])

        self.concat = Concatenate()

    def yolo_output(self, inputs: tf.Tensor, conv: Layer, training: bool = False) -> tf.Tensor:
        x = conv(inputs, training=training)
        x = tf.reshape(
            x,
            (-1, tf.shape(x)[1], tf.shape(x)[2], 3, self.num_class + 5)
        )
        return x

    def call(self, inputs: tf.Tensor, training: bool = False, **kwargs) -> Tuple[tf.Tensor, tf.Tensor, tf.Tensor]:
        output_small, output_medium, output_large = inputs

        shortcut_large = output_large

        # large_scale output
        output_large = self.yolo_output(output_large, conv=self.output_convs[2], training=training)

        # large to medium scale shortcut connection
        shortcut_large = self.down_sample_1(shortcut_large, training=training)
        output_medium = self.concat([shortcut_large, output_medium])

        # medium scale output
        output_medium = shortcut_medium = self.conv_block_1(output_medium, training=training)
        output_medium = self.yolo_output(output_medium, conv=self.output_convs[1], training=training)

        # medium to small scale shortcut connection
        shortcut_medium = self.down_sample_2(shortcut_medium, training=training)
        output_small = self.concat([shortcut_medium, output_small])

        # small scale output
        output_small = self.conv_block_2(output_small, training=training)
        output_small = self.yolo_output(output_small, conv=self.output_convs[0], training=training)

        return output_small, output_medium, output_large


class YOLOv4(tf.keras.Model):
    def __init__(self, num_class: int, name="YOLOv4", **kwargs):
        super(YOLOv4, self).__init__(name=name, **kwargs)
        self.backbone = CSPDarknet53()
        self.panet = PANet()
        self.head = YOLOv4Head(num_class=num_class)

    def call(self, inputs: tf.Tensor, training: bool = False, mask=None) -> Tuple[tf.Tensor, tf.Tensor, tf.Tensor]:
        x = self.backbone(inputs, training=training)
        x = self.panet(x, training=training)
        x = self.head(x, training=training)

        return x
