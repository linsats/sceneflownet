from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
import numpy as np
import os
import time
import sys

#from ..cython.cpu_nms import cpu_nms
#from ..cython.gpu_nms import gpu_nms

#def py_nms_wrapper(thresh):
#  def _nms(dets):
#    return nms(dets,thresh)
#  return _nms

#def cpu_nms_wrapper(thresh):
#  def _nms(dets):
#    return cpu_nms(dets,thresh)
#  return _nms

#def gpu_nms_wrapper(thresh,device_id):
#  def _nms(dets):
#    return gpu_nms(dets,thresh,device_id)
#  return _nms

def nms(pred_c,pred_r,pred_s):
  """
  dets = [x,r,s]
  """
  c = np.reshape(pred_c,(-1,3)) 
  r = np.reshape(pred_r,(-1,))
  scores = np.reshape(pred_s,(-1,))

  index = np.where(scores > 0.0)[0]
    
  c = c[index]
  r = r[index]
  scores = scores[index] 
  
  order = scores.argsort()[::-1]
  keep = []
  while order.size > 0:
    i = order[0]
    tmp = c[order[1:],:] - c[i,:]
    inds = np.where(np.linalg.norm(c[order,:] - c[i,:],axis=1) > max(1.0 * r[i],0.000001))[0]
    diff = len(order) - len(inds)
    if diff > 10:
      keep.append(i)
    order = order[inds]
 
  index = np.array(keep).astype(np.int32)
  
  return c[index], r[index], scores[index]   

def infer_seg(c,r,s,pred_xyz,h=120,w=160):
  final_seg = np.zeros((h,w))
  count = 1
  instances_seg_pred = []
  instances_scores = [] 
  for ins_i in xrange(len(r)):
    map_id = np.linalg.norm(pred_xyz - c[ins_i], axis=2) < r[ins_i] * 1.5
    #left_id = final_seg > 0
    #map_id = np.logical_and(map_id,left_id)
    if np.sum(map_id) > 10:
      final_seg[map_id] = count 
      count += 1
      idx_mask = np.reshape(map_id,[120,160,1])
      idx_mask = idx_mask.astype(np.float32)      
      instances_seg_pred.append(idx_mask)
      instances_scores.append(s[ins_i])
  return final_seg, instances_seg_pred, instances_scores