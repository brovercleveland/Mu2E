#! /usr/bin/env python

import pandas as pd
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit
from tools.fit_funcs import *
from lmfit import  Model
import cPickle as pkl
from matplotlib import gridspec

class FieldFitter:
  """Input hall probe measurements, perform semi-analytical fit, return fit function and other stuff."""
  def __init__(self, input_data):
    self.input_data = input_data
    #self.add_zero_data()

  def add_zero_data(self):
    df_highz = self.input_data[self.input_data.Z==self.input_data.Z.max()]
    df_highz.Z = 1000000
    df_highz.Bz = 0
    df_highz.Bx = 0
    df_highz.By = 0
    df_highz.Br = 0
    df_lowz = df_highz.copy()
    df_lowz.Z = -1000000
    self.zero_data = pd.concat([df_highz, self.input_data, df_lowz], ignore_index=True)
    self.zero_data.sort(['Z','X'],inplace=True)



  def fit_2d(self,A,B,C,use_pickle = False):
    self.mag_field = A
    self.axis2 = B
    self.axis1 = C

    piv = self.input_data.pivot(B,C,A)
    X=piv.columns.values
    Y=piv.index.values
    self.Z=piv.values
    self.Y,self.X = np.meshgrid(X, Y)

    if A == 'Bz':
      self.mod = Model(bz_2d, independent_vars=['r','z'])
    elif A == 'Br':
      self.mod = Model(br_2d, independent_vars=['r','z'])
    else:
      raise KeyError('No function available for '+A)

    if use_pickle:
      self.params = pkl.load(open('result.p',"rb"))
      #for param in self.params:
      #  self.params[param].vary = False
      self.result = self.mod.fit(self.Z.ravel(),r=self.X,z=self.Y, params = self.params,method='leastsq')
    else:
      self.params = Parameters()
      #self.params.add('R',value=1000,vary=False)
      self.params.add('R',value=22000,vary=False)
      if A == 'Br':
        self.params.add('C',value=0)
      self.params.add('A0',value=0)
      self.params.add('B0',value=0)
      #self.result = self.mod.fit(self.Z.ravel(),r=self.X,z=self.Y, params = self.params,method='leastsq')

      for i in range(20):
        print 'refitting with params:',i+1
        #self.params = self.result.params
        self.params.add('A'+str(i+1),value=0)
        self.params.add('B'+str(i+1),value=0)
        #self.result = self.mod.fit(self.Z.ravel(),r=self.X,z=self.Y, params = self.params,method='leastsq')

      #self.result = self.mod.fit(self.Z.ravel(),r=self.X,z=self.Y, params = self.params,method='leastsq')
      self.result = self.mod.fit(self.Z.ravel(),r=self.X,z=self.Y, params = self.params,method='leastsq')
      self.params = self.result.params

    report_fit(self.result)

  def fit_1d(self,A,B):

    if A == 'Bz':
      self.mod = Model(bz_2d)
    elif A == 'Br':
      self.mod = Model(br_2d, independent_vars=['r','z'])
    else:
      raise KeyError('No function available for '+A)


    data_1d = self.input_data.query('X==0 & Y==0')
    self.X=data_1d[B].values
    self.Z=data_1d[A].values
    self.mod = Model(bz_r0_1d)

    self.params = Parameters()
    self.params.add('R',value=100000,vary=False)
    self.params.add('A0',value=0)
    self.params.add('B0',value=0)

    self.result = self.mod.fit(self.Z,z=self.X, params = self.params,method='nelder')
    for i in range(9):
      print 'refitting with params:',i+1
      self.params = self.result.params
      self.params.add('A'+str(i+1),value=0)
      self.params.add('B'+str(i+1),value=0)
      self.result = self.mod.fit(self.Z,z=self.X, params = self.params,method='nelder')

    self.params = self.result.params
    report_fit(self.result)
    #report_fit(self.params)

  def plot_fit(self,ds='1d'):

    plt.close('all')
    plt.rc('font', family='serif')
    fig = plt.figure()
    #plt.hold(True)

    if ds == '1d':
      ax = fig.gca()
      ax.scatter(self.X, self.Z, color='black')
      ax.set_xlabel('Z')
      ax.set_ylabel('Bz')

      ax.plot(self.X, self.result.best_fit, color='green')
      #ax.plot(self.X, self.result.init_fit, color='black',linestyle='--')
    else:
      gs = gridspec.GridSpec(2, 2)
      ax1 = fig.add_subplot(gs[0:,0],projection='3d')
      scat = ax1.scatter(self.X.ravel(), self.Y.ravel(), self.Z.ravel(), color='black')

      ax1.set_xlabel(self.axis2)
      ax1.set_ylabel(self.axis1)
      ax1.set_zlabel(self.mag_field)

      surf = ax1.plot_wireframe(self.X, self.Y, self.result.best_fit.reshape(self.Z.shape),color='green')

      ax2 = fig.add_subplot(gs[0,1])
      heat = ax2.pcolor(self.X,self.Y,self.Z/self.result.best_fit.reshape(self.Z.shape),vmax=1.05,vmin=0.95)
      cb = plt.colorbar(heat, aspect=7)
      cb.set_label('Data/Fit')
      ax2.set_xlabel(self.axis2)
      ax2.set_ylabel(self.axis1)

      ax3 = fig.add_subplot(gs[1,1])
      heat = ax3.pcolor(self.X,self.Y,self.result.residual.reshape(self.Z.shape)*10000,vmin=-20,vmax=20)
      cb = plt.colorbar(heat, aspect=7)
      cb.set_label('Data-Fit (G)')
      ax3.set_xlabel(self.axis2)
      ax3.set_ylabel(self.axis1)

    ax1.view_init(elev=15., azim=-75)
    plt.show()
    plt.get_current_fig_manager().window.wm_geometry("-2600-600")
    #plt.get_current_fig_manager().window.wm_geometry("-1100-600")
    fig.set_size_inches(17,10,forward=True)
    plt.savefig('../plots/field_fits/'+ds+'_'+self.mag_field+'1a.png',transparent=True)
    ax1.view_init(elev=0., azim=-88)
    plt.draw()
    plt.savefig('../plots/field_fits/'+ds+'_'+self.mag_field+'2a.png',transparent=True)
    ax1.view_init(elev=11., azim=12)
    plt.draw()
    plt.savefig('../plots/field_fits/'+ds+'_'+self.mag_field+'3a.png',transparent=True)


    #plt.show()

  def pickle_results(self):
    pkl.dump( self.result.params, open( 'result.p', "wb" ),pkl.HIGHEST_PROTOCOL )

