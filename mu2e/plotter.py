#! /usr/bin/env python

from __future__ import division
from __future__ import absolute_import
from __future__ import print_function
import os
import shutil
import math
import mu2e
import numpy as np
import pandas as pd
from datafileprod import DataFileMaker
from . import src.RowTransformations as rt
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib import gridspec
from matplotlib.ticker import LinearLocator, FormatStrFormatter
from scipy import interpolate
from scipy.optimize import curve_fit
from statsmodels.formula.api import wls
from statsmodels.graphics.regressionplots import abline_plot
from collections import OrderedDict
import matplotlib.ticker as mtick
import re
import IPython.display as IPdisplay
import glob
from PIL import Image as PIL_Image
from images2gif import writeGif
from sys import platform
from six.moves import filter
from six.moves import range
from six.moves import zip
if platform == 'darwin':
    import AppKit
from plotly.offline import init_notebook_mode, iplot, plot
import plotly.graph_objs as go
from .tools.new_iplot import new_iplot
import plotly.plotly as py
from mpldatacursor import datacursor
import warnings
warnings.simplefilter('always', DeprecationWarning)
del Axes3D



class Plotter:
    """Class that takes prepped dataframes and produces all kinds of neat plots and things"""

    def __init__(self, data_frame_dict,main_suffix=None,alt_save_dir=None,extra_suffix = None, clear=True, fit_result=None, no_show=False, use_html_dir = False):
        """Default constructor, takes a dict of pandas DataFrame.
        (optional suffix and save dir)"""
        warnings.warn(("The `Plotter` class is deprecated, please switch to "
                "plotting functions via mu2eplots.py. API will be severely broken."), DeprecationWarning)
        if clear: plt.close('all')

        self.markers = ['o','v','^','s']
        self.lines= ['-','--',':','-.']
        self.colors = {'DS_Mau':'blue','DS_GA01':'darksalmon','DS_GA02':'green','DS_GA03':'maroon'}

        if type(data_frame_dict) != dict: raise TypeError('data_frame_dict must be dict')
        if len(data_frame_dict)==0: raise Exception('data_frame_dict must have at least one entry')

        if main_suffix and main_suffix not in list(data_frame_dict.keys()):
            raise KeyError('main_suffix: '+main_suffix+'not in keys: '+list(data_frame_dict.keys()))

        if not main_suffix and len(data_frame_dict)>1:
            raise Exception('must specify main_suffix if len(dict)>1')

        if not alt_save_dir:
            save_dir = os.path.abspath(os.path.dirname(mu2e.__file__))+'/../plots'
        else:
            save_dir = alt_save_dir
        self.html_dir = '/Users/brianpollack/Documents/PersonalWebPage/mu2e_plots'

        try: self.plot_count = plt.get_fignums()[-1]
        except: self.plot_count = 0

        if len(data_frame_dict)==1:
            self.data_frame_dict = OrderedDict(data_frame_dict)
            self.suffix = list(self.data_frame_dict.keys())[0]
        else:
            self.suffix = main_suffix
            keys = sorted([key for key in data_frame_dict.keys() if key not in main_suffix])
            keys.insert(0,main_suffix)
            self.data_frame_dict = OrderedDict()
            for key in keys:
                self.data_frame_dict[key] = data_frame_dict[key]
            self.suffix_extra = '-'.join(list(self.data_frame_dict.keys()))
            self.init_save_dir(save_dir,extra=True)

        self.init_save_dir(save_dir)
        if fit_result: self.fit_result = fit_result

        self.extra_suffix = extra_suffix

        self.MultiScreen = False
        if platform=='darwin' and len(AppKit.NSScreen.screens())==1:
            self.MultiScreen = False
        self.no_show= no_show
        self.use_html_dir = use_html_dir

    def set_df(self,df):
        self.data_frame_dict[list(self.data_frame_dict.keys())[0]] = df

    def get_df(self):
        return self.data_frame_dict[list(self.data_frame_dict.keys())[0]]



    @classmethod
    def from_hall_study(cls, data_frame_dict, fit_result, use_html_dir = False):
        "Initialize plotter from a hall probe study"
        alt_save_dir =    os.path.abspath(os.path.dirname(mu2e.__file__))+'/../plots/field_fits'
        return cls(data_frame_dict,fit_result = fit_result, alt_save_dir = alt_save_dir, use_html_dir = use_html_dir)

    def plot_wrapper(func):
        def inner(self,*args,**kwargs):
            self.plot_count+=1
            print('Plot {0} is: {1}'.format(self.plot_count,args))
            return func(self,*args,**kwargs)
        return inner

    def init_save_dir(self,save_dir,extra=False):
        if extra:
            self.save_dir_extra = save_dir+'/'+self.suffix_extra
            self.html_dir_extra = self.html_dir+'/'+self.suffix_extra

            if not os.path.exists(self.save_dir_extra):
                        os.makedirs(self.save_dir_extra)
            if not os.path.exists(self.html_dir_extra):
                        os.makedirs(self.html_dir_extra)
        else:
            if self.suffix!='':
                self.save_dir=save_dir+'/'+self.suffix
                self.html_dir=self.html_dir+'/'+self.suffix

            if not os.path.exists(self.save_dir):
                        os.makedirs(self.save_dir)
            if not os.path.exists(self.html_dir):
                        os.makedirs(self.html_dir)

    def polar_to_cart(self,r,theta):
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        return(x, y)

    def make_r(self,row):
        return np.sqrt(row['X']**2+row['Y']**2)
    def center_x(self,row,offset = None):
        if offset == None: offset = 3904
        return row['X']-offset
    def make_br(self,row):
        return np.sqrt(row['Bx']**2+row['By']**2)
    def make_theta(self,row):
        return np.arctan2(row['Y'],row['X'])
    def make_bottom_half(self,row):
        return (-row['Y'])

    def make_interp_grid(self, r=None, data_frame_orig = None, AB = None, val_name = None, interp_num=200):
        """Make a grid for interpolation, either for R vs Theta or A vs B, where
        A and B are some combination of X,Y,Z.    If A and B are used, they must be a pair of triples of the form:
        [['A',start_A,stop_A],['B',start_B,stop_B]].    dicts are not used as I want to preserve order."""

        if r==None and AB==None: raise Exception('No grid parameters specified')
        elif r!=None and AB!=None: raise Exception('Grid parameters over-specified')
        elif AB!=None and type(AB)!=dict and len(AB)!=2: raise Exception('AB is specified incorrectly')

        if r!=None:
            theta_array = np.linspace(-np.pi,np.pi,num=interp_num)
            r_array = np.full(interp_num,r)
            x_array = np.ones(interp_num)
            y_array = np.ones(interp_num)
            val_array = np.full(interp_num,np.nan)
            for i in np.arange(interp_num):
                x_array[i],y_array[i] = self.polar_to_cart(r_array[i],theta_array[i])
            data_frame_interp_grid = pd.DataFrame({'X':x_array,'Y':y_array,val_name:val_array})
            #data_frame_interp = pd.DataFrame({'X':x_array,'Y':y_array,val_name:val_array})
            #data_frame_interp_grid = pd.concat([data_frame_interp,data_frame_orig])
            #data_frame_interp_grid = data_frame_interp_grid[abs(data_frame_interp_grid.X)<(r+50)]
            #data_frame_interp_grid = data_frame_interp_grid[abs(data_frame_interp_grid.Y)<(r+50)]
            data_frame_interp_grid.sort(['X','Y'],inplace=True)
        else:
            a_array = np.linspace(AB[0][1],AB[0][2],interp_num)
            b_array = np.linspace(AB[1][1],AB[1][2],interp_num)
            val_array = np.full(interp_num,np.nan)
            data_frame_interp_grid = pd.DataFrame({AB[0][0]:a_array,AB[1][0]:b_array,val_name:val_array})
            data_frame_interp_grid.sort([AB[0][0],AB[1][0]],inplace=True)
        return data_frame_interp_grid



    def interpolate_data(self, old_frame, new_frame, field, x_ax='X', y_ax='Y', method='cubic'):
        """Interpolate B-field values given a new A-B grid.
        Currently only interpolates for a given field component, then recalculates R, Theta"""
        old_piv = old_frame.pivot(x_ax,y_ax,field)
        old_x = old_piv.index.values
        old_y = old_piv.columns.values
        old_vals = old_piv.values
        new_piv = new_frame.pivot(x_ax,y_ax,field)
        new_x = new_piv.index.values
        new_y = new_piv.columns.values
        new_xx,new_yy = np.meshgrid(new_x,new_y)

        print('interpolating', field)
        interp_function = interpolate.interp2d(old_x,old_y,old_vals.T,kind=method)
        new_vals = interp_function(new_x,new_y)
        data_interp = np.array([new_xx, new_yy, new_vals]).reshape(3, -1).T
        interp_frame = pd.DataFrame(data_interp, columns=[x_ax,y_ax,field])

        C = [c for c in ['X','Y','Z'] if c not in [x_ax,y_ax]][0]
        print('making new',C)
        #interp_frame[C] = old_frame[C].unique()[0]
        interp_frame.eval('{0}={1}'.format(C,old_frame[C].unique()[0]))
        print('making new Theta')
        #interp_frame['Theta'] = interp_frame.apply(self.make_theta,axis=1)
        interp_frame['Phi'] = rt.apply_make_theta(interp_frame['X'].values, interp_frame['Y'].values)
        print('making new R')
        #interp_frame['R'] = interp_frame.apply(self.make_r,axis=1)
        interp_frame['R'] = rt.apply_make_r(interp_frame['X'].values, interp_frame['Y'].values)
        interp_frame = interp_frame[['X','Y','Z','R','Phi',field]]
        print('interp made')
        return interp_frame


    @plot_wrapper
    def plot_A_v_B(self,A,B,*conditions):
        """Plot A vs B given some set of comma seperated boolean conditions"""
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        print(data_frame.head())

        fig = plt.figure(self.plot_count)
        data_frame.eval('{0}err = 0.0001*{0}'.format(A))
        #plt.plot(data_frame[B],data_frame[A],'ro')
        plt.errorbar(data_frame[B],data_frame[A],yerr=data_frame[A+'err'],fmt='ro')
        plt.xlabel(B)
        plt.ylabel(A)
        plt.title('{0} vs {1} at {2}'.format(A,B,conditions))
        #plt.axis([-0.1, 3.24,0.22,0.26])
        plt.grid(True)
        plt.savefig(self.save_dir+'/{0}_v_{1}_at_{2}_{3}.png'.format(A,B,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix))
        return data_frame, fig

    @plot_wrapper
    def plot_A_v_B_ratio(self,A,B,*conditions):
        """Plot A vs B given some set of comma seperated boolean conditions, use multiple dataframes"""
        fig = plt.figure(self.plot_count)
        gs = gridspec.GridSpec(2,1,height_ratios=[3,1])
        ax1=fig.add_subplot(gs[0])
        ax2=fig.add_subplot(gs[1],sharex=ax1)
        plt.setp(ax1.get_xticklabels(), visible=False)
        fig.subplots_adjust(hspace=0)


        data_frame_dict = OrderedDict()
        for key in self.data_frame_dict:
            data_frame_dict[key] = self.data_frame_dict[key].query(' and '.join(conditions))

        for i,key in enumerate(data_frame_dict):
            #ax1.errorbar(data_frame_dict[key][B],data_frame_dict[key][A],yerr=data_frame_dict[key][A+'err'], linestyle='None',marker=self.markers[i], color = self.colors[i], markersize=7,label=key)
            ax1.plot(data_frame_dict[key][B],data_frame_dict[key][A], linestyle=self.lines[i],marker='None', color = self.colors[key], linewidth=2,label=key)
            if i>0:
                #ax2.plot(data_frame_dict[key][B],data_frame_dict.values()[0][A]/data_frame_dict[key][A],linestyle='None',marker=self.markers[i], color= self.colors[i], markersize = 7,label=key)
                ax2.plot(data_frame_dict[key][B],list(data_frame_dict.values())[0][A]/data_frame_dict[key][A],linestyle=self.lines[i],marker='None', color= self.colors[key], linewidth=2,label=key)

        ax2.set_xlabel(B)
        ax1.set_ylabel(A)
        labels = list(data_frame_dict.keys())
        labels = [re.sub('_','\_',i) for i in labels]

        if len(data_frame_dict)==2:
            ax2.set_ylabel(r'$\frac{\mathrm{'+labels[0]+r'}}{\mathrm{'+labels[1]+r'}}$')
        ax1.set_title('{0} vs {1} at {2}'.format(A,B,conditions))
        ax1.grid(True)
        ax2.grid(True)
        ylims = ax2.get_ylim()
        if ylims[0]>1: ylims[0] = 0.995
        if ylims[1]<1: ylims[1] = 1.005
        print(ylims)
        ax2.set_ylim(ylims[0],ylims[1])
        ax2.get_yaxis().get_major_formatter().set_useOffset(False)
        ax2.axhline(1,linewidth=2,color='r')
        ax1.legend(loc='best')
        plt.setp(ax2.get_yticklabels()[-1:], visible=False)
        fig.savefig(self.save_dir_extra+'/{0}_v_{1}_at_{2}_{3}.png'.format(A,B,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix_extra))
        #return data_frame_dict, fig
        return ax2

    @plot_wrapper
    def plot_A_v_B_and_fit(self,A,B,*conditions):
        """Plot A vs B given some set of comma seperated boolean conditions"""
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        print(data_frame.head())

        fig = plt.figure(self.plot_count)
        data_frame.eval('{0}err = 0.0001*{0}'.format(A))
        #plt.plot(data_frame[B],data_frame[A],'ro')
        plt.errorbar(data_frame[B],data_frame[A],yerr=data_frame[A+'err'],fmt='ro')
        plt.xlabel(B)
        plt.ylabel(A)
        plt.title('{0} vs {1} at {2}'.format(A,B,conditions))
        #plt.axis([-0.1, 3.24,0.22,0.26])
        plt.grid(True)
        lm = self.fit_linear_regression(data_frame,A,B,fig)
        plt.savefig(self.save_dir+'/{0}_v_{1}_at_{2}_{3}_fit.png'.format(A,B,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix))
        return data_frame, fig, lm

    @plot_wrapper
    def plot_A_v_B_and_C(self,A='Bz',B='X',C='Z',interp=False,interp_num=300, *conditions,**kwargs):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent. A bit complicated right now to get
        proper setup for contour plotting."""
        if 'data_frame' in kwargs:
            data_frame = kwargs['data_frame']
        else:
            data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        print(data_frame.head())

        if interp:
            data_frame_interp_grid = self.make_interp_grid(AB=[[B,data_frame[B].min(),data_frame[B].max()],[C,data_frame[C].min(),data_frame[C].max()]],
                    data_frame_orig=data_frame,val_name=A,interp_num=interp_num)
            data_frame = self.interpolate_data(data_frame, data_frame_interp_grid, field = A, x_ax = B, y_ax =C, method='cubic')

        data_frame = data_frame.reindex(columns=[A,B,C])
        piv = data_frame.pivot(B,C,A)
        X=piv.columns.values
        Y=piv.index.values
        Z=piv.values
        Xi,Yi = np.meshgrid(X, Y)

        fig = plt.figure(self.plot_count).gca(projection='3d')
        if self.no_show:
            return fig,data_frame
        else:
            fig.plot_surface(Xi, Yi, Z, rstride=1, cstride=1, cmap=plt.get_cmap('viridis'),
                                    linewidth=0, antialiased=False)
            fig.zaxis.set_major_locator(LinearLocator(10))
            fig.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))
            if 'PS' in self.suffix:
                fig.view_init(elev=20., azim=45)
            else:
                fig.view_init(elev=20., azim=-117)

            #cb = plt.colorbar(surf, shrink=0.5, aspect=5)
            #cb.set_label(A)

            plt.xlabel(C)
            plt.ylabel(B)
            fig.set_zlabel(A)
            #return fig
            #plt.ticklabel_format(style='sci', axis='z', scilimits=(0,0))
            fig.zaxis.set_major_formatter(mtick.FormatStrFormatter('%.1e'))
            fig.zaxis.labelpad=20
            fig.zaxis.set_tick_params(direction='out',pad=10)
            #fig.zaxis._axinfo['label']['space_factor'] = 2.2
            plt.title('{0} vs {1} and {2}, {3}'.format(A,B,C,conditions[0]))
            #plt.axis([-0.1, 3.24,0.22,0.26])
            #plt.grid(True)
            if interp:
                plt.savefig(self.save_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_interp_{4}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix),bbox_inches='tight')
            else:
                plt.savefig(self.save_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_{4}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix),bbox_inches='tight')

            self.plot_count+=1
            fig = plt.figure(self.plot_count)
            heat = plt.pcolormesh(Xi,Yi,Z, cmap=plt.get_cmap('viridis'))

            cb = plt.colorbar(heat, shrink=0.5, aspect=5)
            cb.set_label(A)

            plt.xlabel(C)
            plt.ylabel(B)
            plt.title('{0} vs {1} and {2}, {3}'.format(A,B,C,conditions[0]))
            plt.grid(True)
            if interp:
                plt.savefig(self.save_dir+'/{0}_v_{1}_and_{2}_at_{3}_heat_interp_{4}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix),bbox_inches='tight')
            else:
                plt.savefig(self.save_dir+'/{0}_v_{1}_and_{2}_at_{3}_heat_{4}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix),bbox_inches='tight')

            return fig,data_frame

    @plot_wrapper
    def plot_A_v_B_and_C_plotly(self,A='Bz',B='X',C='Z',interp=False,interp_num=300, *conditions,**kwargs):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent. A bit complicated right now to get
        proper setup for contour plotting."""
        #init_notebook_mode()
        layout = go.Layout(
                        title='Plot of {0} vs {1} and {2} for DS, {3}'.format(A,B,C,conditions[0]),
                        autosize=False,
                        width=675,
                        height=650,
                        scene=dict(
                                xaxis=dict(
                                        title='{} (mm)'.format(C),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                yaxis=dict(
                                        title='{} (mm)'.format(B),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                zaxis=dict(
                                        title='{} (T)'.format(A),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                cameraposition=[[-0.1, 0.5, -0.7, -0.2], [0.0, 0, 0.0], 2.8]
                                ),
                        showlegend=True,
                        )

        if 'data_frame' in kwargs:
            data_frame = kwargs['data_frame']
        else:
            data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))

        if interp:
            data_frame_interp_grid = self.make_interp_grid(AB=[[B,data_frame[B].min(),data_frame[B].max()],[C,data_frame[C].min(),data_frame[C].max()]],
                    data_frame_orig=data_frame,val_name=A,interp_num=interp_num)
            data_frame = self.interpolate_data(data_frame, data_frame_interp_grid, field = A, x_ax = B, y_ax =C, method='cubic')

        data_frame = data_frame.reindex(columns=[A,B,C])
        piv = data_frame.pivot(B,C,A)
        X=piv.columns.values
        Y=piv.index.values
        Z=piv.values
        Xi,Yi = np.meshgrid(X, Y)

        surface = go.Surface(x=Xi, y=Yi, z=Z, colorbar = go.ColorBar(title='Tesla',titleside='right'), colorscale = 'Viridis')
        data = [surface]

        fig = go.Figure(data=data, layout=layout)
        plot_html = new_iplot(fig,show_link=False)
        if interp:
            savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_interp_{4}.html'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),  self.suffix)
        else:
            savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_{4}.html'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix)
        with open(savename,'w') as html_file:
            html_file.write(plot_html)

    def plot_A_v_B_and_C_plotly_v2(self,A='Bz',B='X',C='Z',interp=False,interp_num=300, *conditions,**kwargs):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent. A bit complicated right now to get
        proper setup for contour plotting."""
        #init_notebook_mode()
        layout = go.Layout(
                        title='Plot of {0} vs {1} and {2} for DS, {3}'.format(A,B,C,conditions[0]),
                        autosize=False,
                        width=675,
                        height=650,
                        scene=dict(
                                xaxis=dict(
                                        title='{} (mm)'.format(C),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                yaxis=dict(
                                        title='{} (mm)'.format(B),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                zaxis=dict(
                                        title='{} (T)'.format(A),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                cameraposition=[[-0.1, 0.5, -0.7, -0.2], [0.0, 0, 0.0], 2.8]
                                ),
                        showlegend=True,
                        )

        if 'data_frame' in kwargs:
            data_frame = kwargs['data_frame']
        else:
            data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))

        if interp:
            data_frame_interp_grid = self.make_interp_grid(AB=[[B,data_frame[B].min(),data_frame[B].max()],[C,data_frame[C].min(),data_frame[C].max()]],
                    data_frame_orig=data_frame,val_name=A,interp_num=interp_num)
            data_frame = self.interpolate_data(data_frame, data_frame_interp_grid, field = A, x_ax = B, y_ax =C, method='cubic')

        data_frame = data_frame.reindex(columns=[A,B,C])
        piv = data_frame.pivot(B,C,A)
        X=piv.columns.values
        Y=piv.index.values
        Z=piv.values
        Xi,Yi = np.meshgrid(X, Y)

        surface = go.Surface(x=Xi, y=Yi, z=Z, colorbar = go.ColorBar(title='Tesla',titleside='right'), colorscale = 'Viridis')
        data = [surface]

        fig = go.Figure(data=data, layout=layout)
        #plot_html = new_iplot(fig,show_link=False)
        plot(fig)
        #if interp:
        #    savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_interp_{4}.html'.format(A,B,C,'_'.join(filter(None,conditions+(self.extra_suffix,))),  self.suffix)
        #else:
        #    savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_{4}.html'.format(A,B,C,'_'.join(filter(None,conditions+(self.extra_suffix,))),self.suffix)
        #with open(savename,'w') as html_file:
            #html_file.write('<script type="text/javascript">'
            #        +get_plotlyjs()
            #        +'</script>'
            #        +plot_html)
         #   html_file.write(plot_html)

    def plot_A_v_B_and_C_plotly_nb(self,A='Bz',B='X',C='Z',interp=False,interp_num=300, *conditions,**kwargs):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent. A bit complicated right now to get
        proper setup for contour plotting."""
        layout = go.Layout(
                        title='Plot of {0} vs {1} and {2} for DS, {3}'.format(A,B,C,conditions[0]),
                        autosize=False,
                        width=675,
                        height=650,
                        scene=dict(
                                xaxis=dict(
                                        title='{} (mm)'.format(C),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                yaxis=dict(
                                        title='{} (mm)'.format(B),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                zaxis=dict(
                                        title='{} (T)'.format(A),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                cameraposition=[[-0.1, 0.5, -0.7, -0.2], [0.0, 0, 0.0], 2.8]
                                ),
                        showlegend=True,
                        )

        if 'data_frame' in kwargs:
            data_frame = kwargs['data_frame']
        else:
            data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))

        if interp:
            data_frame_interp_grid = self.make_interp_grid(AB=[[B,data_frame[B].min(),data_frame[B].max()],[C,data_frame[C].min(),data_frame[C].max()]],
                    data_frame_orig=data_frame,val_name=A,interp_num=interp_num)
            data_frame = self.interpolate_data(data_frame, data_frame_interp_grid, field = A, x_ax = B, y_ax =C, method='cubic')

        data_frame = data_frame.reindex(columns=[A,B,C])
        piv = data_frame.pivot(B,C,A)
        X=piv.columns.values
        Y=piv.index.values
        Z=piv.values
        Xi,Yi = np.meshgrid(X, Y)

        surface = go.Surface(x=Xi, y=Yi, z=Z, colorbar = go.ColorBar(title='Tesla',titleside='right'), colorscale = 'Viridis')
        data = [surface]

        fig = go.Figure(data=data, layout=layout)
        iplot(fig)


    @plot_wrapper
    def plot_A_v_B_and_C_ratio(self,A='Bz',B='X',C='Z', *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The ratio plotter will plot 2N-1 plots, where N is the number of items in the data dictionary.
        Each data set will be plotted, and ratios will also be plotted for main/extras.
        """

        labels = list(self.data_frame_dict.keys())
        labels = [re.sub('_','\_',i) for i in labels]

        data_frame_dict = OrderedDict()
        piv_dict = OrderedDict()
        X = None
        Y = None
        Xi = None
        Yi = None
        surf = None
        for i,key in enumerate(self.data_frame_dict):
            if i>0: self.plot_count+=1
            data_frame_dict[key] = self.data_frame_dict[key].query(' and '.join(conditions))
            data_frame_dict[key] = data_frame_dict[key].reindex(columns=[A,B,C])

            piv_dict[key] = data_frame_dict[key].pivot(B,C,A)
            if i==0:
                X=piv_dict[key].columns.values
                Y=piv_dict[key].index.values
                Xi,Yi = np.meshgrid(X, Y)
            Z=piv_dict[key].values


            fig = plt.figure(self.plot_count)
            heat = plt.pcolormesh(Xi,Yi,Z)

            cb = plt.colorbar(heat, shrink=0.5, aspect=5)
            cb.set_label(A)

            plt.xlabel(C)
            plt.ylabel(B)
            plt.title('{0}, {1} vs {2} and {3}, {4}'.format(key,A,B,C,conditions[0]))
            plt.grid(True)
            plt.savefig(self.save_dir_extra+'/{0}_v_{1}_and_{2}_at_{3}_heat_{4}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),key),bbox_inches='tight')

            if i>0:
                self.plot_count+=1

#
                fig = plt.figure(self.plot_count).gca(projection='3d')
                surf = fig.plot_surface(Xi, Yi, list(piv_dict.values())[0].values/Z, rstride=1, cstride=1, cmap=cm.coolwarm,
                                        linewidth=0, antialiased=False)
                fig.zaxis.set_major_locator(LinearLocator(10))
                fig.zaxis.set_major_formatter(FormatStrFormatter('%.03f'))
                fig.view_init(elev=9., azim=-112)

                plt.xlabel(C)
                plt.ylabel(B)
                zlims = surf.get_axes().get_zlim()
                zlims[0] = math.floor(zlims[0]*100)/100.0
                zlims[1] = math.ceil(zlims[1]*100)/100.0
                ticks_width = (zlims[1]-zlims[0])/10.0

                fig.set_zticks(np.arange(zlims[0],zlims[1],ticks_width))
                plt.title('{0}/{1}, {2} vs {3} and {4}, {5}'.format(list(piv_dict.keys())[0],key,A,B,C,conditions[0]))
                plt.savefig(self.save_dir_extra+'/{0}_v_{1}_and_{2}_at_{3}_cont_ratio_{4}_{5}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),list(piv_dict.keys())[0],key),bbox_inches='tight')
#
                self.plot_count+=1
                fig = plt.figure(self.plot_count)
                heat = plt.pcolormesh(Xi,Yi,list(piv_dict.values())[0].values/Z)

                cb = plt.colorbar(heat, shrink=0.5, aspect=5)
                cb.set_label(r'$\frac{\mathrm{'+labels[0]+r'}}{\mathrm{'+labels[i]+r'}}$',fontsize=20,labelpad=20)
                cb.formatter.set_useOffset(False)
                cb.update_ticks()

                plt.xlabel(C)
                plt.ylabel(B)
                plt.title('{0}/{1}, {2} vs {3} and {4}, {5}'.format(list(piv_dict.keys())[0],key,A,B,C,conditions[0]))
                plt.grid(True)
                plt.savefig(self.save_dir_extra+'/{0}_v_{1}_and_{2}_at_{3}_heat_ratio_{4}_{5}.png'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),list(piv_dict.keys())[0],key),bbox_inches='tight')


        return surf,data_frame_dict

    def plot_A_v_B_and_C_ratio_plotly(self,A='Bz',B='X',C='Z', *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The ratio plotter will plot 2N-1 plots, where N is the number of items in the data dictionary.
        Each data set will be plotted, and ratios will also be plotted for main/extras.
        """
        #init_notebook_mode()
        layout = go.Layout(
                        #title='Plot of {0}/{1}, {2} vs {3} and {4} for DS, {5}'.format(piv_dict.keys()[0],key,A,B,C,conditions[0]),
                        autosize=False,
                        width=675,
                        height=650,
                        scene=dict(
                                xaxis=dict(
                                        title='{} (mm)'.format(C),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                yaxis=dict(
                                        title='{} (mm)'.format(B),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                zaxis=dict(
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                cameraposition=[[-0.1, 0.5, -0.7, -0.2], [0.0, 0, 0.0], 2.8]
                                ),
                        showlegend=True,
                        )


        labels = list(self.data_frame_dict.keys())
        labels = [re.sub('_','\_',i) for i in labels]

        data_frame_dict = OrderedDict()
        piv_dict = OrderedDict()
        X = None
        Y = None
        Xi = None
        Yi = None
        for i,key in enumerate(self.data_frame_dict):
            data_frame_dict[key] = self.data_frame_dict[key].query(' and '.join(conditions))
            data_frame_dict[key] = data_frame_dict[key].reindex(columns=[A,B,C])

            piv_dict[key] = data_frame_dict[key].pivot(B,C,A)
            if i==0:
                X=piv_dict[key].columns.values
                Y=piv_dict[key].index.values
                Xi,Yi = np.meshgrid(X, Y)
            Z=piv_dict[key].values

            if i>0:
                surface = go.Surface(x=Xi, y=Yi, z=list(piv_dict.values())[0].values/Z, colorbar = go.ColorBar(title='{0}/{1}'.format(list(piv_dict.keys())[0],key),titleside='right'), colorscale = 'Viridis')
                data = [surface]

                layout['title']=('{0}/{1}, {2} vs {3} and {4}, {5}'.format(list(piv_dict.keys())[0],key,A,B,C,conditions[0]))
                #layout['scene']['zaxis']['title']='{0}/{1}'.format(piv_dict.keys()[0],key)
                fig = go.Figure(data=data, layout=layout)
                plot_html = new_iplot(fig,show_link=False)
                savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_{3}_cont_ratio_{4}_{5}.html'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),list(piv_dict.keys())[0],key)
                with open(savename,'w') as html_file:
                    #html_file.write('<script type="text/javascript">'
                    #        +get_plotlyjs()
                    #        +'</script>'
                    #        +plot_html)
                    html_file.write(plot_html)

    @plot_wrapper
    def plot_A_v_B_and_C_fit(self,A='Bz',B='X',C='Z', sim=False, do_3d=False, do_eval = False, *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The distribution will be fit, or a previously made fit will displayed.
        """

        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        print(data_frame.head())
        if not self.fit_result: raise Exception('no fit available')
        fig1 = plt.figure(self.plot_count)

        plt.rc('font', family='serif')
        data_frame = data_frame.reindex(columns=[A,B,C])
        piv = data_frame.pivot(C,B,A)
        Xa=piv.columns.values
        Ya=piv.index.values
        X,Y = np.meshgrid(Xa, Ya)
        Z=piv.values

        ax1 = fig1.add_subplot(111,projection='3d')
        ax1.scatter(X.ravel(), Y.ravel(), Z.ravel(), color='black')

        ax1.set_xlabel(B)
        ax1.set_ylabel(C)
        ax1.set_zlabel(A)

        if do_eval:
            best_fit = self.fit_result.eval(r=X,z=Y)
        else:
            best_fit = self.fit_result.best_fit

        if do_3d:
            l = len(best_fit)/3
            if A=='Br':
                ax1.plot_wireframe(X, Y, best_fit[:l].reshape(Z.shape),color='green')
            elif A=='Bz':
                ax1.plot_wireframe(X, Y, best_fit[l:2*l].reshape(Z.shape),color='green')
            elif A=='Bphi':
                ax1.plot_wireframe(X, Y, best_fit[2*l:].reshape(Z.shape),color='green')

        elif sim and A=='Bz':
            ax1.plot_wireframe(X, Y, best_fit[len(best_fit)/2:].reshape(Z.shape),color='green')
        elif sim and (A=='Br' or A=='By' or A == 'Bx'):
            ax1.plot_wireframe(X, Y, best_fit[0:len(best_fit)/2].reshape(Z.shape),color='green')
        else:
            ax1.plot_wireframe(X, Y, best_fit.reshape(Z.shape),color='green')
        if A=='Bz':
            ax1.view_init(elev=20., azim=59)
        else:
            ax1.view_init(elev=35., azim=15)
        plt.show()
        if self.MultiScreen: plt.get_current_fig_manager().window.wm_geometry("-2600-600")
        savename = self.save_dir+'/{0}_v_{1}_and_{2}_{3}_fit.pdf'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
        plt.savefig(savename,transparent = True)

        self.plot_count+=1
        fig2 = plt.figure(self.plot_count)
        ax3 = fig2.add_subplot(111)
        if do_3d:
            l = len(best_fit)/3
            if A=='Br':
                data_fit_diff = (Z - best_fit[:l].reshape(Z.shape))*10000
            elif A=='Bz':
                data_fit_diff = (Z - best_fit[l:2*l].reshape(Z.shape))*10000
            elif A=='Bphi':
                data_fit_diff = (Z - best_fit[2*l:].reshape(Z.shape))*10000

        elif sim and A=='Bz':
            data_fit_diff = (Z - best_fit[len(best_fit)/2:].reshape(Z.shape))*10000
        elif sim and (A=='Br' or A=='By' or A=='Bx'):
            data_fit_diff = (Z - best_fit[0:len(best_fit)/2].reshape(Z.shape))*10000
        else:
            data_fit_diff = (Z - best_fit.reshape(Z.shape))*10000

        Xa = np.concatenate(([Xa[0]],0.5*(Xa[1:]+Xa[:-1]),[Xa[-1]]))
        Ya = np.concatenate(([Ya[0]],0.5*(Ya[1:]+Ya[:-1]),[Ya[-1]]))
        heat = ax3.pcolormesh(Xa,Ya,data_fit_diff,vmin=-10,vmax=10)

        cb = plt.colorbar(heat, aspect=7)
        cb.set_label('Data-Fit (G)')
        ax3.set_xlabel(B)
        ax3.set_ylabel(C)
        plt.show()
        if self.MultiScreen: plt.get_current_fig_manager().window.wm_geometry("-2600-600")
        savename = self.save_dir+'/{0}_v_{1}_and_{2}_{3}_residual.pdf'.format(A,B,C,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
        plt.savefig(savename,transparent = True)
        #outname =    '{0}_v_{1}_and_{2}_{3}'.format(A,B,C,'_'.join(conditions))
        #return fig1, outname

    @plot_wrapper
    def plot_A_v_B_and_C_fit_cyl(self,A='Bz',B='R',C='Z', phi_steps = (0,), zlims = [-2,2], do_eval = False, *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The distribution will be fit, or a previously made fit will displayed.
        """
        self.plot_count-=1
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))

        for i,phi in enumerate(phi_steps):
            self.plot_count+=1
            if phi==0: nphi = np.pi
            else: nphi=phi-np.pi

            data_frame_phi = data_frame[(np.abs(data_frame.Phi-phi)<1e-6)|(np.abs(data_frame.Phi-nphi)<1e-6)]
            data_frame_phi.ix[np.abs(data_frame_phi.Phi-nphi)<1e-6, 'R']*=-1
            if phi>np.pi/2:
                data_frame_phi.Phi=data_frame_phi.Phi+np.pi
                data_frame_phi.ix[data_frame_phi.Phi>np.pi, 'Phi']-=(2*np.pi)

            print(data_frame.head())
            if not self.fit_result: raise Exception('no fit available')
            fig1 = plt.figure(self.plot_count)

            plt.rc('font', family='serif')
            data_frame_phi = data_frame_phi.reindex(columns=[A,B,C])
            piv = data_frame_phi.pivot(C,B,A)
            Xa=piv.columns.values
            Ya=piv.index.values
            X,Y = np.meshgrid(Xa, Ya)
            Z=piv.values

            ax1 = fig1.add_subplot(111,projection='3d')
            ax1.plot(X.ravel(), Y.ravel(), Z.ravel(), 'ko',markersize=2 )

            ax1.set_xlabel(B)
            ax1.set_ylabel(C)
            ax1.set_zlabel(A)

            if do_eval:
                best_fit = self.fit_result.eval(r=X,z=Y)
            else:
                best_fit = self.fit_result.best_fit

            l = int(len(best_fit)/3)
            print(l)
            if A=='Br':
                bf = best_fit[:l]
            elif A=='Bz':
                bf = best_fit[l:int(2*l)]
            elif A=='Bphi':
                bf = best_fit[int(2*l):]
            p = len(bf)
            bf = bf[(i/len(phi_steps))*p:((i+1)/len(phi_steps))*p]
            ax1.plot_wireframe(X, Y, bf.reshape(Z.shape),color='green')
            plt.title('{0}_v_{1}_and_{2}_phi={3}'.format(A,B,C,phi))

            if A=='Bz':
                ax1.view_init(elev=20., azim=59)
            else:
                ax1.view_init(elev=35., azim=15)
            #plt.show()
            if self.MultiScreen: plt.get_current_fig_manager().window.wm_geometry("-2600-600")
            if self.use_html_dir:
                savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_phi={3}_{4}_fit.png'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            else:
                savename = self.save_dir+'/{0}_v_{1}_and_{2}_at_phi={3}_{4}_fit.pdf'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            plt.savefig(savename,transparent = True)

            self.plot_count+=1
            fig2 = plt.figure(self.plot_count)
            ax3 = fig2.add_subplot(111)

            data_fit_diff = (Z - bf.reshape(Z.shape))*10000

            Xa = np.concatenate(([Xa[0]],0.5*(Xa[1:]+Xa[:-1]),[Xa[-1]]))
            Ya = np.concatenate(([Ya[0]],0.5*(Ya[1:]+Ya[:-1]),[Ya[-1]]))
            heat = ax3.pcolormesh(Xa,Ya,data_fit_diff,vmin=zlims[0],vmax=zlims[1],cmap=plt.get_cmap('viridis'))
            plt.title('{0}_v_{1}_and_{2}_phi={3}'.format(A,B,C,phi))

            cb = plt.colorbar(heat, aspect=7)
            cb.set_label('Data-Fit (G)')
            ax3.set_xlabel(B)
            ax3.set_ylabel(C)
            datacursor(heat, hover=True, bbox=dict(alpha=1, fc='w'))
            #plt.show()
            if self.MultiScreen: plt.get_current_fig_manager().window.wm_geometry("-2600-600")
            if self.use_html_dir:
                savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_phi={3}_{4}_heat.png'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            else:
                savename = self.save_dir+'/{0}_v_{1}_and_{2}_at_phi={3}_{4}_heat.pdf'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))

            plt.savefig(savename,transparent = True)
            #outname = '{0}_v_{1}_and_{2}_{3}'.format(A,B,C,'_'.join(conditions))

    @plot_wrapper
    def plot_A_v_B_and_C_fit_ext(self,A='Bz',B='X',C='Z', xy_steps = (0,), do_eval = False, *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The distribution will be fit, or a previously made fit will displayed.
        """
        self.plot_count-=1

        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        for i,y in enumerate(xy_steps):
            self.plot_count+=1

            data_frame_ext = data_frame[data_frame.Y==y]
            print(data_frame_ext.head())
            if not self.fit_result: raise Exception('no fit available')
            fig1 = plt.figure(self.plot_count)

            plt.rc('font', family='serif')
            data_frame_ext = data_frame_ext.reindex(columns=[A,B,C])
            piv = data_frame_ext.pivot(C,B,A)
            Xa=piv.columns.values
            Ya=piv.index.values
            X,Y = np.meshgrid(Xa, Ya)
            Z=piv.values

            ax1 = fig1.add_subplot(111,projection='3d')
            ax1.plot(X.ravel(), Y.ravel(), Z.ravel(), 'ko',markersize=2 )

            ax1.set_xlabel(B)
            ax1.set_ylabel(C)
            ax1.set_zlabel(A)

            if do_eval:
                best_fit = self.fit_result.eval(r=X,z=Y)
            else:
                best_fit = self.fit_result.best_fit

            l = len(best_fit)/3
            if A=='Bx':
                bf = best_fit[:l]
            elif A=='By':
                bf = best_fit[l:2*l]
            elif A=='Bz':
                bf = best_fit[2*l:]
            p = len(bf)
            bf = bf[(i/len(xy_steps))*p:((i+1)/len(xy_steps))*p]
            ax1.plot_wireframe(X, Y, bf.reshape(Z.shape),color='green')
            plt.title('{0}_v_{1}_and_{2}_y={3}'.format(A,B,C,y))

            if A=='Bz':
                ax1.view_init(elev=20., azim=59)
            else:
                ax1.view_init(elev=35., azim=15)
            plt.show()
            if self.MultiScreen: plt.get_current_fig_manager().window.wm_geometry("-2600-600")
            savename = self.save_dir+'/{0}_v_{1}_and_{2}_y={3}_{4}_fit.pdf'.format(A,B,C,y,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            plt.savefig(savename,transparent = True)

            self.plot_count+=1
            fig2 = plt.figure(self.plot_count)
            ax3 = fig2.add_subplot(111)

            data_fit_diff = (Z - bf.reshape(Z.shape))*10000

            Xa = np.concatenate(([Xa[0]],0.5*(Xa[1:]+Xa[:-1]),[Xa[-1]]))
            Ya = np.concatenate(([Ya[0]],0.5*(Ya[1:]+Ya[:-1]),[Ya[-1]]))
            heat = ax3.pcolormesh(Xa,Ya,data_fit_diff,vmin=-2,vmax=2, cmap=plt.get_cmap('viridis'))
            plt.title('{0}_v_{1}_and_{2}_y={3}'.format(A,B,C,y))

            cb = plt.colorbar(heat, aspect=7)
            cb.set_label('Data-Fit (G)')
            ax3.set_xlabel(B)
            ax3.set_ylabel(C)
            plt.show()
            if self.MultiScreen: plt.get_current_fig_manager().window.wm_geometry("-2600-600")
            savename = self.save_dir+'/{0}_v_{1}_and_{2}_y={3}_{4}_residual.pdf'.format(A,B,C,y,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            plt.savefig(savename,transparent = True)
            #outname =    '{0}_v_{1}_and_{2}_{3}'.format(A,B,C,'_'.join(conditions))

    def plot_A_v_B_and_C_fit_cyl_plotly(self,A='Bz',B='R',C='Z', phi_steps = (0,), zlims = [-2,2], do_eval = False, *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The distribution will be fit, or a previously made fit will displayed.
        """
        #init_notebook_mode()
        layout = go.Layout(
                        autosize=False,
                        width=675,
                        height=650,
                        scene=dict(
                                xaxis=dict(
                                        title='R (mm)',
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                yaxis=dict(
                                        title='Z (mm)',
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                zaxis=dict(
                                        title='{} (T)'.format(A),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        )
                                ),
                        showlegend=True,
                        )

        layout_heat = go.Layout(
                        autosize=False,
                        width=675,
                        height=650,
                        xaxis=dict(title='R (mm)', tickfont=dict(size=20)),
                        yaxis=dict(title='Z (mm)', tickfont=dict(size=20)),
        )

        #phi_steps = (0,)
        for i,phi in enumerate(phi_steps):
            data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
            if phi==0: nphi = np.pi
            else: nphi=phi-np.pi

            data_frame = data_frame[(np.abs(data_frame.Phi-phi)<1e-6)|(np.abs(data_frame.Phi-nphi)<1e-6)]
            data_frame.ix[np.abs(data_frame.Phi-nphi)<1e-6, 'R']*=-1

            #print data_frame.head()
            if not self.fit_result: raise Exception('no fit available')

            data_frame = data_frame.reindex(columns=[A,B,C])
            piv = data_frame.pivot(C,B,A)
            Xa=piv.columns.values
            Ya=piv.index.values
            X,Y = np.meshgrid(Xa, Ya)
            Z=piv.values

            #scat = ax1.plot(X.ravel(), Y.ravel(), Z.ravel(), 'ko',markersize=2 )
            scat = go.Scatter3d(x=X.ravel(), y=Y.ravel(), z=Z.ravel(),
                            mode='markers',
                            marker=dict(
                                size=3,
                                color='rgb(0, 0, 0)',
                                line=dict(
                                        color='rgb(0, 0, 0)',
                                ),
                                opacity=1
                                ),
                                name = 'data'
                            )
            if do_eval:
                best_fit = self.fit_result.eval(r=X,z=Y)
            else:
                best_fit = self.fit_result.best_fit

            l = len(best_fit)/3
            if A=='Br':
                bf = best_fit[:l]
            elif A=='Bz':
                bf = best_fit[l:2*l]
            elif A=='Bphi':
                bf = best_fit[2*l:]
            p = len(bf)
            bf = bf[(i/len(phi_steps))*p:((i+1)/len(phi_steps))*p]

            lines = [scat]
            line_marker = dict(color='green', width=2)
            do_leg = True
            for i, j, k in zip(X, Y, bf.reshape(Z.shape)):
                if do_leg:
                        lines.append(go.Scatter3d(x=i, y=j, z=k, mode='lines', line=line_marker,name='fit',legendgroup='fitgroup'))
                else:
                        lines.append(go.Scatter3d(x=i, y=j, z=k, mode='lines', line=line_marker, name='fit',legendgroup='fitgroup',showlegend=False))
                do_leg = False
            layout['title']='Plot of {0} vs {1} and {2} for {3}, phi={4}'.format(A,B,C,self.suffix,phi),
            fig = go.Figure(data=lines, layout=layout)

            plot_html = new_iplot(fig,show_link=False)
            savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_phi={3}_{4}_fit.html'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            print('plotting {0}_v_{1}_and_{2}_at_phi={3}_{4}_fit.html'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f])))
            #py.image.save_as(fig, savename[:-5]+'.png')
            with open(savename,'w') as html_file:
                html_file.write(plot_html)


            data_fit_diff = (Z - bf.reshape(Z.shape))*10000
            Xa = np.concatenate(([Xa[0]],0.5*(Xa[1:]+Xa[:-1]),[Xa[-1]]))
            Ya = np.concatenate(([Ya[0]],0.5*(Ya[1:]+Ya[:-1]),[Ya[-1]]))

            trace = go.Heatmap(x=Xa, y=Ya, z=data_fit_diff, colorscale='Viridis',
                    colorbar=dict(title='Data-Fit (G)', titlefont=dict(size=18),tickfont=dict(size=20)),zmin=zlims[0],zmax=zlims[1])
            layout_heat['title']='Residuals of {0} vs {1} and {2} for {3}, phi={4}'.format(A,B,C,self.suffix,phi),

            fig = go.Figure(data=[trace], layout = layout_heat)
            plot_html = new_iplot(fig,show_link=False)
            savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_phi={3}_{4}_heat.html'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            print('plotting {0}_v_{1}_and_{2}_at_phi={3}_{4}_heat.html'.format(A,B,C,phi,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f])))
            #py.image.save_as(fig, savename[:-5]+'.png')
            with open(savename,'w') as html_file:
                html_file.write(plot_html)

    def plot_A_v_B_and_C_fit_ext_plotly(self,A='Bz',B='X',C='Z', xy_steps= (0,), do_eval = False, *conditions):
        """Plot A vs B and C given some set of comma seperated boolean conditions.
        B and C are the independent, A is the dependent.

        The distribution will be fit, or a previously made fit will displayed.
        """
        init_notebook_mode()
        layout = go.Layout(
                        autosize=False,
                        width=675,
                        height=650,
                        scene=dict(
                                xaxis=dict(
                                        title='X (mm)',
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                yaxis=dict(
                                        title='Z (mm)',
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        ),
                                zaxis=dict(
                                        title='{} (T)'.format(A),
                                        gridcolor='rgb(255, 255, 255)',
                                        zerolinecolor='rgb(255, 255, 255)',
                                        showbackground=True,
                                        backgroundcolor='rgb(230, 230,230)'
                                        )
                                ),
                        showlegend=True,
                        )

        layout_heat = go.Layout(
                        autosize=False,
                        width=675,
                        height=650,
                        xaxis=dict(title='X (mm)', tickfont=dict(size=20)),
                        yaxis=dict(title='Z (mm)', tickfont=dict(size=20)),
        )

        #phi_steps = (0,)
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        for i,y in enumerate(xy_steps):

            data_frame_ext = data_frame[data_frame.Y==y]

            #print data_frame.head()
            if not self.fit_result: raise Exception('no fit available')

            data_frame_ext = data_frame_ext.reindex(columns=[A,B,C])
            piv = data_frame_ext.pivot(C,B,A)
            Xa=piv.columns.values
            Ya=piv.index.values
            X,Y = np.meshgrid(Xa, Ya)
            Z=piv.values

            #scat = ax1.plot(X.ravel(), Y.ravel(), Z.ravel(), 'ko',markersize=2 )
            scat = go.Scatter3d(x=X.ravel(), y=Y.ravel(), z=Z.ravel(),
                            mode='markers',
                            marker=dict(
                                size=3,
                                color='rgb(0, 0, 0)',
                                line=dict(
                                        color='rgb(0, 0, 0)',
                                ),
                                opacity=1
                                ),
                                name = 'data'
                            )
            if do_eval:
                best_fit = self.fit_result.eval(x=X,z=Z)
            else:
                best_fit = self.fit_result.best_fit

            l = len(best_fit)/3
            if A=='Bx':
                bf = best_fit[:l]
            elif A=='By':
                bf = best_fit[l:2*l]
            elif A=='Bz':
                bf = best_fit[2*l:]
            p = len(bf)
            bf = bf[(i/len(xy_steps))*p:((i+1)/len(xy_steps))*p]

            lines = [scat]
            line_marker = dict(color='green', width=2)
            do_leg = True
            for i, j, k in zip(X, Y, bf.reshape(Z.shape)):
                if do_leg:
                        lines.append(go.Scatter3d(x=i, y=j, z=k, mode='lines', line=line_marker,name='fit',legendgroup='fitgroup'))
                else:
                        lines.append(go.Scatter3d(x=i, y=j, z=k, mode='lines', line=line_marker, name='fit',legendgroup='fitgroup',showlegend=False))
                do_leg = False
            layout['title']='Plot of {0} vs {1} and {2} for {3}, y={4}'.format(A,B,C,self.suffix,y),
            fig = go.Figure(data=lines, layout=layout)

            plot_html = new_iplot(fig,show_link=False)
            savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_y={3}_{4}_fit.html'.format(A,B,C,y,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            py.image.save_as(fig, savename[:-5]+'.png')
            with open(savename,'w') as html_file:
                html_file.write(plot_html)

            data_fit_diff = (Z - bf.reshape(Z.shape))*10000
            Xa = np.concatenate(([Xa[0]],0.5*(Xa[1:]+Xa[:-1]),[Xa[-1]]))
            Ya = np.concatenate(([Ya[0]],0.5*(Ya[1:]+Ya[:-1]),[Ya[-1]]))

            trace = go.Heatmap(x=Xa, y=Ya, z=data_fit_diff, colorscale='Viridis',
                    colorbar=dict(title='Data-Fit (G)', titlefont=dict(size=18),tickfont=dict(size=20)),zmin=-2,zmax=2)
            layout_heat['title']='Residuals of {0} vs {1} and {2} for {3}, y={4}'.format(A,B,C,self.suffix,y),

            fig = go.Figure(data=[trace], layout = layout_heat)
            plot_html = new_iplot(fig,show_link=False)
            savename = self.html_dir+'/{0}_v_{1}_and_{2}_at_y={3}_{4}_heat.html'.format(A,B,C,y,'_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]))
            py.image.save_as(fig, savename[:-5]+'.png')
            with open(savename,'w') as html_file:
                html_file.write(plot_html)
            #plot_url = iplot(fig)

    def make_gif(self, fig,outname):

        plt.figure(fig.number)
        ax = fig.get_axes()[0]
        plt.sca(ax)
        tmpdir = self.save_dir+'/anim/tmpfigs'
        gifdir = self.save_dir+'/anim'
        if not os.path.exists(tmpdir):
            os.makedirs(tmpdir)
        #fig.canvas.manager.window.attributes('-topmost', 1)
        #raw_input()
        for n in range(0, 360,2):
            ax.view_init(elev=35., azim=n)
            plt.draw()

            plt.savefig(tmpdir+'/' + outname + str(n).zfill(3) + '.png',dpi=60)

        #plt.close('all')
        #images = [PIL_Image.open(image) for image in glob.glob('../plots/anim/' + gif_filename + '/*.png')]
        images = []
        for image in glob.glob(tmpdir + '/*.png'):
            img = PIL_Image.open(image)
            images.append(img.copy())
            img.close()

        file_path_name = gifdir+'/'+outname+'.gif'
        writeGif(file_path_name, images, duration=0.15)
        IPdisplay.Image(url=file_path_name)
        shutil.rmtree(tmpdir)

        ##plt.show()


    @plot_wrapper
    def plot_A_v_Theta(self,A,r,z_cond,interp_num=200,method='linear',do_fit = True):
        """Plot A vs Theta for a given Z and R. The values are interpolated """

        print(self.data_frame_dict[self.suffix].head())
        data_frame = self.data_frame_dict[self.suffix].query(z_cond)
        if method!=None:

            data_frame_interp_grid = self.make_interp_grid(r=r, data_frame_orig=data_frame,val_name=A,interp_num=interp_num)
            data_frame_interp = self.interpolate_data(data_frame, data_frame_interp_grid, A,method=method)
            #data_frame_interp = data_frame_interp.query('R=={0}'.format(r))
            data_frame_interp = data_frame_interp[(data_frame_interp.R-r).abs()<0.0005]

        data_frame = data_frame[(data_frame.R-r).abs()<0.05]

        #print data_frame.head()
        #print data_frame_interp.head()
        #print data_frame.head()
        #raw_input()

        fig = plt.figure(self.plot_count)
        if method!=None:
            data_frame_interp.eval('{0}err = 0.0001*{0}'.format(A))
            #plt.plot(data_frame_interp.Theta,data_frame_interp[A],'b^')
            plt.errorbar(data_frame_interp.Phi,data_frame_interp[A],yerr=data_frame_interp[A+'err'],fmt='b^')
        plt.plot(data_frame.Phi,data_frame[A],'ro')
        plt.xlabel('Phi')
        plt.ylabel(A)
        plt.title('{0} vs Theta at {1} for R=={2}'.format(A,z_cond,r))
        ###plt.axis([-0.1, 3.24,0.22,0.26])
        plt.grid(True)
        savename = self.save_dir+'/{0}_v_Theta_at_{1}_R=={2}_{3}.png'.format(A,z_cond,r,self.suffix)
        if not do_fit:
            plt.savefig(savename,bbox_inches='tight')
        else:
            if method:
                popt,pcov = self.fit_radial_plot(data_frame_interp, A, savename=savename,fig=fig,p0=(-0.0001,0.0,0.05))
            else:
                popt,pcov = self.fit_radial_plot(data_frame, A, savename=savename,fig=fig,p0=(-0.0001,0.0,0.05))

        if (method and do_fit): return data_frame_interp,fig,popt,pcov
        elif (method and not do_fit): return data_frame_interp,fig
        elif (not method and do_fit): return data_frame,fig,popt,pcov
        else: return data_frame,fig

    def plot_symmetry(self, reflect = 'X',const = 'Z', interp = False, interp_num = 0, *conditions):
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        data_frame_top = data_frame[data_frame[reflect]>0].sort([const,reflect]).reset_index(drop=True)
        data_frame_bottom = data_frame[data_frame[reflect]<0].sort([const,reflect],ascending=[True,False]).reset_index(drop=True)
        data_frame_diff = data_frame_top.copy()
        data_frame_diff['Bz_diff'] = data_frame_top['Bz']-data_frame_bottom['Bz']
        data_frame_diff['Bx_diff'] = data_frame_top['Bx']-data_frame_bottom['Bx']
        data_frame_diff['By_diff'] = data_frame_top['By']-data_frame_bottom['By']
        data_frame_diff['Bphi_diff'] = data_frame_top['Bphi']-data_frame_bottom['Bphi']
        data_frame_diff['Br_diff'] = data_frame_top['Br']-data_frame_bottom['Br']
        data_frame_diff['Bz_add'] = data_frame_top['Bz']+data_frame_bottom['Bz']
        data_frame_diff['Bx_add'] = data_frame_top['Bx']+data_frame_bottom['Bx']
        data_frame_diff['By_add'] = data_frame_top['By']+data_frame_bottom['By']
        data_frame_diff['Bphi_add'] = data_frame_top['Bphi']+data_frame_bottom['Bphi']
        data_frame_diff['Br_add'] = data_frame_top['Br']+data_frame_bottom['Br']
        #self.plot_A_v_B_and_C('Bz_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bz_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C_plotly('Bx_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C_plotly('Bx_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        self.plot_A_v_B_and_C('Bx_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        self.plot_A_v_B_and_C('Bx_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('By_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('By_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bphi_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bphi_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Br_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Br_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bphi_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bphi_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bz_diff',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)
        #self.plot_A_v_B_and_C('Bz_add',reflect,const,interp,interp_num,*conditions,data_frame = data_frame_diff)

    @plot_wrapper
    def plot_mag_field(self,step_size = 1,*conditions):
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        fig, ax = plt.subplots(1,1)
        print('len Y',len(np.unique(data_frame.Y.values)))
        print('len X',len(np.unique(data_frame.X.values)))
        print(data_frame.head())
        quiv = ax.quiver(data_frame.X[::step_size],data_frame.Y[::step_size],data_frame.Bx[::step_size],data_frame.By[::step_size],pivot='mid')
        plt.quiverkey(quiv, 1400, -1430, 0.5, '0.5 T', coordinates='data',clim=[-1.1,5])
        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')
        ax.set_title('Radial Magnetic Components, {0}'.format([x for x in conditions if 'Z' in x]))
        plt.grid(True)
        circle2=plt.Circle((0,0),831.038507,color='b',fill=False)
        fig.gca().add_artist(circle2)
        fig.savefig(self.save_dir+'/PsField_{0}_{1}.png'.format('_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix))

    @plot_wrapper
    def plot_mag_field2(self,A,B,density= 1,*conditions):
        data_frame = self.data_frame_dict[self.suffix].query(' and '.join(conditions))
        fig, ax = plt.subplots(1,1)
        piv = data_frame.pivot(A,B,'B'+A.lower())
        xax = piv.columns.values
        yax = piv.index.values
        V = piv.values
        U = data_frame.pivot(A,B,'B'+B.lower()).values

        mag = np.sqrt(V**2+U**2)


        plt.streamplot(xax, yax, U, V, color = mag, density=density,linewidth=2)

        plt.xlabel('{} (mm)'.format(B))
        plt.ylabel('{} (mm)'.format(A))
        cb = plt.colorbar()
        cb.set_label('Mag (T)')

        plt.title('Magnetic Field Lines in {0}-{1} plane for {2}'.format(A,B,conditions))
        fig.savefig(self.save_dir+'/Field_Lines_{0}_{1}.png'.format('_'.join([_f for _f in conditions+(self.extra_suffix,) if _f]),self.suffix),bbox_inches='tight')

    def fit_radial_plot(self, df, mag, savename,fig=None,p0=(0.0001,0.0,0.05)):
        """Given a data_frame, fit the theta vs B(r)(z) plot and plot the result"""
        def cos_func(x, A,p1,p2):
            return A*np.cos(x+p1)+p2
        #popt, pcov = curve_fit(cos_func, df.Theta.values, df[mag].values, sigma=df[mag+'err'].values, absolute_sigma=True, p0=p0)
        popt, pcov = curve_fit(cos_func, df.Phi.values, df[mag].values, sigma=df[mag+'err'].values, p0=p0)
        try:
            std_devs = np.sqrt(np.diag(pcov))
        except:
            std_devs = [0,0,0]

        if fig==None:
            fig = plt.gcf()
        elif type(fig) == str and fig.lowercase() == 'new':
            self.plot_count+=1
            plt.figure(self.plot_count)

        curvex=np.linspace(-np.pi,np.pi,500)
        curvey=cos_func(curvex,popt[0],popt[1],popt[2])
        plt.plot(curvex,curvey,color='lawngreen',linestyle='--',linewidth=3)
        plt.figtext(0.33, 0.75,
                'Amplitude: {0:.2e}$\pm${1:.1e}\nPhase: {2:.2e}$\pm${3:.1e}\nY-Offset: {4:.2e}$\pm${5:.1e}'.format(
                    popt[0],std_devs[0],popt[1],std_devs[1],popt[2],std_devs[2]),
                size='large')
        plt.draw()
        if '.png' in savename: savename = savename.split('.png')[0]
        plt.savefig(savename+'_fit.png',bbox_inches='tight')
        return popt,pcov

    def fit_linear_regression(self, df,A,B,fig=None,text_x=0.15,text_y=0.75):
        """Basic WLS for DataFrames"""
        lm = wls(formula = '{0} ~ {1}'.format(A,B), data=df, weights=df[A+'err']).fit()
        if fig==None:
            fig = plt.gcf()
        elif type(fig) == str and fig.lower() == 'new':
            self.plot_count+=1
            fig = plt.figure(self.plot_count)

        abline_plot(model_results=lm,ax=fig.axes[0])
        plt.figtext(text_x, text_y,
            'Intercept: {0:.3e}$\pm${1:.3e}\nSlope: {2:.3e}$\pm${3:.3e}'.format(lm.params[0], lm.bse[0], lm.params[1], lm.bse[1]),
            figure=fig, size='large',axes=fig.axes[0])
        plt.draw()
        return lm

if __name__=="__main__":
    data_maker=DataFileMaker('../datafiles/FieldMapData_1760_v5/Mu2e_PSMap_fastTest',use_pickle = True)
    plot_maker = Plotter(data_maker.data_frame)
    #fit_compare_sweep()

