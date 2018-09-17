from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
import numpy as np
import os
import time
import sys


def loss(frame2_input_xyz, pred_quater, gt_quater, pred_transl, gt_transl,pred_mask, pred_traj, gt_traj, pred_score, gt_score, pred_r, gt_r, pred_flow, gt_flow, batch_size, dim=3, h=240, w=320): 
  obj_mask_origin = tf.greater(gt_traj[:,:,:,2],tf.zeros_like(gt_traj[:,:,:,2]))
  obj_mask_origin = tf.cast(obj_mask_origin,tf.float32)
  obj_mask_1  = tf.reshape(obj_mask_origin,[-1,h,w,1])
  obj_mask_6 = tf.tile(obj_mask_1,[1,1,1,6])

  loss_mask = tf.reduce_mean( tf.nn.sparse_softmax_cross_entropy_with_logits(labels=tf.cast(obj_mask_origin,dtype=tf.int32),logits=pred_mask))
  score_weight = obj_mask_origin + 0.001

  loss_score = tf.reduce_sum( (score_weight) * tf.nn.sparse_softmax_cross_entropy_with_logits(labels=tf.cast(gt_score,dtype=tf.int32), logits=pred_score)) / (tf.reduce_sum(score_weight) + 0.000001)

  loss_elem = tf.reduce_sum(tf.squared_difference(pred_traj,gt_traj)*obj_mask_6)/(tf.reduce_sum(obj_mask_1) + 0.000001)  

  loss_boundary = tf.reduce_sum(tf.squared_difference(gt_r, pred_r)*obj_mask_1)/(tf.reduce_sum(obj_mask_1) + 0.000001)
  loss_flow = tf.reduce_mean(tf.squared_difference(pred_flow,gt_flow))
  loss_transl = tf.reduce_mean(tf.squared_difference(pred_transl,gt_transl))
  loss_quater = tf.reduce_mean(tf.reduce_sum(-(pred_quater * gt_quater),3))
  loss_rigid_flow = 0.0  
  loss_variance = 0.0
  loss_violation = 0.0
  
  for b_i in xrange(batch_size):
    tmp = gt_traj[b_i,:,:,2]
    tmp = tf.reshape(tmp,(-1,))
    y, idx = tf.unique(tmp)
    idx = tf.reshape(idx,(h,w,1))

    ins_tmp = tf.ones_like(idx)
    ones = tf.ones_like(gt_traj[b_i,:,:,2])

    obj_mask = obj_mask_origin[b_i]

    def instance_variance_loss(z):
      idx_mask = tf.equal(gt_traj[b_i,:,:,2], ones * z)
      idx_mask = tf.logical_and(idx_mask,tf.cast(obj_mask,tf.bool))
      idx_mask = tf.reshape(idx_mask, [h,w,1])
      idx_mask = tf.cast(idx_mask, tf.float32)
      idx_mask_6d  = tf.tile(idx_mask, [1,1,6])
      tmp_prd = idx_mask_6d * pred_traj[b_i]
      tmp_prd = tf.reshape(tmp_prd,(-1,6))
      tmp_mean = tf.reduce_sum(tmp_prd,axis=0)/(tf.reduce_sum(idx_mask)+0.000001)
      tmp_mean = tf.reshape(tmp_mean,(1,1,6))
      tmp_mean_final = tf.tile(tmp_mean,[h,w,1])
      loss_variance_instance = tf.reduce_sum(idx_mask_6d * tf.squared_difference(tmp_mean_final,pred_traj[b_i])) / (tf.reduce_sum(idx_mask)+0.000001)
      return loss_variance_instance

    loss_variance += tf.reduce_mean(tf.map_fn(instance_variance_loss,y))  
    
    def instance_violation_loss(z):
      idx_mask = tf.equal(gt_traj[b_i,:,:,2],ones * z)
      idx_mask = tf.logical_and(idx_mask,tf.cast(obj_mask,tf.bool))
      idx_mask = tf.reshape(idx_mask,[h,w,1])
      idx_mask = tf.cast(idx_mask,tf.float32)
      idx_mask_6d  = tf.tile(idx_mask,[1,1,6])

      tmp_prd = idx_mask_6d * pred_traj[b_i,:,:,0:6]
      tmp_prd = tf.reshape(tmp_prd,(-1,6))

      tmp_r = idx_mask_6d[:,:,0:1] * pred_r[b_i]
      tmp_r_mean = tf.reduce_sum(tmp_r)/(tf.reduce_sum(idx_mask)+0.000001)
      r = tmp_r_mean * 0.5

      friend_mask = idx_mask_6d[:,:,0]
      l2_error = tf.reduce_sum(tf.squared_difference(pred_traj[b_i], gt_traj[b_i]),2)
      dist = tf.sqrt(l2_error)
      pull_mask =  tf.less(r * ones, dist)
      pull_mask = tf.cast(pull_mask,tf.float32)
      pos = tf.reduce_sum(friend_mask * pull_mask * l2_error)/(tf.reduce_sum(friend_mask * pull_mask) + 0.000001)
      return pos

    loss_violation += tf.reduce_mean(tf.map_fn(instance_violation_loss,y))

    def instance_sceneflow_loss(z):
      idx_mask = tf.equal(gt_traj[b_i,:,:,dim-1],ones * z)
      idx_mask = tf.logical_and(idx_mask,tf.cast(obj_mask,tf.bool))
      idx_mask = tf.reshape(idx_mask,[h,w,1])
      idx_mask = tf.cast(idx_mask,tf.float32)
      idx_mask_4d  = tf.tile(idx_mask,[1,1,4])
      idx_mask_3d  = tf.tile(idx_mask,[1,1,3])

      tmp_quater = idx_mask_4d * pred_quater[b_i,:,:,0:4]
      tmp_quater = tf.reshape(tmp_quater,(-1,4))
      tmp_quater = tf.reduce_sum(tmp_quater,axis=0)/(tf.reduce_sum(idx_mask)+0.000001)

      tmp_transl = idx_mask_3d * pred_transl[b_i,:,:,0:3]
      tmp_transl = tf.reshape(tmp_transl,(-1,3))
      tmp_transl = tf.reduce_sum(tmp_transl,axis=0)/(tf.reduce_sum(idx_mask)+0.000001)

      w1, x1, y1, z1 = tf.unstack(tmp_quater, axis=-1)
      x2, y2, z2  = tf.unstack(frame2_input_xyz[b_i], axis=-1)
      wm =         - x1 * x2 - y1 * y2 - z1 * z2
      xm = w1 * x2           + y1 * z2 - z1 * y2
      ym = w1 * y2           + z1 * x2 - x1 * z2
      zm = w1 * z2           + x1 * y2 - y1 * x2

      x = -wm * x1 + xm * w1 - ym * z1 + zm * y1
      y = -wm * y1 + ym * w1 - zm * x1 + xm * z1
      z = -wm * z1 + zm * w1 - xm * y1 + ym * x1

      tmp_flow = tf.stack((x,y,z),axis=-1)
      tmp_flow = tmp_flow + tmp_transl - frame2_input_xyz[b_i]
      tmp_loss = tf.reduce_sum(idx_mask_3d * tf.squared_difference(tmp_flow, gt_flow[b_i])) / (tf.reduce_sum(idx_mask)+0.000001) 
      return tmp_loss
    loss_rigid_flow += tf.reduce_mean(tf.map_fn(instance_sceneflow_loss,y)) 

  return loss_rigid_flow, loss_variance, loss_violation, loss_quater, loss_transl, loss_boundary, loss_flow, loss_elem, loss_mask, loss_score