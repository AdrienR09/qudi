# -*- coding: utf-8 -*-
"""
This file contains the Qudi logic class that captures and processes photoluminescence
spectra and the spot image.

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

from qtpy import QtCore
from collections import OrderedDict
import numpy as np

from core.connector import Connector
from core.statusvariable import StatusVar
from core.util.mutex import Mutex
from core.util.network import netobtain
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from logic.save_logic import SaveLogic

import math as mt


class DataAnalysisLogic(GenericLogic):

    ##############################################################################
    #                            Initialization functions
    ##############################################################################


    _file_path = StatusVar("file_path", None)
    if _file_path == None:
        _file_path = ConfigOption("file_path", missing='warn')

    _data = StatusVar("spim_matrix", np.empty((2,2,2)))
    _axis_range = StatusVar("axis_range", [(0,10e-4),(0,10e-4),(0,10e-4)])
    _axis_name = StatusVar("axis_name", ["X axis", "Y axis", "Wavelength"])
    _axis_unit = StatusVar("axis_unit", ["m", "m", "nm"])
    _values_name = StatusVar("values_name", "counts")
    _values_unit = StatusVar("values_unit", "/s")


    def __init__(self, **kwargs):
        """ Create SpectrumLogic object with connectors and status variables loaded.

          @param dict kwargs: optional parameters
        """
        super().__init__(**kwargs)

    def on_activate(self):

        with open(self._file_path, mode='r', encoding='latin-1') as file:
            self._data = file.read()


    def define_axis(self, axis_name, axis_range):
        """ Function defining the principe data_axis
        """
        if not len(axis_name) == self._dim:
            self.log.warning("")
        self._axis_range = axis_range
        self._axis_name = axis_name

    def affine_plane_slicing(self, normal_vector, offset_point):
        """

        """
        data_shape = self._data.shape
        v1, v2, v3 = normal_vector
        x_pos = np.arange(data_shape[0])
        y_pos = np.arange(data_shape[1])
        X_pos, Y_pos = np.meshgrid(x_pos, y_pos)
        affine_plane = -v1/v3*X_pos -v2/v3*Y_pos + offset_point
        affine_plane = affine_plane.T
        sliced_data = np.array([self._data[i, j, int(affine_plane[i, j])] for i in x_pos for j in y_pos
                                if i>0 and j>0 and data_shape[2]>affine_plane[i, j]>0])
        return sliced_data

