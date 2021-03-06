from typing import Tuple

import numpy as np
import tensorflow as tf

from config import cfg


@tf.function
def decode(pred: tf.Tensor, anchors: np.ndarray) -> Tuple[tf.Tensor, tf.Tensor, tf.Tensor]:
    # pred: (batch_size, grid, grid, anchors, (x, y, w, h, obj, ...classes))
    grid_size = tf.shape(pred)[1]
    box_xy, box_wh, objectness, class_probs = tf.split(pred, (2, 2, 1, -1), axis=-1)

    box_xy = cfg.grid_sensitivity_ratio * tf.sigmoid(box_xy)
    objectness = tf.sigmoid(objectness)
    class_probs = tf.sigmoid(class_probs)

    grid = tf.meshgrid(tf.range(grid_size), tf.range(grid_size))
    grid = tf.expand_dims(tf.stack(grid, axis=-1), axis=2)

    box_xy = (box_xy + tf.cast(grid, tf.float32)) / tf.cast(grid_size, tf.float32)
    box_wh = tf.exp(box_wh) * anchors

    box_x1y1 = box_xy - box_wh / 2
    box_x2y2 = box_xy + box_wh / 2
    bbox = tf.concat([box_x1y1, box_x2y2], axis=-1)

    return bbox, objectness, class_probs


@tf.function
def flatten_output(outputs: Tuple[tf.Tensor, tf.Tensor, tf.Tensor]) -> Tuple[tf.Tensor, tf.Tensor, tf.Tensor]:
    bbox, objectness, class_probs = outputs
    bbox = tf.reshape(bbox, (tf.shape(bbox)[0], -1, tf.shape(bbox)[-1]))
    objectness = tf.reshape(objectness, (tf.shape(objectness)[0], -1, tf.shape(objectness)[-1]))
    class_probs = tf.reshape(class_probs, (tf.shape(class_probs)[0], -1, tf.shape(class_probs)[-1]))

    return bbox, objectness, class_probs


@tf.function
def non_max_suppression(
        inputs: Tuple[tf.Tensor, tf.Tensor, tf.Tensor],
        iou_threshold: float = cfg.yolo_iou_threshold,
        score_threshold: float = cfg.yolo_score_threshold,
        max_bbox_size: int = cfg.max_bbox_size
) -> Tuple[tf.Tensor, tf.Tensor, tf.Tensor, tf.Tensor]:
    anchors = cfg.anchors.get_anchors()
    anchor_masks = cfg.anchors.get_anchor_masks()

    output_small, output_medium, output_large = inputs
    output_small = decode(output_small, anchors[anchor_masks[0]])
    output_medium = decode(output_medium, anchors[anchor_masks[1]])
    output_large = decode(output_large, anchors[anchor_masks[2]])

    # flatten output to shape [batch_size, toto_grid_size, *]
    bbox_small, objectness_small, class_probs_small = flatten_output(output_small)
    bbox_medium, objectness_medium, class_probs_medium = flatten_output(output_medium)
    bbox_large, objectness_large, class_probs_large = flatten_output(output_large)

    # concat all output
    bbox = tf.concat([bbox_small, bbox_medium, bbox_large], axis=1)
    confidence = tf.concat([objectness_small, objectness_medium, objectness_large], axis=1)
    class_probs = tf.concat([class_probs_small, class_probs_medium, class_probs_large], axis=1)

    scores = confidence * class_probs

    bboxes, scores, classes, valid_detections = tf.image.combined_non_max_suppression(
        boxes=tf.reshape(bbox, (tf.shape(bbox)[0], -1, 1, 4)),
        scores=tf.reshape(scores, (tf.shape(scores)[0], -1, tf.shape(scores)[-1])),
        max_output_size_per_class=max_bbox_size,
        max_total_size=max_bbox_size,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold
    )

    return bboxes, scores, classes, valid_detections
