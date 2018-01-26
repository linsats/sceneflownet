import sys
import os
import numpy as np
from math import cos,sin
import warnings
from scipy import spatial
import scipy.ndimage
from utils import *
from local_variables import *
sys.path.append(os.path.join(pygeometry_dir,'obj_codes'))
from objfile import OBJ
from scipy import spatial


def quaternion_matrix(quaternion):
    """Return homogeneous rotation matrix from quaternion.
    >>> M = quaternion_matrix([0.99810947, 0.06146124, 0, 0])
    >>> numpy.allclose(M, rotation_matrix(0.123, [1, 0, 0]))
    True
    >>> M = quaternion_matrix([1, 0, 0, 0])
    >>> numpy.allclose(M, numpy.identity(4))
    True
    >>> M = quaternion_matrix([0, 1, 0, 0])
    >>> numpy.allclose(M, numpy.diag([1, -1, -1, 1]))
    True
    """
    _EPS = np.finfo(float).eps * 4.0
    q = np.array(quaternion, dtype=np.float64, copy=True)
    n = np.dot(q, q)
    if n < _EPS:
        return np.identity(4)
    q *= math.sqrt(2.0 / n)
    q = np.outer(q, q)
    return np.array([
        [1.0-q[2, 2]-q[3, 3],     q[1, 2]-q[3, 0],     q[1, 3]+q[2, 0], 0.0],
        [    q[1, 2]+q[3, 0], 1.0-q[1, 1]-q[3, 3],     q[2, 3]-q[1, 0], 0.0],
        [    q[1, 3]-q[2, 0],     q[2, 3]+q[1, 0], 1.0-q[1, 1]-q[2, 2], 0.0],
        [                0.0,                 0.0,                 0.0, 1.0]])

  
def read_pgm_xyz(filename):
    """Return image data from a PGM file generated by blensor. """
    fx = 472.92840576171875
    fy = fx 
    with open(filename, 'rb') as f:
        f.readline()
        f.readline()
        width_height = f.readline().strip().split()
        if len(width_height) > 1:
          width, height = map(int,width_height)
          value_max_range = float(f.readline())
          image_ = [float(line.strip()) for line in f.readlines()]
          if len(image_) == height * width:
            nx,ny = (width,height)
            x_index = np.linspace(0,width-1,width)
            y_index = np.linspace(0,height-1,height)
            xx,yy = np.meshgrid(x_index,y_index)
            xx -= float(width)/2
            yy -= float(height)/2
            xx /= fx
            yy /= fy

            cam_z = np.reshape(image_,(height, width))
            cam_z = cam_z / value_max_range * 1.5
            cam_x = xx * cam_z 
            cam_y = yy * cam_z
            image_z = np.flipud(cam_z)
            image_y = np.flipud(cam_y)
            image_x = np.flipud(cam_x)

            zoom_scale = 0.5
            image_x = scipy.ndimage.zoom(image_x, zoom_scale, order=1)
            image_y = scipy.ndimage.zoom(image_y, zoom_scale, order=1)
            image_z = scipy.ndimage.zoom(image_z, zoom_scale, order=1)
            image = np.dstack((image_x,image_y,image_z))

            return image
        
    return np.zeros((60,80,3))
  
np.set_printoptions(precision=4,suppress=True,linewidth=300)


def rot_tran(filepath):
  rot = np.zeros((3,3))
  tran = np.zeros((3,))
  lines = [line.strip() for line in open(filepath)]
  for idx,line in enumerate(lines):
    tmp = str(line).split('(')[1].split(')')[0].split()
    tmp= [float(x.split(',')[0]) for x in tmp]
    if idx < 3:
      rot[idx,:] = np.array(tmp[0:3])
      tran[idx] = tmp[3]
  return rot,tran
  

class Seg_Label:
  def __init__(self,graspmap_top_dir,obj_top_dir):
    self.graspmap_top_dir = graspmap_top_dir
    self.obj_top_dir = obj_top_dir
    frame_id = '20'
    self.model_ids =  [line for line in os.listdir(self.graspmap_top_dir) if line.endswith('.txt') and line.startswith('frame'+frame_id)]
    self.model_ids.sort()
 
  def label_frame(self,frame_id,n_sample=20000,ep=0.003):   
    self.graspmap_filepath = [line for line in os.listdir(self.graspmap_top_dir) if line.endswith('.pgm') and line.startswith('frame'+frame_id)][0]
    
    self.num_objs = len(self.model_ids)
    
    tmp = self.graspmap_filepath.split('.pgm')[0].split('_')

    azimuth_deg = float(tmp[2].split('azi')[1])
    elevation_deg = float(tmp[3].split('ele')[1])
    theta_deg = float(tmp[4].split('theta')[1])
    rho = float(tmp[1].split('rho')[1])
    
    self.azimuth_deg = azimuth_deg  
    cx, cy, cz = obj_centened_camera_pos(rho, azimuth_deg, elevation_deg)
    q1 = camPosToQuaternion(cx , cy , cz)
    q2 = camRotQuaternion(cx, cy , cz, theta_deg)
    q = quaternionProduct(q2, q1)
    R = quaternion_matrix(q)[0:3,0:3]
    
    self.grasp_xyz = read_pgm_xyz(os.path.join(graspmap_top_dir,self.graspmap_filepath))
    self.grasp_xyz_old = np.copy(self.grasp_xyz)
    self.height,self.width,self.depth = self.grasp_xyz.shape
    self.labeling = np.zeros((self.height,self.width,3))
    self.labeling_model_id = np.zeros((self.height,self.width,1))
    self.grasp_xyz = self.grasp_xyz.reshape((-1,3))
    self.labeling = self.labeling.reshape((-1,3))
    self.labeling_model_id = self.labeling_model_id.reshape((-1,1))
    self.grasp_xyz[:,2] *= -1.0
    self.grasp_xyz = R.dot(self.grasp_xyz.T).T + np.array([cx,cy,cz])
    
    #self.grasp_xyz = self.grasp_xyz.reshape((self.height,self.width,3))
    #self.graspmap_para_savepath_tmp = os.path.join(graspmap_top_dir,'frame'+frame_id+'_grasp.npz')
    #np.savez(self.graspmap_para_savepath_tmp,labeling=self.grasp_xyz)
    #print('savez')

    #self.grasp_xyz = self.grasp_xyz.reshape((-1,3)) 
    z_value = np.unique(self.grasp_xyz[:,2])
    #tmp_inn = np.array([self.grasp_xyz[:,0] != self.grasp_xyz[0,0],self.grasp_xyz[:,1] != self.grasp_xyz[0,1],self.grasp_xyz[:,2] != self.grasp_xyz[0,2]]).T
    #tmp_inn = np.any(tmp_inn,axis=1)
    #print(tmp_inn.shape)
    #print('test')
    tmp_inn = (np.linalg.norm(self.grasp_xyz - self.grasp_xyz[0],axis=1) > 0.0001)
    inddd = (self.grasp_xyz[:,2] > -0.2 + 0.001) * (np.linalg.norm(self.grasp_xyz - self.grasp_xyz[0],axis=1) > 0.001)
    foreground_inds = np.where(inddd)[0]
    
    print(len(foreground_inds))
    self.objs = []
    self.obj_trans = np.zeros((self.num_objs,3,))
    self.obj_rots = np.zeros((self.num_objs,3,3))
    self.num_samples = 60000
    self.obj_points = np.zeros((self.num_objs,self.num_samples,3))
    for idx,cate_models in enumerate(self.model_ids):
      cate, model = cate_models.split('_matrix')[0].split('_')[1:]
      rot, tran = rot_tran(os.path.join(graspmap_top_dir,'frame'+frame_id+'_'+cate+'_'+model+'_matrix_wolrd.txt'))
      tmp_path = os.path.join(self.obj_top_dir,cate,model,'model.obj')
      self.objs.append(OBJ(file_name=tmp_path,scale=1.0))
      if tran[2] > -0.2:
        self.obj_points[idx]=self.objs[idx].sample_points(self.num_samples,with_normal=False)[0]
        self.obj_points[idx] = (rot.dot(self.obj_points[idx].T)).T + tran
        tmp_kdtree = spatial.KDTree(self.obj_points[idx])
        dist_pred_in_gt = tmp_kdtree.query(self.grasp_xyz[foreground_inds])[0]
        obj_inds = np.where(dist_pred_in_gt < ep)[0]
        left_inds = np.where(dist_pred_in_gt >= ep)[0]
        self.labeling[foreground_inds[obj_inds]] = R.T.dot(tran - np.array([cx,cy,cz]))
        self.labeling_model_id[foreground_inds[obj_inds]] = idx + 1
        foreground_inds = foreground_inds[left_inds]
        print(len(foreground_inds))

    #self.labeling_model_id[foreground_inds] = 100
    print("finally ") 
    print(len(foreground_inds))   
    self.labeling = self.labeling.reshape((self.height,self.width,3))
    self.graspmap_para_savepath = os.path.join(graspmap_top_dir,'frame'+frame_id+'_labeling.npz')
    np.savez(self.graspmap_para_savepath,labeling=self.labeling)
     
    self.labeling_model_id = self.labeling_model_id.reshape((self.height,self.width,1))
    self.graspmap_model_id_para_savepath = os.path.join(graspmap_top_dir,'frame'+frame_id+'_labeling_model_id.npz')
    np.savez(self.graspmap_model_id_para_savepath,labeling=self.labeling_model_id)

graspmap_top_dir = sys.argv[-1]
test = Seg_Label(graspmap_top_dir=graspmap_top_dir, obj_top_dir='/home/linshaonju/interactive-segmentation/Data/ShapenetManifold')  
test.label_frame('20') 
test.label_frame('80')
