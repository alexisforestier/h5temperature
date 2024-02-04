import sys
import numpy as np
import traceback
#import pandas as pd
import h5py
from scipy.optimize import curve_fit
import matplotlib.pyplot
import matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from PyQt5.QtWidgets import (QApplication, 
                             QWidget,
                             QLabel,
                             QSpinBox,
                             QCheckBox,
#                            QDoubleSpinBox,
                             QGroupBox,
                             QPushButton,
                             QListWidget,
                             QFormLayout,
                             QVBoxLayout,
                             QHBoxLayout,
                             QFileDialog,
                             QMessageBox)

#from h5temperaturePhysics import planck, wien, temp2color
from h5temperatureModels import BlackBodyFromh5

class PlotsCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):

        self.fig, self.axes = matplotlib.pyplot.subplots(2, 2, 
                            constrained_layout=True)

        # Planck
        self.axes[0,0].set_xlabel('wavelength (nm)')
        self.axes[0,0].set_ylabel('intensity (arb. unit)')
        self.ax_planck_res = self.axes[0,0].twinx()
        self.ax_planck_res.set_ylabel('Planck fit residuals')

        # Wien
        self.axes[0,1].set_xlabel('1/wavelength (1/nm)')
        self.axes[0,1].set_ylabel('Wien')
        self.ax_wien_res = self.axes[0,1].twinx()
        self.ax_wien_res.set_ylabel('Wien fit residuals')

        # Two color
        self.axes[1,0].set_xlabel('wavelength (nm)')
        self.axes[1,0].set_ylabel('two-color temperature (K)')

        # Two color Histogram
        self.axes[1,1].set_xlabel('two-color temperature (K)')
        self.axes[1,1].set_ylabel('frequency')

        super(PlotsCanvas, self).__init__(self.fig)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.resize(1500,900)
        
        # data stored in self
        self.filepath = str()
        self.data = dict()
        # parameters and their default values
        self.pars = dict(lowerb = 550,
                         upperb = 900,
                         delta = 100)

        # left layout   
        load_button = QPushButton('Load h5')
        reload_button = QPushButton('Reload')
        clear_button = QPushButton('Clear')

        topleftbuttonslayout = QHBoxLayout()
        topleftbuttonslayout.addWidget(load_button)
        topleftbuttonslayout.addWidget(reload_button)

        currentfile_layout = QHBoxLayout()
        currentfile_label = QLabel('Current file:')
        self.currentfilename_label = QLabel('')
        self.currentfilename_label.setStyleSheet("border: 1px solid black;\
                                                  background-color: white")

        currentfile_layout.addWidget(currentfile_label, stretch=0)
        currentfile_layout.addWidget(self.currentfilename_label, stretch=10)

        self.dataset_list = QListWidget()
        self.dataset_list.setSelectionMode(1) # single selection

        leftlayout = QVBoxLayout()
        leftlayout.addLayout(topleftbuttonslayout)
        leftlayout.addLayout(currentfile_layout)
        leftlayout.addWidget(self.dataset_list)
        leftlayout.addWidget(clear_button)

        left_groupbox = QGroupBox('Data')
        left_groupbox.setLayout(leftlayout)

        left_groupbox.setMinimumWidth(230)

        # right layout
        lowerbound_spinbox = QSpinBox()
        upperbound_spinbox = QSpinBox()
        delta_spinbox = QSpinBox()

        lowerbound_spinbox.setMinimum(1)
        upperbound_spinbox.setMinimum(1)
        delta_spinbox.setMinimum(1)
        lowerbound_spinbox.setMaximum(9999)
        upperbound_spinbox.setMaximum(9999)
        delta_spinbox.setMaximum(9999)
        
        # default values:
        lowerbound_spinbox.setValue(self.pars.get('lowerb'))
        upperbound_spinbox.setValue(self.pars.get('upperb'))
        delta_spinbox.setValue(self.pars.get('delta'))

        choosedelta_button = QPushButton('Choose delta')
        fit_button = QPushButton('Re-fit')

        fitparam_form = QFormLayout()
        fitparam_form.addRow('Lower limit (nm):', lowerbound_spinbox)
        fitparam_form.addRow('Upper limit (nm):', upperbound_spinbox)
        fitparam_form.addRow('2-color delta (px):', delta_spinbox)
        
        fit_layout = QVBoxLayout()
        fit_layout.addLayout(fitparam_form)
        fit_layout.addWidget(choosedelta_button)
        fit_layout.addWidget(fit_button)
        fit_layout.addStretch()

        right_groupbox = QGroupBox('Fitting')
        right_groupbox.setLayout(fit_layout)
        right_groupbox.setMinimumWidth(200)

        # center layout
        center_groupbox = QGroupBox()
        center_groupbox.setStyleSheet('QGroupBox  {border: 2px solid gray;\
                                                background-color: white;}')
        plot_layout = QVBoxLayout()

        # set empty plots
        self.canvas = PlotsCanvas(self)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("font-size: 16px;")
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)

        center_groupbox.setLayout(plot_layout)

        layout = QHBoxLayout()
        layout.addWidget(left_groupbox, stretch=3)
        layout.addStretch()
        layout.addWidget(center_groupbox, stretch=12)
        layout.addStretch()
        layout.addWidget(right_groupbox, stretch=2)
        
        self.setLayout(layout)

        # CONNECTS

        load_button.clicked.connect(self.load_h5file)
        reload_button.clicked.connect(self.reload_h5file)
        clear_button.clicked.connect(self.clear_all)
        choosedelta_button.clicked.connect(
            lambda: self.choose_delta( self.dataset_list.currentItem().text() ))

        fit_button.clicked.connect(
            lambda: self.update_plots_fit(
                        self.dataset_list.currentItem().text()))

        lowerbound_spinbox.valueChanged.connect(
                lambda x: self.pars.__setitem__('lowerb', x))
        upperbound_spinbox.valueChanged.connect(
                lambda x: self.pars.__setitem__('upperb', x))
        delta_spinbox.valueChanged.connect(
                lambda x: self.pars.__setitem__('delta', x))

        self.dataset_list.currentTextChanged.connect(self.update)

    def get_h5file_content(self):
        # read h5 file and store in self.data: 
        with h5py.File(self.filepath, 'r') as file:
            for nam, dat in file.items():
            # /!\ when hdf5 files are open in another thread
            # it seems to lead to None in the entire subgroup...
            # this will need to be checked again...:
            # Can the last measured T be opened or not?
                if dat is not None: 
                # get temperature measurements only
                    if 'measurement/T_planck' in dat:
                    # not already loaded only:
                        if nam not in self.data:
                        # populate data:
                            self.data[nam] = BlackBodyFromh5(dat, nam)

    def populate_dataset_list(self):
        if self.data:
            # sort datasets in chronological order
            names_chrono = sorted(self.data.keys(), 
                            key = lambda k: self.data[k].timestamp)

            prev_items = [self.dataset_list.item(x).text() 
                    for x in range(self.dataset_list.count())]
            # new items will always be added at the end
            # thus data are in chronological order within 
            # a given h5 loaded but not globally. 
            for n in names_chrono:
                if n not in prev_items:
                    self.dataset_list.addItem(n)

    def load_h5file(self):
        options = QFileDialog.Options()
        # ! use Native dialog or qt dialog... 
        # ! Must be checked on different platforms !

    #   options |= QFileDialog.DontUseNativeDialog
        self.filepath, _ = QFileDialog.getOpenFileName(self,
            "Load HDF5 file", "","HDF5 file (*.h5)", 
            options=options)

        if self.filepath:
            self.get_h5file_content()
            self.populate_dataset_list()
            self.currentfilename_label.setText(self.filepath.split('/')[-1])
 
    def reload_h5file(self):
        if self.filepath:
            self.get_h5file_content()
            self.populate_dataset_list()

    def choose_delta(self, nam):
        import matplotlib.pyplot as plt
#        fig_delta, ax_delta = plt.subplots()
#        ax_delta.set_xlabel('delta (px)')
#        ax_delta.set_ylabel('Two-color temperature std. dev (K)')
#
#
#        # reread data... not ideal but it should work
#        lam = np.array( self.data[nam]['spectrum_lambdas'] )
#        y_planck = np.array( self.data[nam]['planck_data'] )
#        y_wien = wien(lam, y_planck)
#
#        within = np.logical_and(lam >= self.pars['lowerb'], 
#                                lam <= self.pars['upperb'])
#
#        alldeltas = np.array(range(300))
#        allstddevs = np.array( [temp2color(lam[within], y_wien[within], di).std() 
#                            for di in alldeltas ] )
#
#        ax_delta.scatter(alldeltas, 
#                         allstddevs,
#                         marker='X',
#                         edgecolor='k',
#                         color='royalblue',
#                         alpha=0.5,
#                         s=30)
#
#        ax_delta.set_ylim([0,1e3])
#        fig_delta.show()
#
#        def get_xclick(event): 
#            x = int(event.xdata)
#            print(x)
#
#        # click event
#        fig_delta.canvas.mpl_connect('button_press_event', get_xclick)


    def clear_all(self):
        self.filepath = str()
        self.currentfilename_label.setText('')
        self.data = dict()
        self.dataset_list.clear()

        self.clear_plots()
        self.canvas.draw()

    def clear_plots(self):
        # clear previous data on plots
        self.canvas.axes[0,0].collections.clear()
        self.canvas.axes[0,1].collections.clear()
        self.canvas.axes[1,0].collections.clear()
        # to remove histogram bars:
        _ = [b.remove() for b in self.canvas.axes[1,1].containers]

        self.canvas.ax_planck_res.collections.clear()
        self.canvas.ax_wien_res.collections.clear()

        self.canvas.axes[0,0].lines.clear()
        self.canvas.axes[0,1].lines.clear()
        self.canvas.axes[1,0].lines.clear()
        self.canvas.axes[1,1].lines.clear()

        self.canvas.axes[0,0].texts.clear()
        self.canvas.axes[0,1].texts.clear()
        self.canvas.axes[1,0].texts.clear()
        self.canvas.axes[1,1].texts.clear()

    def eval_fits(self, nam, interval, delta):
        # eval all quantities for a given spectrum
        try:
            self.data[nam].eval_twocolor(interval, delta)
            self.data[nam].eval_wien_fit(interval)
            self.data[nam].eval_planck_fit(interval)
        except Exception:
            traceback.print_exc()

    def update(self, nam):
        interval = self.pars['lowerb'], self.pars['upperb']

        self.clear_plots()
        self.plot_data(nam)

        # do something to check if fit was already calculated...

        self.eval_fits(nam, interval, self.pars['delta'])
        self.plot_fits(nam)


    def plot_data(self, nam):
        # plot data
        current = self.data[nam]

        self.canvas.axes[0,0].scatter(current.lam, 
                                      current.planck, 
                                      edgecolor='k',
                                      facecolor='royalblue',
                                      alpha=.3,
                                      s=15, 
                                      label='Planck data')

        self.canvas.axes[0,1].scatter(1 / current.lam, 
                                      current.wien, 
                                      edgecolor='k',
                                      facecolor='royalblue',
                                      alpha=.3,
                                      s=15, 
                                      label='Wien data')

    def plot_fits(self, nam):

        current = self.data[nam]
        interval = [self.pars['lowerb'], self.pars['upperb']]

        self.canvas.axes[1,0].scatter(
            current.lam_infit(interval)[:-self.pars['delta']], 
            current.twocolor, 
            edgecolor='k',
            facecolor='royalblue',
            alpha=.3,
            s=15, 
            label='two-color data')

        h_y, h_x, _ = self.canvas.axes[1,1].hist(current.twocolor, 
                                   color='royalblue',
                                   bins = 50,
                                   alpha=.6, 
                                   label='two-color histogram')

        # plot fits:
        self.canvas.axes[0,0].plot(current.lam_infit(interval),
                                   current.planck_fit,
                                   color='r',
                                   linewidth=2,
                                   label='Planck fit')
        self.canvas.ax_planck_res.scatter(current.lam_infit(interval), 
                                          current.planck_residuals, 
                                          color='gray',
                                          alpha=0.1,
                                          s=15, 
                                          label='residuals')

        self.canvas.axes[0,1].plot(1 / current.lam_infit(interval), 
                                   current.wien_fit, 
                                   c='r', 
                                   linewidth=2, 
                                   label='Wien fit')

        self.canvas.axes[1,0].axhline(np.mean(current.twocolor), 
                                      color='r',
                                      linestyle='dashed',
                                      label='mean')            
        
        self.canvas.ax_wien_res.scatter(1 / current.lam_infit(interval), 
                                        current.wien_residuals, 
                                        color='gray',
                                        alpha=0.1,
                                        s=15, 
                                        label='residuals')

        # texts on plots:
        self.canvas.axes[0,0].text(0.1, 0.7, 
                            'T$_\\mathrm{Planck}$= ' + 
                            str( round(current.T_planck) ) + 
                            ' K', 
                            size=17, 
                            color='r', 
                            zorder=3,
                            transform=self.canvas.axes[0,0].transAxes)

        self.canvas.axes[0,1].text(0.1, 0.7, 
                            'T$_\\mathrm{Wien}$= ' + 
                            str( round(current.T_wien) ) + 
                            ' K', 
                            size=17, 
                            color='r', 
                            zorder=3,
                            transform=self.canvas.axes[0,1].transAxes)
        
        self.canvas.axes[1,0].text(0.3, 0.7, 
                            'T$_\\mathrm{two-color}$= ' + 
                            str( round( current.T_twocolor ) ) + 
                            ' K', 
                            size=17, 
                            color='r', 
                            zorder=3,
                            transform=self.canvas.axes[1,0].transAxes)

        self.canvas.axes[1,1].text(0.1, 0.8, 
                            'std dev. = ' + 
                            str( round( current.T_std_twocolor ) ) + 
                            ' K', 
                            size=17, 
                            color='r', 
                            zorder=3,
                                transform=self.canvas.axes[1,1].transAxes)
        # Autoscale:
        # planck:
        self.canvas.axes[0,0].set_xlim([self.pars['lowerb'] - 100, 
                                        self.pars['upperb'] + 100]) 

        self.canvas.axes[0,0].set_ylim([np.min( current.planck_fit - \
                                            0.5*np.ptp(current.planck_fit)),
                                        np.max( current.planck_fit + \
                                            0.5*np.ptp(current.planck_fit))])

        self.canvas.ax_planck_res.set_ylim([
            np.min( current.planck_residuals ),
            np.max( current.planck_residuals ) ])

        # wien:
        self.canvas.axes[0,1].set_xlim(
            [np.min( 1/current.lam_infit(interval) - 0.0002 ),
             np.max( 1/current.lam_infit(interval) + 0.0002 )])

        self.canvas.axes[0,1].set_ylim([np.min( current.wien_fit - \
                                            0.5*np.ptp(current.wien_fit)),
                                        np.max( current.wien_fit + \
                                            0.5*np.ptp(current.wien_fit))])
        self.canvas.ax_wien_res.set_ylim([
            np.min( current.wien_fit ),
            np.max( current.wien_fit )])

        # 2color:
        self.canvas.axes[1,0].set_xlim([self.pars['lowerb'],
                                        self.pars['upperb']+20])
        self.canvas.axes[1,0].set_ylim(
            [current.T_twocolor - 5 * current.T_std_twocolor, 
             current.T_twocolor + 5 * current.T_std_twocolor])

        # histogram
        self.canvas.axes[1,1].set_xlim(
            [current.T_twocolor - 5 * current.T_std_twocolor,
             current.T_twocolor + 5 * current.T_std_twocolor])
        self.canvas.axes[1,1].set_ylim([0, np.max(h_y) + 10])

        # legends
        self.canvas.axes[0,0].legend(loc='upper left')
        self.canvas.ax_planck_res.legend(loc='upper right')
        self.canvas.axes[0,1].legend(loc='upper left')   
        self.canvas.ax_wien_res.legend(loc='upper right')
        self.canvas.axes[1,0].legend() 
        self.canvas.axes[1,1].legend()
            
        self.canvas.draw()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    app.exec()