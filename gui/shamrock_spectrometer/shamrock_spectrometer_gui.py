# -*- coding: utf-8 -*-
"""
This module contains a GUI for operating the spectrum logic module.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import os
import pyqtgraph as pg
import numpy as np

from core.connector import Connector
from core.util import units

from gui.colordefs import QudiPalettePale as palette
from gui.guibase import GUIBase
from gui.fitsettings import FitSettingsDialog, FitSettingsComboBox
from qtpy import QtCore
from qtpy import QtWidgets
from qtpy import uic


class SpectrometerWindow(QtWidgets.QMainWindow):

    def __init__(self):
        """ Create the laser scanner window.
        """
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_shamrock_spectrometer.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class SpectrometerGui(GUIBase):
    """
    """

    # declare connectors
    spectrum_logic_connector = Connector(interface='spectrumlogic')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition and initialisation of the GUI.
        """

        # connect the logic module from the declared connector
        self._spectrum_logic = self.spectrum_logic_connector()

        # setting up the window
        self._mw = SpectrometerWindow()

        self._mw.run_acquisition_Action.triggered.connect(self.run_acquisition)

        self._mw.stop_acquisition_Action.triggered.connect(self.stop_acquisition)

        # giving the plots names allows us to link their axes together
        self._plot = self._mw.plotWidget
        self._plot_item = self._plot.plotItem

        # create a new ViewBox, link the right axis to its coordinate system
        self._right_axis = pg.ViewBox() # Create a ViewBox right axis
        self._plot_item.showAxis('right') # Show the right axis of plotItem
        self._plot_item.scene().addItem(self._right_axis) # associate the ViewBox right axis to the plotItem
        self._plot_item.getAxis('right').linkToView(self._right_axis) # link this right axis to the ViewBox
        self._right_axis.setXLink(self._plot_item) # link the ViewBox object to the plotItem x axis

        # create a new ViewBox, link the top axis to its coordinate system (same procedure)
        self._top_axis = pg.ViewBox()
        self._plot_item.showAxis('top')
        self._plot_item.scene().addItem(self._top_axis)
        self._plot_item.getAxis('top').linkToView(self._top_axis)
        self._top_axis.setYLink(self._plot_item)
        self._top_axis.invertX(b=True) # We force the x axis to be rightward

        # label plot axis :

        self._plot.setLabel('left', 'Fluorescence', units='counts/s')
        self._plot.setLabel('right', 'Number of Points', units='#')
        self._plot.setLabel('bottom', 'Wavelength', units='m')
        self._plot.setLabel('top', 'Relative Frequency', units='Hz')

        # Create 2 empty plot curve to be filled later, set its pen (curve style)
        self._curve1 = self._plot.plot()
        self._curve1.setPen(palette.c1, width=2)

        # Connect signals
        self._mw.run_acquisition_Action.triggered.connect(self.run_acquisition)

        self._mw.stop_acquisition_Action.triggered.connect(self.stop_acquisition)

        self.update_data()

        self._save_PNG = True

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """

        self._mw.close()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def run_acquisition(self):
        """Run the spectrum acquisition called from run_acquisition_Action
        and plot the spectrum data obtained.
        """
        self._spectrum_logic.acquire_single_spectrum()
        data = self._spectrum_logic._spectrum_data
        self._curve1.setData(x=data[0,:],y=data[1,:])

    def stop_acquisition(self):
        """Stop the spectrum acquisition called from run_acquisition_Action
        """
        pass